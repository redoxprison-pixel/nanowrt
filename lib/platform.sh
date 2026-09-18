nw_platform() {
    printf '\nSYSTEM\n'
    nw_release_data=$(nw_file /etc/openwrt_release)
    nw_os_data=$(nw_file /etc/os-release)
    nw_board_json=''
    if nw_has ubus; then nw_board_json=$(ubus call system board 2>/dev/null); fi
    nw_distribution=$(printf '%s\n' "$nw_release_data" | nw_kv DISTRIB_ID)
    [ -n "$nw_distribution" ] || nw_distribution=$(printf '%s\n' "$nw_board_json" | nw_json '@.release.distribution')
    [ -n "$nw_distribution" ] || nw_distribution=$(printf '%s\n' "$nw_os_data" | nw_kv NAME)
    nw_release=$(printf '%s\n' "$nw_release_data" | nw_kv DISTRIB_RELEASE)
    [ -n "$nw_release" ] || nw_release=$(printf '%s\n' "$nw_board_json" | nw_json '@.release.version')
    nw_revision=$(printf '%s\n' "$nw_release_data" | nw_kv DISTRIB_REVISION)
    [ -n "$nw_revision" ] || nw_revision=$(printf '%s\n' "$nw_board_json" | nw_json '@.release.revision')
    nw_target=$(printf '%s\n' "$nw_release_data" | nw_kv DISTRIB_TARGET)
    [ -n "$nw_target" ] || nw_target=$(printf '%s\n' "$nw_board_json" | nw_json '@.release.target')
    nw_arch=$(printf '%s\n' "$nw_release_data" | nw_kv DISTRIB_ARCH)
    # nw_config is initialized by nw_inventory before platform detection.
    # shellcheck disable=SC2154
    nw_arches=$(printf '%s\n' "$nw_config" | awk -F '\t' '$1 == "arch" {print "arch " $2 " " $3}')
    if [ -z "$nw_arch" ]; then
        nw_candidates=$(printf '%s\n' "$nw_arches" | awk '$1 == "arch" && $2 != "all" && $2 != "noarch" {print $2}' | sort -u)
        if [ "$(printf '%s\n' "$nw_candidates" | awk 'NF {n++} END {print n+0}')" -eq 1 ]; then nw_arch=$nw_candidates; fi
    fi
    nw_board=$(nw_file /tmp/sysinfo/board_name)
    [ -n "$nw_board" ] || nw_board=$(printf '%s\n' "$nw_board_json" | nw_json '@.board_name')
    nw_model=$(nw_file /tmp/sysinfo/model)
    [ -n "$nw_model" ] || nw_model=$(printf '%s\n' "$nw_board_json" | nw_json '@.model')
    nw_kernel=$(nw_file /proc/sys/kernel/osrelease)
    if [ -z "$nw_kernel" ] && nw_has uname; then nw_kernel=$(uname -r); fi
    nw_value distribution "$nw_distribution"
    nw_value release "$nw_release"
    nw_value revision "$nw_revision"
    nw_value model "$nw_model"
    nw_value board_name "$nw_board"
    nw_value target "$nw_target"
    nw_value 'package architecture' "$nw_arch"
    if [ -n "$nw_arches" ]; then nw_value 'opkg configured architectures' "$nw_arches"
    else nw_report WARN 'opkg configured architectures' 'unknown: no readable arch declarations; compiled-in defaults are not queried'; fi
    nw_value 'kernel version' "$nw_kernel"
    nw_compare_evidence distribution "$nw_distribution" "$(printf '%s\n' "$nw_board_json" | nw_json '@.release.distribution')"
    nw_compare_evidence release "$nw_release" "$(printf '%s\n' "$nw_board_json" | nw_json '@.release.version')"
    nw_compare_evidence revision "$nw_revision" "$(printf '%s\n' "$nw_board_json" | nw_json '@.release.revision')"
    nw_compare_evidence target "$nw_target" "$(printf '%s\n' "$nw_board_json" | nw_json '@.release.target')"
    nw_compare_evidence board "$nw_board" "$(printf '%s\n' "$nw_board_json" | nw_json '@.board_name')"
    nw_compare_evidence kernel "$nw_kernel" "$(printf '%s\n' "$nw_board_json" | nw_json '@.kernel')"
    if [ -n "$nw_arch" ] && [ -n "$nw_arches" ]; then
        if ! printf '%s\n' "$nw_arches" | awk -v arch="$nw_arch" '$2 == arch {found=1} END {exit !found}'; then
            nw_report WARN 'arch evidence conflict' 'Release architecture is absent from configured architecture declarations'
        fi
    fi
    case "$nw_distribution" in
        OpenWrt|ImmortalWrt|'') ;;
        *) nw_report FAIL platform 'Not identified as OpenWrt/ImmortalWrt; unsupported runtime' ;;
    esac
    case "$nw_board" in
        friendlyarm,nanopi-r5s) nw_profile=friendlyarm_nanopi-r5s.conf ;;
        friendlyarm,nanopi-r3s) nw_profile=friendlyarm_nanopi-r3s.conf ;;
        *) nw_profile='' ;;
    esac
    if [ -n "$nw_profile" ]; then
        nw_report PASS 'board profile' "$nw_profile (identification only, no compatibility certification)"
    else
        nw_report WARN 'board profile' 'Unknown board; generic read-only detection only'
    fi
}

nw_resources() {
    printf '\nRESOURCES\n'
    nw_mounts=$(nw_file /proc/mounts)
    nw_value 'root filesystem type' "$(printf '%s\n' "$nw_mounts" | awk '$2 == "/" {print $3; exit}')"
    if printf '%s\n' "$nw_mounts" | awk '$2 == "/overlay" {found=1} END {exit !found}'; then
        if nw_has df; then
            nw_disk=$(df -Pk "$NW_ROOT/overlay" 2>/dev/null | awk 'NR > 1 && NF >= 6 {print "total=" $2 " KiB free=" $4 " KiB"; exit}')
            nw_value overlay "$nw_disk"
        else nw_report WARN overlay 'df unavailable'; fi
    else nw_report WARN overlay 'No separate /overlay mount detected'; fi
    nw_mem=$(nw_file /proc/meminfo)
    nw_value 'RAM total' "$(printf '%s\n' "$nw_mem" | awk '$1 == "MemTotal:" {print $2 " KiB"}')"
    nw_value 'RAM available' "$(printf '%s\n' "$nw_mem" | awk '$1 == "MemAvailable:" {print $2 " KiB"}')"
}
