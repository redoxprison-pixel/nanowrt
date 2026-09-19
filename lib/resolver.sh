# Deterministic base selection over normalized observations/manifests.
# Requires kernel-identity.sh and manifest.sh. No detection, JSON or file access.
np_reset() {
    np_seen_observations='' np_observation_records='' np_observations_invalid=false
    np_snapshot_locked=false np_trusted_snapshot=false np_snapshot_generation=''
    np_seen_ids='' np_matches=0 np_undetermined=0 np_invalid=false
    np_schema_invalid=false np_reference_invalid=false
    np_match_id='' np_match_kernel=UNKNOWN
    np_selected_id='' np_selection=BLOCKED np_selection_reason=MANIFEST_NOT_FOUND
    np_installation_eligible=false np_execution_supported=false np_execution_authorized=false
    np_distribution_state=missing np_distribution_value=''
    np_release_state=missing np_release_value=''
    np_revision_state=missing np_revision_value=''
    np_board_name_state=missing np_board_name_value=''
    np_target_state=missing np_target_value=''
    np_architecture_state=missing np_architecture_value=''
    np_kernel_state=missing np_kernel_value=''
    np_kernel_abi_state=missing np_kernel_abi_value=''
}

# Legacy literal observations: marker/method arguments are audit data only.
# Only np_load_snapshot can attach a registered, sealed verification result.
np_observe() {
    if [ "$np_snapshot_locked" = true ]; then np_observations_invalid=true; return 0; fi
    if [ "$#" -lt 4 ] || [ "$#" -gt 6 ]; then np_observations_invalid=true; return 0; fi
    case " $np_seen_observations " in *" $1 "*) np_observations_invalid=true; return 0 ;; esac
    np_seen_observations="$np_seen_observations $1"
    np_observation_records="${np_observation_records}${#1}:$1${#2}:$2${#3}:$3${#4}:$4"
    np_observed_state=$2
    case "$2" in known|missing|conflicting|unsupported) ;; *) np_observed_state=unsupported ;; esac
    if [ "$np_observed_state" = known ] && ! nm_token "$3"; then np_observed_state=unsupported; fi
    case "$1" in
        distribution) np_distribution_state=$np_observed_state np_distribution_value=$3 ;;
        release) np_release_state=$np_observed_state np_release_value=$3 ;;
        revision) np_revision_state=$np_observed_state np_revision_value=$3 ;;
        board_name) np_board_name_state=$np_observed_state np_board_name_value=$3 ;;
        target) np_target_state=$np_observed_state np_target_value=$3 ;;
        architecture) np_architecture_state=$np_observed_state np_architecture_value=$3 ;;
        kernel) np_kernel_state=$np_observed_state np_kernel_value=$3 ;;
        kernel_abi) np_kernel_abi_state=$np_observed_state np_kernel_abi_value=$3 ;;
        *) np_observations_invalid=true ;;
    esac
    if [ "$1" = kernel_abi ]; then
        np_claimed_verification=${5:-unverified} np_claimed_method=${6:-}
        np_observation_records="${np_observation_records}${#np_claimed_verification}:$np_claimed_verification${#np_claimed_method}:$np_claimed_method"
    fi
}

# Snapshot values are copied once; generation and fault checks prevent stale reuse.
# Snapshot globals are produced by observations.sh, never accepted as arguments.
# shellcheck disable=SC2154
np_load_snapshot() {
    if [ "$np_snapshot_locked" = true ] || [ -n "$np_seen_observations" ] ||
        ! command -v ns_ready >/dev/null 2>&1 || ! ns_ready; then
        np_observations_invalid=true
        return 0
    fi
    for np_field in distribution release revision board_name target architecture kernel kernel_abi; do
        ns_get "$np_field"
        np_observe "$np_field" "$ns_state" "$ns_value" "$ns_provenance"
    done
    np_trusted_snapshot=true np_snapshot_generation=$ns_generation
    np_snapshot_locked=true
}

# shellcheck disable=SC2154
np_check_snapshot() {
    if [ "$np_trusted_snapshot" = true ]; then
        if ! ns_ready || [ "$np_snapshot_generation" != "$ns_generation" ]; then
            np_observations_invalid=true
        fi
    fi
}

np_reason() {
    case " $np_candidate_reasons " in *" $1 "*) return 0 ;; esac
    np_candidate_reasons="${np_candidate_reasons}${np_candidate_reasons:+ }$1"
}

