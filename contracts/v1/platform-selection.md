# Platform selection contract v1 — v0.2 slice 2

This is base-platform selection, not artifact compatibility or installation.
Doctor and the slice-1 adapter are unchanged. There is no new CLI command.
No hardware discovery, opkg, network, filesystem writes, cache, dependency
resolver, artifact reader or executor is added.

## Host/build boundary

`platform-manifest.schema.json` defines the host JSON shape. The host-only
`tools/platform_manifest.py:normalize(text)` performs strict JSON decoding
(including duplicate keys, trailing data and nonstandard numeric constants),
shape/type checks, fixed-field checks and normalization to 12 literal arguments.
Unknown fields are invalid. Unknown schema versions are unsupported.

The normalizer validates this specific contract; it is NOT a general JSON Schema
implementation. Its returned record MUST additionally pass `nm_validate` for
adapter-specific ABI semantics. Schema conformance alone is not sufficient.
Any host decoding/normalization failure MUST call `np_invalid_input(code)` and
invalidate the active set; callers must never skip failed documents.

Production router JSON ingestion and JSON validation parity are NOT implemented.
Python is a host tool only; the shell modules have no external-command dependency.

## Manifest

Required top-level fields: schema_version (integer 1), document_type (platform),
id, identity. Optional note is informational, printable ASCII, at most 256 chars.
Identity requires distribution, release, revision, board_name, target,
architecture, kernel, kernel_abi. Revision requires policy, value and rationale.

- ID: 1..64 ASCII letters/digits/underscore/dot/hyphen; IDs are unique per set.
- Identity tokens: 1..128 ASCII letters/digits or `_.,/+~-`.
- Distribution: exact OpenWrt or ImmortalWrt.
- Revision policy: exact or informational, no other policies.
- Exact revision value: nonempty token, not null; rationale may be empty.
- Informational revision value: token or null; nonempty rationale is required.
- Rationale: printable ASCII, at most 256 characters. Never executed.
- Kernel ABI: JSON null, or canonical identifier accepted by slice-1
  `nk_parse_feed`; no second ABI parser. Null is NOT a wildcard.
- Input JSON text: at most 16384 UTF-8 bytes. No package URLs or references.

No wildcard, regex, prefix, substring, nearest-version or case-fold matching.
The token character class describes syntax only, never a matching expression.

## Router normalized manifest interface

Legacy observation mode sources kernel-identity.sh, manifest.sh, resolver.sh.
For trusted snapshot mode also source observations.sh and verifiers.sh.
`nm_validate` and `np_add_manifest` accept exactly these 12 quoted arguments:

    schema id distribution release revision_policy revision_value rationale
    board_name target architecture kernel kernel_abi

JSON null is represented by the literal `-` ONLY for informational revision and
kernel_abi. Literal JSON string `-` is forbidden for these fields by the host
normalizer. Empty ABI is invalid. The normalized contract has no filename,
source priority or component-reference field.

`nm_validate` sets nm_valid/nm_reason and parsed nm_* fields. Functions return 0
for completed evaluation, including invalid input: callers must inspect data.
Trusted caller code owns the argument framing; never source or interpolate data.

## Legacy observation interface and lifecycle

For Slice 3 snapshot consumption, see [observations.md](observations.md).

1. `np_reset` starts a fresh selection and initializes all observations missing.
2. `np_observe field state value source [verification [method]]` supplies each
   observation at most once, before adding any manifests.
3. Submit EVERY active manifest via `np_add_manifest` or every invalid document
   via `np_invalid_input`.
4. `np_finish` computes the final result. Copy results before the next reset.

Fields: distribution, release, revision, board_name, target, architecture, kernel,
kernel_abi. States: known, missing, conflicting, unsupported. Unknown state or
invalid known token is treated as unsupported, never a proven mismatch.
Unknown field, duplicate observation or bad observation arity invalidates the
snapshot and blocks selection. Omitted records remain missing. Source strings
are preserved, not interpreted as permissions or commands.

Raw observation fields are retained in np_observation_records using concatenated
length:original-value records (field/state/value/source, and ABI marker/method).
Lengths use shell character semantics; identity fields are ASCII. The caller
retains original structured evidence and all conflicting values; no parser for
these evidence records is provided. Snapshots are immutable during evaluation.

## Predicates and classification

Each of distribution/release/board_name/target/architecture/kernel compares exact
known router value to manifest value. Exact revision follows the same rule.
Informational revision contributes TRUE for policy satisfaction, NOT equality;
its observed value/state does not decide base matching.

