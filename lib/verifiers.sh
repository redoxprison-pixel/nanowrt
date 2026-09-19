# Explicit registry; IDs are data, never command names. Requires kernel-identity.sh.
nv_reason() {
    case " $nv_reasons " in *" $1 "*) return 0 ;; esac
    nv_reasons="${nv_reasons}${nv_reasons:+ }$1"
}

nv_dispatch() {
    nv_id='' nv_verification=unverified nv_binding=UNDETERMINED
    nv_abi='' nv_reasons='' nv_feed_check=UNDETERMINED
    case "$1" in
        openwrt-immortalwrt-kernel-package-v1)
            nv_id=openwrt-immortalwrt-kernel-package-v1
            if ! command -v nk_parse_identity >/dev/null 2>&1 ||
                ! command -v nk_parts_valid >/dev/null 2>&1 ||
                ! command -v nk_parse_feed >/dev/null 2>&1; then
                nv_reason VERIFIER_UNAVAILABLE
            else nv_kernel_package; fi ;;
        '') nv_reason VERIFIER_UNAVAILABLE ;;
        *) nv_reason VERIFIER_UNKNOWN ;;
    esac
}

# Snapshot/parser globals are outputs from ns_get and nk_parse_identity/feed.
# shellcheck disable=SC2154
nv_kernel_package() {
    if [ -n "$ns_fault" ]; then nv_reason "$ns_fault"; return 0; fi
    if [ "$ns_state_invalid" = true ]; then
        nv_reason OBSERVATION_STATE_INVALID; return 0
    fi
    nv_inputs_ok=true
    # Check every identity field's explicit conflict/unsupported state. Missing
    # base fields remain a resolver concern; the binding requires three fields.
    for nv_field in distribution release revision board_name target architecture kernel installed_kernel feed_abi claimed_abi; do
        ns_get "$nv_field"
        case "$ns_state" in
            conflicting)
                nv_inputs_ok=false
                nv_reason IDENTITY_EVIDENCE_CONFLICT
                [ "$nv_field" != feed_abi ] || nv_reason AMBIGUOUS_KMOD_FEEDS ;;
            unsupported)
                nv_inputs_ok=false
                nv_reason IDENTITY_FIELD_UNAVAILABLE ;;
        esac
    done
    [ "$nv_inputs_ok" = true ] || return 0
    ns_get distribution; nv_distribution=$ns_value
    ns_get kernel; nv_running=$ns_value
    ns_get installed_kernel; nv_installed=$ns_value
    if [ -z "$nv_distribution" ] || [ -z "$nv_running" ]; then
        nv_reason ACTIVE_KERNEL_BINDING_UNVERIFIED
    fi
    if [ -z "$nv_installed" ]; then nv_reason KERNEL_ABI_UNAVAILABLE; fi
    [ -z "$nv_reasons" ] || return 0
    nk_parse_identity "$nv_distribution" "$nv_installed"
    if [ "$nk_parse_state" != TRUE ]; then
        nv_reason KERNEL_METADATA_FORMAT_UNSUPPORTED; return 0
    fi
    nv_candidate=$nk_canonical_abi nv_installed_version=$nk_version
    # Reuse the same VERSION validator, with already parsed RELEASE/VERMAGIC.
    nk_version=$nv_running
    if ! nk_parts_valid; then
        nv_reason KERNEL_METADATA_FORMAT_UNSUPPORTED; return 0
    fi
    nv_binding=TRUE
    if [ "$nv_running" != "$nv_installed_version" ]; then
        nv_binding=FALSE
        nv_reason KERNEL_VERSION_MISMATCH
        nv_reason ACTIVE_KERNEL_BINDING_MISMATCH
    fi
    for nv_field in feed_abi claimed_abi; do
        ns_get "$nv_field"
        [ "$ns_state" = known ] || continue
        nv_supplied=$ns_value
        nk_parse_feed "$nv_distribution" "$nv_supplied"
        if [ "$nk_parse_state" != TRUE ]; then
            [ "$nv_binding" = FALSE ] || nv_binding=UNDETERMINED
            nv_reason KERNEL_METADATA_FORMAT_UNSUPPORTED
        elif [ "$nv_supplied" != "$nv_candidate" ]; then
            nv_binding=FALSE
            nv_reason KERNEL_ABI_MISMATCH
            [ "$nv_field" != feed_abi ] || nv_feed_check=FALSE
        elif [ "$nv_field" = feed_abi ]; then nv_feed_check=TRUE
        fi
    done
    case "$nv_binding" in
        TRUE) nv_verification=verified nv_abi=$nv_candidate ;;
        FALSE) nv_verification=rejected ;;
    esac
}