np_exact() {
    np_predicate=UNDETERMINED
    case "$1" in
        known)
            if [ "$2" = "$3" ]; then np_predicate=TRUE
            else np_predicate=FALSE; np_reason "$4"; fi ;;
        conflicting) np_reason IDENTITY_EVIDENCE_CONFLICT ;;
        *) np_reason IDENTITY_FIELD_UNAVAILABLE ;;
    esac
}

# An invalid JSON/host contract must be submitted here with an explicit reason code.
np_invalid_input() {
    np_snapshot_locked=true
    np_invalid=true np_candidate_class=INVALID
    np_candidate_id='' np_candidate_reasons=MANIFEST_INVALID
    np_candidate_predicates='' np_candidate_kernel=UNKNOWN np_kernel_predicate=UNDETERMINED
    case "${1:-}" in
        MANIFEST_SCHEMA_UNSUPPORTED) np_schema_invalid=true; np_reason MANIFEST_SCHEMA_UNSUPPORTED ;;
        MANIFEST_REFERENCE_INVALID) np_reference_invalid=true; np_reason MANIFEST_REFERENCE_INVALID ;;
    esac
}

# nm_validate/nk_parse_feed/nk_aggregate publish globals in sourced modules.
# shellcheck disable=SC2154
np_add_manifest() {
    np_check_snapshot
    np_snapshot_locked=true
    np_candidate_id='' np_candidate_reasons='' np_candidate_predicates=''
    np_candidate_kernel=UNKNOWN np_kernel_predicate=UNDETERMINED
    nm_validate "$@"
    if [ "$nm_valid" != true ]; then
        np_invalid_input "$nm_reason"
        return 0
    fi
    np_candidate_id=$nm_id
    case " $np_seen_ids " in
        *" $nm_id "*)
            np_invalid_input MANIFEST_REFERENCE_INVALID
            np_candidate_id=$nm_id
            return 0 ;;
    esac
    np_seen_ids="$np_seen_ids $nm_id"
    np_base=COMPATIBLE
    np_exact "$np_distribution_state" "$np_distribution_value" "$nm_distribution" DISTRIBUTION_MISMATCH
    np_candidate_predicates="$np_candidate_predicates distribution:$np_predicate"
    case "$np_predicate:$np_base" in
        FALSE:*) np_base=INCOMPATIBLE ;;
        UNDETERMINED:COMPATIBLE) np_base=UNKNOWN ;;
    esac
    np_exact "$np_release_state" "$np_release_value" "$nm_release" RELEASE_MISMATCH
    np_candidate_predicates="$np_candidate_predicates release:$np_predicate"
    case "$np_predicate:$np_base" in
        FALSE:*) np_base=INCOMPATIBLE ;;
        UNDETERMINED:COMPATIBLE) np_base=UNKNOWN ;;
    esac
    if [ "$nm_revision_policy" = informational ]; then np_predicate=TRUE
    else np_exact "$np_revision_state" "$np_revision_value" "$nm_revision" REVISION_MISMATCH; fi
    np_candidate_predicates="$np_candidate_predicates revision:$np_predicate"
    case "$np_predicate:$np_base" in
        FALSE:*) np_base=INCOMPATIBLE ;;
        UNDETERMINED:COMPATIBLE) np_base=UNKNOWN ;;
    esac
    np_exact "$np_board_name_state" "$np_board_name_value" "$nm_board" BOARD_MISMATCH
    np_candidate_predicates="$np_candidate_predicates board_name:$np_predicate"
    case "$np_predicate:$np_base" in
        FALSE:*) np_base=INCOMPATIBLE ;;
        UNDETERMINED:COMPATIBLE) np_base=UNKNOWN ;;
    esac
    np_exact "$np_target_state" "$np_target_value" "$nm_target" TARGET_MISMATCH
    np_candidate_predicates="$np_candidate_predicates target:$np_predicate"
    case "$np_predicate:$np_base" in
        FALSE:*) np_base=INCOMPATIBLE ;;
        UNDETERMINED:COMPATIBLE) np_base=UNKNOWN ;;
    esac
    np_exact "$np_architecture_state" "$np_architecture_value" "$nm_architecture" ARCH_MISMATCH
    np_candidate_predicates="$np_candidate_predicates architecture:$np_predicate"
    case "$np_predicate:$np_base" in
        FALSE:*) np_base=INCOMPATIBLE ;;
        UNDETERMINED:COMPATIBLE) np_base=UNKNOWN ;;
    esac
    np_exact "$np_kernel_state" "$np_kernel_value" "$nm_kernel" KERNEL_VERSION_MISMATCH
    np_candidate_predicates="$np_candidate_predicates kernel:$np_predicate"
    case "$np_predicate:$np_base" in
        FALSE:*) np_base=INCOMPATIBLE ;;
        UNDETERMINED:COMPATIBLE) np_base=UNKNOWN ;;
    esac
    # Malformed observation envelope invalidates its predicates as evidence.
    if [ "$np_observations_invalid" = true ]; then
        np_base=UNKNOWN
        np_candidate_reasons=IDENTITY_FIELD_UNAVAILABLE
        np_candidate_predicates=observations:UNDETERMINED
    fi
    case "$np_base" in
        COMPATIBLE) np_candidate_class=MATCH; np_reason PLATFORM_MATCH ;;
        INCOMPATIBLE) np_candidate_class=NO_MATCH ;;
        *) np_candidate_class=UNDETERMINED ;;
    esac
    if [ "$nm_abi" = '-' ]; then
        np_reason KERNEL_ABI_UNAVAILABLE
    elif [ "$np_trusted_snapshot" = true ] && [ "$ns_verification" != verified ]; then
        np_reason KERNEL_ABI_UNVERIFIED
        # Reasons are a closed set of internal identifiers, not input values.
        np_pending_reasons=$ns_reasons
        while [ -n "$np_pending_reasons" ]; do
            np_reason "${np_pending_reasons%% *}"
            case "$np_pending_reasons" in
                *' '*) np_pending_reasons=${np_pending_reasons#* } ;;
                *) np_pending_reasons='' ;;
            esac
        done
    elif [ "$np_kernel_abi_state" = conflicting ]; then
        np_reason IDENTITY_EVIDENCE_CONFLICT
        np_reason KERNEL_ABI_UNVERIFIED
    elif [ "$np_kernel_abi_state" != known ]; then
        np_reason KERNEL_ABI_UNAVAILABLE
    elif [ "$np_trusted_snapshot" != true ]; then
        np_reason KERNEL_ABI_UNVERIFIED
    else
        nk_parse_feed "$nm_distribution" "$np_kernel_abi_value"
        if [ "$nk_parse_state" != TRUE ]; then
            np_reason KERNEL_METADATA_FORMAT_UNSUPPORTED
        elif [ "$np_observations_invalid" = true ]; then
            np_reason KERNEL_ABI_UNVERIFIED
        elif [ "$np_kernel_abi_value" = "$nm_abi" ]; then np_kernel_predicate=TRUE
        else np_kernel_predicate=FALSE; np_reason KERNEL_ABI_MISMATCH
        fi
    fi
    case "$np_base" in
        COMPATIBLE) np_base_predicate=TRUE ;;
        INCOMPATIBLE) np_base_predicate=FALSE ;;
        *) np_base_predicate=UNDETERMINED ;;
    esac
    nk_aggregate "$np_base_predicate" "$np_kernel_predicate"
    np_candidate_kernel=$nk_compatibility
    case "$np_candidate_class" in
        MATCH)
            np_matches=$((np_matches + 1))
            np_match_id=$nm_id np_match_kernel=$np_candidate_kernel ;;
        UNDETERMINED) np_undetermined=$((np_undetermined + 1)) ;;
    esac
}

