# Narrow in-memory evidence collector. Requires manifest.sh and verifiers.sh.
# Trusted shell code supplies extracted literal values, never source text to execute.
# ns_* storage is private by convention, not a sandbox against arbitrary shell code.
ns_generation=0

ns_reset() {
    ns_generation=$((${ns_generation:-0} + 1))
    ns_phase=collecting ns_fault='' ns_input_count=0 ns_raw_records=''
    ns_state_invalid=false
    ns_verifier='' ns_verification=unverified ns_binding=UNDETERMINED
    ns_abi='' ns_reasons=VERIFIER_UNAVAILABLE ns_feed_check=UNDETERMINED
    ns_distribution_record='|false|false|'
    ns_release_record='|false|false|'
    ns_revision_record='|false|false|'
    ns_board_name_record='|false|false|'
    ns_target_record='|false|false|'
    ns_architecture_record='|false|false|'
    ns_kernel_record='|false|false|'
    ns_installed_kernel_record='|false|false|'
    ns_feed_abi_record='|false|false|'
    ns_claimed_abi_record='|false|false|'
}

# Unknown fields are structural errors. No variable-name construction or eval.
ns_read_record() {
    ns_record=''
    case "$1" in
        distribution) ns_record=$ns_distribution_record ;;
        release) ns_record=$ns_release_record ;;
        revision) ns_record=$ns_revision_record ;;
        board_name) ns_record=$ns_board_name_record ;;
        target) ns_record=$ns_target_record ;;
        architecture) ns_record=$ns_architecture_record ;;
        kernel) ns_record=$ns_kernel_record ;;
        installed_kernel) ns_record=$ns_installed_kernel_record ;;
        feed_abi) ns_record=$ns_feed_abi_record ;;
        claimed_abi) ns_record=$ns_claimed_abi_record ;;
        *) return 1 ;;
    esac
}

ns_write_record() {
    case "$1" in
        distribution) ns_distribution_record=$2 ;;
        release) ns_release_record=$2 ;;
        revision) ns_revision_record=$2 ;;
        board_name) ns_board_name_record=$2 ;;
        target) ns_target_record=$2 ;;
        architecture) ns_architecture_record=$2 ;;
        kernel) ns_kernel_record=$2 ;;
        installed_kernel) ns_installed_kernel_record=$2 ;;
        feed_abi) ns_feed_abi_record=$2 ;;
        claimed_abi) ns_claimed_abi_record=$2 ;;
        *) return 1 ;;
    esac
}

ns_reject_mutation() {
    # Fault latch is outside immutable snapshot data; consumption must fail closed.
    ns_fault=SNAPSHOT_MUTATION_REJECTED
    return 1
}

# field, state, raw value, stable provenance ID. No verification input is accepted.
ns_collect() {
    [ "$ns_phase" = collecting ] || { ns_reject_mutation; return 1; }
    if [ "$#" -ne 4 ]; then ns_fault=OBSERVATION_INVALID; return 1; fi
    if ! ns_read_record "$1"; then ns_fault=OBSERVATION_INVALID; return 1; fi
    case "$4" in
        openwrt-release|os-release|board-json|sysinfo-board|proc-kernel-osrelease|uname-r|opkg-config|installed-kernel-package|configured-kmods-feed|caller-claim) ;;
        *) ns_fault=OBSERVATION_INVALID; return 1 ;;
    esac
    ns_input_count=$((ns_input_count + 1))
    if [ "$ns_input_count" -gt 128 ] || [ "${#3}" -gt 128 ] || [ "${#2}" -gt 32 ]; then
        ns_fault=OBSERVATION_INVALID; return 1
    fi
    ns_raw_records="${ns_raw_records}${#1}:$1${#2}:$2${#3}:$3${#4}:$4"
    ns_known=${ns_record%%|*}; ns_tail=${ns_record#*|}
    ns_conflict=${ns_tail%%|*}; ns_tail=${ns_tail#*|}
    ns_unsupported=${ns_tail%%|*}; ns_sources=${ns_tail#*|}
    ns_input_state=$2
    case "$ns_input_state" in
        known) if ! nm_token "$3"; then ns_input_state=unsupported; fi ;;
        missing|conflicting|unsupported) ;;
        *) ns_input_state=unsupported; ns_state_invalid=true ;;
    esac
    case "$ns_input_state" in
        known)
            if [ -n "$ns_known" ] && [ "$ns_known" != "$3" ]; then ns_conflict=true; fi
            # Once conflicting, discard the arbitrary first value permanently.
            [ "$ns_conflict" = true ] || ns_known=$3 ;;
        conflicting) ns_conflict=true ;;
        unsupported) ns_unsupported=true ;;
    esac
    [ "$ns_conflict" != true ] || ns_known=''
    ns_sources="$ns_sources $4"
    ns_provenance=''
    for ns_source in openwrt-release os-release board-json sysinfo-board proc-kernel-osrelease uname-r opkg-config installed-kernel-package configured-kmods-feed caller-claim; do
        case " $ns_sources " in
            *" $ns_source "*) ns_provenance="${ns_provenance}${ns_provenance:+ }$ns_source" ;;
        esac
    done
    ns_write_record "$1" "$ns_known|$ns_conflict|$ns_unsupported|$ns_provenance"
}

# Read normalized fields, including the internally derived ABI. No trust setters.
ns_get() {
    ns_value='' ns_state=missing ns_provenance='' ns_observation=observed
    if [ "$1" = kernel_abi ]; then
        ns_value=$ns_abi ns_observation=$ns_verification ns_provenance=$ns_verifier
        [ -z "$ns_value" ] || ns_state=known
        return 0
    fi
    ns_read_record "$1" || return 1
    ns_value=${ns_record%%|*}; ns_tail=${ns_record#*|}
    ns_conflict=${ns_tail%%|*}; ns_tail=${ns_tail#*|}
    ns_unsupported=${ns_tail%%|*}; ns_provenance=${ns_tail#*|}
    if [ "$ns_conflict" = true ]; then ns_state=conflicting
    elif [ "$ns_unsupported" = true ]; then ns_state=unsupported
    elif [ -n "$ns_value" ]; then ns_state=known
    fi
    [ "$ns_state" = known ] || ns_value=''
}

# nv_dispatch publishes only implementation-produced results.
# shellcheck disable=SC2154
ns_verify() {
    [ "$ns_phase" = collecting ] || { ns_reject_mutation; return 1; }
    if [ "$#" -ne 1 ]; then ns_fault=OBSERVATION_INVALID; return 1; fi
    if ! command -v nv_dispatch >/dev/null 2>&1 || ! nv_dispatch "$1"; then
        ns_verifier='' ns_verification=unverified ns_binding=UNDETERMINED
        ns_abi='' ns_reasons=VERIFIER_UNAVAILABLE ns_feed_check=UNDETERMINED
        ns_phase=bound
        return 0
    fi
    ns_verifier=$nv_id ns_verification=$nv_verification ns_binding=$nv_binding
    ns_abi=$nv_abi ns_reasons=$nv_reasons ns_feed_check=$nv_feed_check
    ns_phase=bound
}

ns_seal() {
    case "$ns_phase" in
        collecting) ns_phase=sealed ;; # No verifier -> unverified, never a default match.
        bound) ns_phase=sealed ;;
        *) ns_reject_mutation; return 1 ;;
    esac
}

ns_ready() {
    [ "$ns_phase" = sealed ] && [ -z "$ns_fault" ]
}

# Loading trusted code starts unverified; inherited environment is not a snapshot.
ns_reset
