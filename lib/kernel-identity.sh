# NanoWrt kernel contract v1. Pure argument consumers; no detection or I/O.
# Adapter scope is explicitly OpenWrt/ImmortalWrt VERSION~VERMAGIC-rRELEASE.
# Public functions return data in nk_* globals; status 0 means evaluation completed.
nk_adapter_id=openwrt-immortalwrt-kernel-package
nk_adapter_version=1

nk_digits() {
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
    [ "${#1}" -le 6 ] || return 1
    case "$1" in 0|[1-9]|[1-9][0-9]*) return 0 ;; *) return 1 ;; esac
}

nk_parts_valid() {
    case "$nk_version" in *.*.*) ;; *) return 1 ;; esac
    nk_major=${nk_version%%.*}
    nk_tail=${nk_version#*.}
    nk_minor=${nk_tail%%.*}
    nk_patch=${nk_tail#*.}
    nk_digits "$nk_major" && nk_digits "$nk_minor" && nk_digits "$nk_patch" || return 1
    nk_digits "$nk_release" && [ "$nk_release" != 0 ] || return 1
    [ "${#nk_vermagic}" -eq 32 ] || return 1
    case "$nk_vermagic" in *[!0-9a-f]*) return 1 ;; esac
}

nk_parse_identity() {
    nk_raw_identity=$2
    nk_parse_state=UNDETERMINED
    nk_version='' nk_release='' nk_vermagic='' nk_canonical_abi=''
    case "$1" in OpenWrt|ImmortalWrt) ;; *) return 0 ;; esac
    [ "${#2}" -le 62 ] || return 0
    case "$2" in *'~'*'-r'*) ;; *) return 0 ;; esac
    nk_version=${2%%~*}
    nk_tail=${2#*~}
    nk_vermagic=${nk_tail%%-r*}
    nk_release=${nk_tail#*-r}
    if nk_parts_valid; then
        nk_canonical_abi=$nk_version-$nk_release-$nk_vermagic
        nk_parse_state=TRUE
    else
        nk_version='' nk_release='' nk_vermagic=''
    fi
}

nk_parse_feed() {
    nk_raw_feed=$2
    nk_parse_state=UNDETERMINED
    nk_version='' nk_release='' nk_vermagic='' nk_canonical_abi=''
    case "$1" in OpenWrt|ImmortalWrt) ;; *) return 0 ;; esac
    [ "${#2}" -le 60 ] || return 0
    case "$2" in *-*-*) ;; *) return 0 ;; esac
    nk_version=${2%%-*}
    nk_tail=${2#*-}
    nk_release=${nk_tail%%-*}
    nk_vermagic=${nk_tail#*-}
    if nk_parts_valid; then
        nk_canonical_abi=$nk_version-$nk_release-$nk_vermagic
        nk_parse_state=TRUE
    else
        nk_version='' nk_release='' nk_vermagic=''
    fi
}

# A single exact requirement, NOT a complete Depends expression/parser.
nk_parse_requirement() {
    nk_raw_dependency=$3
    nk_requirement_state=UNDETERMINED
    nk_requirement_abi='' nk_requirement_version=''
    nk_requirement_release='' nk_requirement_vermagic=''
    nk_requirement_reason=PACKAGE_METADATA_UNAVAILABLE
    nk_requirement_evidence=unverified_metadata_only
    case "$2" in
        unavailable) return 0 ;;
        valid) ;;
        *) nk_requirement_reason=PACKAGE_METADATA_INVALID; return 0 ;;
    esac
    nk_requirement_reason=DEPENDENCY_SYNTAX_UNSUPPORTED
    [ "${#3}" -le 73 ] || return 0
    case "$3" in 'kernel (= '*) ;; *) return 0 ;; esac
    case "$3" in *')') ;; *) return 0 ;; esac
    nk_dependency_identity=${3#'kernel (= '}
    nk_dependency_identity=${nk_dependency_identity%')'}
    nk_parse_identity "$1" "$nk_dependency_identity"
    [ "$nk_parse_state" = TRUE ] || return 0
    nk_requirement_state=TRUE nk_requirement_reason=''
    nk_requirement_abi=$nk_canonical_abi
    nk_requirement_version=$nk_version nk_requirement_release=$nk_release
    nk_requirement_vermagic=$nk_vermagic
}

nk_aggregate() {
    nk_compatibility=COMPATIBLE
    [ "$#" -gt 0 ] || nk_compatibility=UNKNOWN
    for nk_predicate in "$@"; do
        case "$nk_predicate" in
            FALSE) nk_compatibility=INCOMPATIBLE ;;
            TRUE) ;;
            *) [ "$nk_compatibility" = INCOMPATIBLE ] || nk_compatibility=UNKNOWN ;;
        esac
    done
}