- known exact equality -> TRUE;
- known exact inequality -> FALSE with the dimension mismatch code;
- missing/unsupported -> UNDETERMINED / IDENTITY_FIELD_UNAVAILABLE;
- conflicting -> UNDETERMINED / IDENTITY_EVIDENCE_CONFLICT.

Any FALSE -> NO_MATCH. Otherwise any UNDETERMINED -> UNDETERMINED.
All mandatory base predicates TRUE -> MATCH. Invalid manifest -> INVALID.
All field predicates and applicable reasons are retained for each candidate.
Duplicate IDs invalidate the active set (MANIFEST_REFERENCE_INVALID), even when
the first occurrence was provisionally classified MATCH. No duplicate wins.

Per-candidate outputs: np_candidate_id, np_candidate_class,
np_candidate_predicates (field:predicate records), np_candidate_reasons,
np_kernel_predicate, np_candidate_kernel. Capture these after each submission.

## Selection precedence and deterministic output

- Any INVALID input -> BLOCKED / MANIFEST_INVALID.
- Invalid observation envelope -> BLOCKED / MANIFEST_SELECTION_UNDETERMINED.
- More than one MATCH -> BLOCKED / MANIFEST_SELECTION_AMBIGUOUS.
- Any UNDETERMINED contender -> BLOCKED / MANIFEST_SELECTION_UNDETERMINED.
- Exactly one MATCH and no UNDETERMINED -> SELECTED / PLATFORM_MATCH.
- Otherwise -> BLOCKED / MANIFEST_NOT_FOUND.

np_selected_id is empty for every blocked result. The order-independent final
outputs are np_selection, np_selected_id, np_selection_reason,
np_base_compatibility and np_selected_kernel. Candidate records are keyed by ID,
not filesystem order; scratch fields such as np_match_id are NOT selected output.
Invalid-input detail codes are appended in fixed schema/reference order. Candidate
reason order is fixed identity-field order followed by ABI checks; codes are unique.

## Kernel boundary

Base selection does not use ABI. Kernel compatibility aggregates base compatibility
with a separate kernel predicate via slice-1 nk_aggregate.

- Manifest null ABI -> UNDETERMINED / KERNEL_ABI_UNAVAILABLE.
- Router ABI missing/unsupported -> UNDETERMINED / KERNEL_ABI_UNAVAILABLE.
- Conflicting ABI -> UNDETERMINED / IDENTITY_EVIDENCE_CONFLICT and KERNEL_ABI_UNVERIFIED.
- Known but unverified ABI -> UNDETERMINED / KERNEL_ABI_UNVERIFIED.
- Any externally supplied verified marker/method -> UNDETERMINED.
- ABI rejected by the slice-1 parser -> UNDETERMINED / KERNEL_METADATA_FORMAT_UNSUPPORTED.
- Valid verified ABI equal to manifest -> TRUE; different -> FALSE / KERNEL_ABI_MISMATCH.

Slice 3 supersedes the former externally trusted marker precondition.
Legacy marker/method arguments are audit-only, even for a registered method ID.
Use the [sealed observation contract](observations.md) and np_load_snapshot for
registry-produced version-consistency binding. A raw fixture cannot confer trust.

Selection and even kernel COMPATIBLE do not prove artifact compatibility.
np_installation_eligible, np_execution_supported and np_execution_authorized
are always false. No resolution/stage/apply eligibility is conferred by selection.

## Stable reasons

New selection reasons: PLATFORM_MATCH, DISTRIBUTION_MISMATCH, RELEASE_MISMATCH,
REVISION_MISMATCH, BOARD_MISMATCH, TARGET_MISMATCH, ARCH_MISMATCH,
IDENTITY_FIELD_UNAVAILABLE, IDENTITY_EVIDENCE_CONFLICT, MANIFEST_NOT_FOUND,
MANIFEST_SELECTION_AMBIGUOUS, MANIFEST_SELECTION_UNDETERMINED, MANIFEST_INVALID,
MANIFEST_SCHEMA_UNSUPPORTED, MANIFEST_REFERENCE_INVALID.

Reused slice-1 reasons: KERNEL_VERSION_MISMATCH, KERNEL_ABI_MISMATCH,
KERNEL_ABI_UNAVAILABLE, KERNEL_ABI_UNVERIFIED, KERNEL_METADATA_FORMAT_UNSUPPORTED.
Reasons are identifiers, never executable text or behavior encoded in prose.