np_finish() {
    np_check_snapshot
    np_selected_id='' np_selection=BLOCKED np_selected_kernel=UNKNOWN
    np_base_compatibility=UNKNOWN
    if [ "$np_invalid" = true ]; then
        np_selection_reason=MANIFEST_INVALID
        [ "$np_schema_invalid" != true ] || np_selection_reason="$np_selection_reason MANIFEST_SCHEMA_UNSUPPORTED"
        [ "$np_reference_invalid" != true ] || np_selection_reason="$np_selection_reason MANIFEST_REFERENCE_INVALID"
    elif [ "$np_observations_invalid" = true ]; then np_selection_reason=MANIFEST_SELECTION_UNDETERMINED
    elif [ "$np_matches" -gt 1 ]; then np_selection_reason=MANIFEST_SELECTION_AMBIGUOUS
    elif [ "$np_undetermined" -gt 0 ]; then np_selection_reason=MANIFEST_SELECTION_UNDETERMINED
    elif [ "$np_matches" -eq 1 ]; then
        np_selection=SELECTED np_selected_id=$np_match_id
        np_base_compatibility=COMPATIBLE np_selected_kernel=$np_match_kernel
        np_selection_reason=PLATFORM_MATCH
    else np_selection_reason=MANIFEST_NOT_FOUND
    fi
}
