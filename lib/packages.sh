nw_abi_from_url() {
    # Identifier must be present verbatim as the sole trailing path segment.
    # Do not derive an ABI from uname or treat a generic kmods URL as identity.
    printf '%s\n' "$1" | awk '
        /^https?:\/\// {
            sub(/[?#].*$/, "")
            sub(/\/$/, "")
            n=split($0,a,"/")
            parts=split(a[n],id,"-")
            if (a[n-1] == "kmods" && parts == 3 && id[1] ~ /^[0-9]+[.][0-9]+[.][0-9]+$/ && id[2] ~ /^[0-9]+$/ && length(id[3]) == 32 && id[3] ~ /^[a-fA-F0-9]+$/) print a[n]
        }'
}
# nw_config and nw_packages are initialized by nw_inventory in the entrypoint.
# shellcheck disable=SC2154
nw_kernel_abi() {
    printf '\nKERNEL PACKAGE ABI\n'
    nw_feeds=$(printf '%s\n' "$nw_config" | awk -F '\t' '$1 == "src" && ($2 ~ /kmods/ || $3 ~ /\/kmods\//) {print $2 "\t" $3}')
    nw_abi='' nw_abis='' nw_nonabi=0
    if [ -z "$nw_feeds" ]; then
        nw_report WARN 'kmods feed' 'No configured kmods feed found; ABI unknown'
    else
        while IFS="$(printf '\t')" read -r nw_source nw_url; do
            nw_value 'kmods source name' "$nw_source"
            nw_value 'kmods feed URL' "$nw_url"
            nw_feed_abi=$(nw_abi_from_url "$nw_url")
            if [ -n "$nw_feed_abi" ]; then
                nw_value 'feed kernel ABI identifier' "$nw_feed_abi"
                nw_abis="$nw_abis
$nw_feed_abi"
            else
                nw_nonabi=$((nw_nonabi + 1))
                nw_report INFO 'feed classification' 'kmods-like candidate; no extractable exact ABI'
            fi
        done <<EOF
$nw_feeds
EOF
        nw_unique=$(printf '%s\n' "$nw_abis" | awk 'NF && !seen[$0]++ {print}')
        nw_count=$(printf '%s\n' "$nw_unique" | awk 'NF {n++} END {print n+0}')
        case "$nw_count" in
            0) nw_report WARN 'kernel ABI' 'No ABI-capable effective feed; identity unknown' ;;
            1)
                nw_abi=$nw_unique
                nw_value 'selected ABI identity candidate' "$nw_abi"
                nw_report INFO 'ABI selection' 'All ABI-capable feeds agree; source trust and package compatibility are not verified' ;;
            *) nw_report WARN 'kernel ABI' 'Multiple distinct valid ABI identifiers; ambiguous, no identity selected' ;;
        esac
        if [ "$nw_nonabi" -gt 0 ]; then
            nw_report INFO 'additional kmods-like feeds' "$nw_nonabi without extractable ABI; excluded from ABI identity selection"
        fi
    fi
    nw_installed_kernel=$(printf '%s\n' "$nw_packages" | awk -F '\t' '$1 == "kernel" {print $2}')
    nw_value 'installed kernel package version' "$nw_installed_kernel"
    if [ -n "$nw_abi" ] && [ -n "$nw_installed_kernel" ]; then
        nw_report WARN 'ABI comparison' 'Not verified: feed ABI and installed package version are separate observations; metadata format mapping is not implemented'
    else nw_report WARN 'ABI comparison' 'Cannot establish feed/installed-kernel equality'; fi
    nw_report WARN 'compatibility invariant' 'No manifest/package artifact verified in milestone 0.1; kernel version or feed equality alone is insufficient'
}

nw_components() {
    printf '\nCOMPONENT DETECTION\n'
    nw_component Zapret 'zapret' 'nfqws tpws zapret'
    nw_component Forkop 'forkop' 'forkop'
    nw_component 'sing-box / sing-box-extended' 'sing-box sing-box-extended' 'sing-box sing-box-extended'
    nw_component AmneziaWG 'amneziawg-tools kmod-amneziawg' 'awg'
    nw_component mwan3 'mwan3' 'mwan3track'
    nw_loaded=$(nw_file /proc/modules | awk '$1 ~ /^amneziawg/ {print $1}')
    nw_value 'AmneziaWG loaded module' "$nw_loaded"
}
# Shared inventory globals are initialized before component detection.
# shellcheck disable=SC2154
nw_component() {
    nw_label=$1 nw_names=$2 nw_procs=$3
    nw_found='' nw_presence=''
    for nw_name in $nw_names; do
        nw_match=$(printf '%s\n' "$nw_packages" | awk -F '\t' -v p="$nw_name" '$1 == p {print $1 "=" $2}')
        [ -z "$nw_match" ] || nw_found="$nw_found $nw_match;"
        if [ -f "$NW_ROOT/etc/init.d/$nw_name" ]; then nw_presence="$nw_presence init-script=$nw_name;"; fi
    done
    if [ "$nw_pkg_known" != yes ]; then
        nw_report WARN "$nw_label package" unknown
    elif [ -n "$nw_found" ]; then
        nw_report PASS "$nw_label package" "installed;$nw_found"
    else nw_report WARN "$nw_label package" 'absent (optional)'; fi
    for nw_proc in $nw_procs; do
        if nw_has "$nw_proc"; then nw_presence="$nw_presence binary=$nw_proc;"; fi
    done
    if [ -n "$nw_presence" ]; then nw_report PASS "$nw_label files" "$nw_presence (presence only)"; fi
    nw_process_level=WARN
    if [ "$nw_pkg_known" = yes ] && [ -z "$nw_found$nw_presence" ]; then nw_process_level=INFO; fi
    nw_running='' nw_process_error=no
    if nw_has pidof; then
        for nw_proc in $nw_procs; do
            nw_pids=$(pidof "$nw_proc" 2>/dev/null)
            nw_pid_rc=$?
            case "$nw_pid_rc:$nw_pids" in
                0:*)
                    case "$nw_pids" in
                        ''|*[!0-9\ ]*) nw_process_error=yes ;;
                        *) nw_running="$nw_running process=$nw_proc PID=$nw_pids;" ;;
                    esac ;;
                1:) ;; # pidof's documented no-match status
                *) nw_process_error=yes ;;
            esac
        done
        if [ -n "$nw_running" ]; then nw_report PASS "$nw_label process" "running;$nw_running"
        elif [ "$nw_process_error" = yes ]; then nw_report "$nw_process_level" "$nw_label process" 'unavailable (pidof error)'
        else nw_report "$nw_process_level" "$nw_label process" 'not-running (no matching visible PID)'; fi
    else nw_report "$nw_process_level" "$nw_label process" 'unavailable (pidof unavailable)'; fi
}
