# Platform manifest v1 normalized positional contract; no JSON ingestion.
# Requires kernel-identity.sh, supplied by trusted caller. No hardware detection.
nm_token() {
    [ -n "$1" ] && [ "${#1}" -le 128 ] || return 1
    case "$1" in *[!a-zA-Z0-9_.,/+~-]*) return 1 ;; esac
}

# nk_parse_feed publishes nk_parse_state through the slice-1 global API.
# shellcheck disable=SC2154
nm_validate() {
    nm_valid=false nm_reason=MANIFEST_INVALID nm_id=''
    [ "$#" -eq 12 ] || return 0
    nm_schema=$1 nm_id=$2 nm_distribution=$3 nm_release=$4
    nm_revision_policy=$5 nm_revision=$6 nm_rationale=$7
    shift 7
    nm_board=$1 nm_target=$2 nm_architecture=$3 nm_kernel=$4 nm_abi=$5
    if [ "$nm_schema" != 1 ]; then nm_reason=MANIFEST_SCHEMA_UNSUPPORTED; return 0; fi
    case "$nm_id" in ''|*[!a-zA-Z0-9_.-]*) return 0 ;; esac
    [ "${#nm_id}" -le 64 ] || return 0
    for nm_value in "$nm_distribution" "$nm_release" "$nm_board" "$nm_target" "$nm_architecture" "$nm_kernel"; do
        nm_token "$nm_value" || return 0
    done
    case "$nm_distribution" in OpenWrt|ImmortalWrt) ;; *) return 0 ;; esac
    case "$nm_revision_policy" in
        exact) nm_token "$nm_revision" && [ "$nm_revision" != '-' ] || return 0 ;;
        informational)
            nm_token "$nm_revision" || return 0
            [ -n "$nm_rationale" ] || return 0 ;;
        *) return 0 ;;
    esac
    [ "${#nm_rationale}" -le 256 ] || return 0
    # ASCII printable rationale only; it is never a program or match expression.
    case "$nm_rationale" in *[!\ -~]*) return 0 ;; esac
    if [ "$nm_abi" != '-' ]; then
        nk_parse_feed "$nm_distribution" "$nm_abi"
        [ "$nk_parse_state" = TRUE ] || return 0
    fi
    nm_valid=true nm_reason=''
}
