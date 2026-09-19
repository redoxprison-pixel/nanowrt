# Trusted observations v1 — v0.2 slice 3

This is an in-memory, literal-argument interface, not a JSON ingestion API or a
new CLI command. Source trusted modules in order: kernel-identity.sh, manifest.sh,
observations.sh, verifiers.sh, resolver.sh. No external utilities, filesystem
access, temporary files, package operations or network are used by these modules.
Doctor's existing acquisition code, output and semantics are unchanged.

## Evidence boundary

Trusted acquisition code extracts raw values and submits **all** relevant evidence
via `ns_collect field state value source`. This collector validates framing,
normalizes and merges evidence without choosing a preferred source. It does not
read paths or execute provenance IDs. This slice does not yet wire live router
acquisition into a new command: raw file/ubus extraction remains with the caller.
Do not convert doctor's printed fallback summary into a trusted snapshot: doing
so would lose conflicting sources. Do not omit unreadable or unsupported sources
and pretend they agree. Production router JSON ingestion is NOT IMPLEMENTED.

A snapshot cannot authenticate a dishonest collector, root, a modified status
database, or arbitrary shell code with access to its globals/functions. Trusted
program code owns framing and ns_/nv_/np_ storage. The guarantee is against
**input data** promoting its own verification status, not process isolation or
cryptographic attestation. Source IDs describe provenance, not trust credentials.

The layers remain distinct: raw evidence -> collector -> normalized observation
-> registered version binding -> manifest compatibility -> base selection.
Installation eligibility, execution support and execution authorization remain
false. No plan, stage, apply, artifact validation or dependency solver is added.

## Fields and provenance

Collectable fields are distribution, release, revision, board_name, target,
architecture, kernel (running VERSION), installed_kernel (installed package
version), feed_abi (already extracted effective ABI candidate), claimed_abi
(optional caller claim, cross-check only). `kernel_abi` is derived and cannot be
collected or assigned through this API.

Stable source IDs follow existing acquisition concepts: openwrt-release,
os-release, board-json, sysinfo-board, proc-kernel-osrelease, uname-r, opkg-config,
installed-kernel-package, configured-kmods-feed, caller-claim. These are metadata;
using installed-kernel-package as a label never bypasses parsing or binding.

Each call has exactly four arguments. Unknown field/source/arity, >128 evidence
records, value >128 characters or state >32 characters latches OBSERVATION_INVALID.
Known values use the existing ASCII identity token validator. Empty values,
whitespace, quotes, substitutions, globs and other disallowed characters become
unsupported, never executable input. Accepted path-like tokens and leading `-`
are literal data, not paths/options. Kernel-specific grammar is checked separately.
States are known, missing, conflicting, unsupported. Invalid states normalize to
unsupported and additionally latch OBSERVATION_STATE_INVALID for verification.

Merge rules are commutative: explicit conflict or distinct known values wins;
otherwise unsupported wins; otherwise any known value wins; otherwise missing.
Conflicts are sticky, and their normalized value is empty. Missing evidence does
not contradict a known value. Equal duplicates are idempotent within the record
limit. Provenance is a unique set in the fixed source-ID order above.

`ns_get field` returns ns_state, ns_value, ns_provenance, ns_observation.
Raw fields are observed; derived kernel_abi is verified, unverified or rejected.
Missing/conflicting/unsupported are distinct even though each normalized value
is empty. Original accepted records are retained in ns_raw_records as concatenated
length:value fields, in arrival order, including duplicates. This is an audit
transcript, **not** the canonical semantic snapshot or a supported serialized
input format. The canonical projection is ns_get results in the fixed field order
above plus derived kernel_abi and binding results. Input order does not affect it.

## Lifecycle and consumption

1. `ns_reset` starts collecting with a new process-local generation. All fields
   are missing. A reset creates a new snapshot; it does not mutate the old one.
2. `ns_collect` accepts evidence only in collecting phase. It returns 1 on
   structural rejection and latches a fault; callers must not ignore the fault.
3. `ns_verify verifier_id` evaluates the static registry once and transitions
   to bound, including failed/unknown verification. No results are accepted as
   parameters. Evidence is frozen at binding time, before sealing.
4. `ns_seal` transitions collecting or bound to sealed. Sealing without a verifier
   retains unverified/VERIFIER_UNAVAILABLE. Repeated sealing is rejected.
5. `ns_ready` returns success only for a sealed snapshot without structural or
   mutation fault. Then `np_reset; np_load_snapshot` copies its normalized fields
   and binds the selection session to that generation. A load after observations
   or evaluation, or a load of an unsealed/faulted snapshot, blocks selection.
6. Submit every active manifest and finish using the existing resolver API.

Mutation attempts after binding/sealing return 1 and latch
SNAPSHOT_MUTATION_REJECTED. Values, states, provenance and verifier results remain
unchanged. The separate fault latch invalidates consumption: a historic verified
field alone is not permission to use it. Resolver rechecks readiness/generation
before each candidate and at np_finish, so a mutation/reset after a provisional
MATCH cannot leave a SELECTED result. Reverification cannot overwrite results.
These are single-snapshot, single-selection-session APIs, not reentrant handles.
Private helpers/globals are not public mutation interfaces.