nk_reason() {
    case " $nk_reasons " in *" $1 "*) return 0 ;; esac
    nk_reasons="${nk_reasons}${nk_reasons:+ }$1"
}

# distribution, running VERSION, installed identity, metadata state,
# exact dependency, supplied platform predicate; remaining args: feed ABI candidates.
# Caller owns structural metadata/platform validation; this is not a JSON reader.
nk_evaluate() {
    nk_distribution=$1 nk_raw_running=$2 nk_raw_installed=$3
    nk_metadata_state=$4 nk_raw_artifact_dependency=$5 nk_platform_predicate=$6
    shift 6
    nk_reasons='' nk_binding=UNDETERMINED nk_feed_predicate=TRUE
    nk_abi_predicate=UNDETERMINED
    nk_router_candidate='' nk_installed_version=''
    nk_installation_eligible=false nk_resolution_eligible=false
    nk_execution_supported=false nk_execution_authorized=false
    nk_active_kernel_evidence=version_consistency_only
    nk_parse_identity "$nk_distribution" "$nk_raw_installed"
    if [ -z "$nk_raw_installed" ]; then
        nk_reason KERNEL_ABI_UNAVAILABLE
        nk_reason ACTIVE_KERNEL_BINDING_UNVERIFIED
    elif [ "$nk_parse_state" != TRUE ]; then
        nk_reason KERNEL_METADATA_FORMAT_UNSUPPORTED
        nk_reason ACTIVE_KERNEL_BINDING_UNVERIFIED
    else
        nk_router_candidate=$nk_canonical_abi nk_installed_version=$nk_version
        if [ -z "$nk_raw_running" ]; then
            nk_reason ACTIVE_KERNEL_BINDING_UNVERIFIED
        elif [ "$nk_raw_running" != "$nk_installed_version" ]; then
            nk_binding=FALSE
            nk_reason KERNEL_VERSION_MISMATCH
            nk_reason ACTIVE_KERNEL_BINDING_MISMATCH
        else nk_binding=TRUE; fi
    fi
    nk_raw_feeds=''
    nk_feed_first='' nk_feed_ambiguous=false nk_feed_invalid=false
    for nk_feed_input in "$@"; do
        nk_raw_feeds="${nk_raw_feeds}${#nk_feed_input}:$nk_feed_input"
        nk_parse_feed "$nk_distribution" "$nk_feed_input"
        if [ "$nk_parse_state" != TRUE ]; then
            nk_feed_invalid=true
        elif [ -z "$nk_feed_first" ]; then nk_feed_first=$nk_canonical_abi
        elif [ "$nk_feed_first" != "$nk_canonical_abi" ]; then nk_feed_ambiguous=true
        fi
    done
    if [ "$nk_feed_ambiguous" = true ]; then
        nk_feed_predicate=UNDETERMINED
        nk_reason AMBIGUOUS_KMOD_FEEDS
    elif [ -n "$nk_feed_first" ] && [ -n "$nk_router_candidate" ] && [ "$nk_feed_first" != "$nk_router_candidate" ]; then
        nk_feed_predicate=FALSE
        nk_reason KERNEL_ABI_MISMATCH
    fi
    if [ "$nk_feed_invalid" = true ]; then
        [ "$nk_feed_predicate" = FALSE ] || nk_feed_predicate=UNDETERMINED
        nk_reason KERNEL_METADATA_FORMAT_UNSUPPORTED
    fi
    nk_parse_requirement "$nk_distribution" "$nk_metadata_state" "$nk_raw_artifact_dependency"
    if [ "$nk_requirement_state" != TRUE ]; then
        nk_reason "$nk_requirement_reason"
    elif [ -n "$nk_router_candidate" ]; then
        if [ "$nk_requirement_abi" = "$nk_router_candidate" ]; then nk_abi_predicate=TRUE
        else
            nk_abi_predicate=FALSE
            nk_reason KERNEL_ABI_MISMATCH
            nk_reason KERNEL_DEPENDENCY_MISMATCH
        fi
    fi
    nk_aggregate "$nk_platform_predicate"
    nk_platform_compatibility=$nk_compatibility
    nk_aggregate "$nk_platform_predicate" "$nk_binding" "$nk_feed_predicate" "$nk_abi_predicate"
    nk_resolution_compatibility=$nk_compatibility
    [ "$nk_compatibility" != COMPATIBLE ] || nk_resolution_eligible=true
    # Version consistency is not proof of the active kernel's full build identity.
    nk_aggregate "$nk_platform_predicate" "$nk_binding" "$nk_feed_predicate" "$nk_abi_predicate" UNDETERMINED
    nk_artifact_compatibility=$nk_compatibility
    nk_reason KERNEL_ABI_UNVERIFIED
    nk_reason ARTIFACT_DIGEST_UNVERIFIED
    nk_reason METADATA_ARTIFACT_BINDING_UNVERIFIED
}
