# Kernel compatibility contracts v1 — slice 1

Host JSON Schemas describe synthetic reference inputs and the result projection.
They are not router input formats. No runtime JSON reader, schema validator,
manifest selector, artifact inspector or JSON serializer is implemented here.
Host schema validation requires a separately available JSON Schema validator;
JSON syntax checks alone are not schema validation.

## Router API

Source `lib/kernel-identity.sh` from trusted application code. It is not sourced
by doctor. Call functions with quoted positional arguments; never source data.
Functions do not detect hardware, invoke external commands, or write files.
They return status 0 when evaluation completes; read result globals, not status.
Use exactly the documented arity (evaluate requires at least six arguments).

- `nk_parse_identity distribution raw_identity`: returns `nk_parse_state`,
  `nk_raw_identity`, `nk_version`, `nk_release`, `nk_vermagic`, `nk_canonical_abi`.
- `nk_parse_feed distribution raw_feed_abi`: same parsed fields, `nk_raw_feed`.
  Input is an already extracted identifier, not a URL; no URL parsing here.
- `nk_parse_requirement distribution metadata_state raw_dependency`: returns
  `nk_requirement_state`, `nk_requirement_reason`, `nk_raw_dependency`,
  `nk_requirement_version`, `nk_requirement_release`, `nk_requirement_vermagic`,
  `nk_requirement_abi`, `nk_requirement_evidence=unverified_metadata_only`.
- `nk_aggregate predicate...`: TRUE/FALSE/UNDETERMINED -> `nk_compatibility`.
  Invalid predicates and the empty set are UNKNOWN, unless another predicate
  proves FALSE. FALSE dominates UNDETERMINED.
- `nk_evaluate distribution running_version installed_identity metadata_state
  exact_dependency platform_predicate [feed_abi...]`: returns
  `nk_platform_compatibility`, `nk_resolution_compatibility`,
  `nk_artifact_compatibility`, `nk_resolution_eligible`,
  `nk_installation_eligible`, `nk_execution_supported`, `nk_execution_authorized`,
  `nk_reasons`, `nk_router_candidate`, and normalized requirement fields.
  Raw inputs remain in `nk_raw_running`, `nk_raw_installed`,
  `nk_raw_artifact_dependency`, and `nk_raw_feeds` (concatenated decimal character
  length, colon, original value records; preserves order and duplicates).

Metadata state is `valid`, `invalid`, or `unavailable`. `valid` is a caller
precondition: structural metadata validation is NOT performed by this module.
The parser then validates the entire isolated exact dependency expression.
No complete Depends list is accepted; general dependency parsing is deferred.
Platform predicate is supplied by the caller, not calculated by this slice.
Raw snapshots must be retained by the caller as primary evidence.
Globals are scratch state; copy outputs before the next call. No reentrancy.

## Named adapter and grammar

Adapter ID: `openwrt-immortalwrt-kernel-package`, version `1`.
Distributions: exact `OpenWrt` or `ImmortalWrt` only.
This is the explicitly supported format family supplied in the slice contract,
not a claim to support every build/version of either distribution.

- decimal component: `0` or a nonzero-leading decimal integer, at most 6 digits;
- VERSION: exactly three decimal components joined with dots;
- RELEASE: nonzero-leading positive decimal integer, at most 6 digits;
- VERMAGIC: exactly 32 lowercase hexadecimal characters;
- installed identity: `VERSION~VERMAGIC-rRELEASE`;
- feed ABI: `VERSION-RELEASE-VERMAGIC`;
- isolated exact dependency: `kernel (= VERSION~VERMAGIC-rRELEASE)`.

No whitespace normalization, case conversion, prefix matching, optional suffixes,
leading-zero normalization, URL handling, shell expansion or generic rearranging.
Unknown formats remain UNDETERMINED. Parsed fields are empty on parse failure.
Raw values remain unchanged. Canonical ABI is constructed only after every
component passes this adapter's grammar. VERMAGIC here is the build hash field,
not the full textual `.ko` vermagic string.

## Evidence and results

Running VERSION must equal parsed installed VERSION. Inequality proves
ACTIVE_KERNEL_BINDING_MISMATCH and KERNEL_VERSION_MISMATCH. Equality establishes
only version consistency (`nk_active_kernel_evidence=version_consistency_only`),
not cryptographic/complete active-build identity. No full active-kernel verifier
is implemented. Feed identifiers are supporting cross-checks, never root proof.
No feeds is allowed for resolution consistency; it adds no ABI evidence.
Identical candidates agree. Distinct valid candidates produce UNKNOWN ambiguity;
a single different candidate produces a proven cross-check mismatch. Invalid
candidates remain unsupported. No candidate is chosen from an ambiguous set.

Resolution compatibility concerns only supplied platform predicate, version
binding consistency, feed consistency, and normalized exact kernel requirement.
`resolution_eligible=true` means those narrow predicates pass; it is NOT full
dependency resolution, stage eligibility, verified artifact compatibility, or
permission to install. Artifact compatibility additionally contains a mandatory
UNDETERMINED verification predicate; it can never be COMPATIBLE in this slice.
Installation eligibility and both execution flags are always false.
A proven FALSE still dominates unknown verification (INCOMPATIBLE).

Reasons are stable identifiers declared by kernel-result.schema.json. They are
unique, ordered by fixed evaluation phases: installed/binding, feeds, requirement,
then verification blockers. Multiple problems are retained; there is no behavior
encoded in explanatory text. Feed order does not change semantic decisions or
reasons. Human raw input order is preserved separately.

No provenance verification, artifact byte binding, .ko inspection, dependency
solver, network access, package operations or router state changes exist here.