## Registry and binding

Only registered verifier: `openwrt-immortalwrt-kernel-package-v1`.
Dispatch is a literal case table, never an input-derived function/command name.
Empty ID or unavailable registry/parser implementation -> VERIFIER_UNAVAILABLE;
other IDs -> VERIFIER_UNKNOWN. Neither can verify.

Supported evidence: OpenWrt/ImmortalWrt VERSION~VERMAGIC-rRELEASE installed package
metadata, running VERSION, optional canonical feed ABI and caller ABI claim.
Existing nk_parse_identity, nk_parts_valid and nk_parse_feed implement all grammar;
no duplicate parser is introduced. VERMAGIC is the 32-hex package build hash,
not the textual .ko vermagic. The latter is not collected or verified here.

Binding requires known distribution, running VERSION and installed identity;
valid installed syntax; supported running VERSION; parsed VERSION equal to
running VERSION. Only then can NanoWrt derive VERSION-RELEASE-VERMAGIC internally.
Missing required evidence yields unverified. Any explicit conflict/unsupported
state in the snapshot prevents verification. Missing unrelated platform fields
are separately evaluated by the resolver, never filled in by the kernel binding.

Feeds and claimed ABI are cross-checks only. A known supported equal feed sets
ns_feed_check=TRUE; a known different feed sets FALSE and rejects the binding.
Missing feed leaves UNDETERMINED and does not prevent the independent package/
running-version binding. Conflicting feeds prevent verification. Unsupported
feed/claim syntax prevents verification. A mismatching claim rejects verification;
a matching claim cannot independently establish it. Supply each effective ABI
candidate; a kmods-like URL without an extractable identifier is not a fabricated
known ABI. This interface accepts identifiers, not feed URLs.

Results: ns_verifier (registered ID or empty), ns_verification
(verified/unverified/rejected), ns_binding (TRUE/UNDETERMINED/FALSE), ns_abi
(derived only when verified), ns_reasons, ns_feed_check. Evaluation returns 0 even
when evidence cannot verify; inspect results. Structural/lifecycle failures use 1.

**Verified means only supported package/running VERSION consistency.** It does
not prove the active kernel's complete build identity, artifact bytes, .ko content,
metadata-to-artifact binding or package compatibility. The slice-1 adapter and
its artifact UNKNOWN semantics remain unchanged. Release/target/architecture
identity are independent resolver predicates, not a replacement for kernel ABI.

## Resolver changes

Legacy `np_observe ... verified method` arguments are retained as audit data but
never authorize ABI equality. This includes the actual registered ID supplied
as a string. Only np_load_snapshot can attach a result produced by ns_verify.
A verified derived ABI can then compare exactly with a non-null manifest ABI:
equal -> TRUE, different -> FALSE. Without verified binding -> UNDETERMINED,
even if rejected evidence contains a candidate string. Manifest null remains
UNDETERMINED, not a wildcard. Base selection is still separate from kernel
compatibility, and all installation/execution flags remain false.

## Stable reasons and precedence

New codes: OBSERVATION_INVALID (bad envelope/bounds/source/field),
OBSERVATION_STATE_INVALID (unknown state), SNAPSHOT_MUTATION_REJECTED (late write,
repeat verification or repeated seal), VERIFIER_UNKNOWN, VERIFIER_UNAVAILABLE.

Reused: IDENTITY_EVIDENCE_CONFLICT, IDENTITY_FIELD_UNAVAILABLE,
AMBIGUOUS_KMOD_FEEDS, ACTIVE_KERNEL_BINDING_UNVERIFIED, KERNEL_ABI_UNAVAILABLE,
KERNEL_METADATA_FORMAT_UNSUPPORTED, KERNEL_VERSION_MISMATCH,
ACTIVE_KERNEL_BINDING_MISMATCH, KERNEL_ABI_MISMATCH, KERNEL_ABI_UNVERIFIED.
No synonymous generic VERIFICATION_FAILED or OBSERVATION_CONFLICT is added.

Readiness faults dominate consumption. Registry availability is checked before
verifier execution. Within the registered verifier: structural fault; invalid
state; conflict/unsupported checks in fixed field order (including feed ambiguity);
missing required evidence (binding then installed); installed/running grammar;
version mismatch; feed check; claim check. Earlier blocking phases return without
speculating about later checks. Within the final phase all applicable reasons
are deduplicated in that order; FALSE dominates UNDETERMINED. Late faults remain
separate from immutable prior verifier reasons. Resolver keeps its existing
manifest-invalid > observation-invalid > ambiguity > undetermined > unique-match
precedence. Kernel reasons follow platform reasons.

## Validation and limits

Shell tests exercise actual production functions under sh/dash/BusyBox, including
forged markers, lifecycle misuse, injection, permutations and selector regressions.
R5S reference inputs use the hardware-observed identity; Slice 3 itself has not
been hardware validated. R3S remains fixture/reference only. JSON fixtures are
host-only data; existing manifest/kernel JSON Schemas are unchanged. No router
JSON Schema validator, jq, Python or GNU utility is required.
