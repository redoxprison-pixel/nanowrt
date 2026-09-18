nw_network() {
    printf '\nNETWORK\n'
    nw_lan_json=$(nw_status lan)
    nw_lan_dev=$(printf '%s\n' "$nw_lan_json" | nw_json '@.l3_device')
    if [ -n "$nw_lan_dev" ]; then
        nw_value 'LAN runtime device' "$nw_lan_dev"
    else
        nw_lan_dev=$(nw_uci network.lan.device)
        [ -n "$nw_lan_dev" ] || nw_lan_dev=$(nw_uci network.lan.ifname)
        nw_value 'LAN configured device (not runtime proof)' "$nw_lan_dev"
    fi
    nw_value 'LAN configured address (not runtime proof)' "$(nw_uci network.lan.ipaddr)"
    if nw_has ip; then
        if [ -n "$nw_lan_dev" ]; then
            for nw_dev in $nw_lan_dev; do
                nw_value "LAN addresses $nw_dev" "$(ip addr show dev "$nw_dev" 2>/dev/null | awk '$1 == "inet" || $1 == "inet6" {print $2}')"
            done
        fi
        nw_routes=$(ip -4 route show default 2>/dev/null)
        nw_routes6=$(ip -6 route show default 2>/dev/null)
        nw_value 'IPv4 default route (main table)' "$nw_routes"
        nw_value 'IPv6 default route (main table)' "$nw_routes6"
        nw_value 'default WAN/data devices (main table)' "$(printf '%s\n%s\n' "$nw_routes" "$nw_routes6" | awk '{for(i=1;i<NF;i++) if($i=="dev") print $(i+1)}' | sort -u)"
    else nw_report WARN 'network runtime' 'ip unavailable; routes and addresses unknown'; fi
    # Bound external probes. Do not substitute a persistent helper or change DNS.
    if nw_has timeout && nw_has ping; then
        if timeout 5 ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1; then
            nw_report PASS 'Internet connectivity' 'IPv4 ICMP response from 1.1.1.1 (limited evidence)'
        else nw_report WARN 'Internet connectivity' 'IPv4 ICMP probe failed/blocked; Internet status inconclusive'; fi
    elif nw_busybox_ping_bounded; then
        if busybox ping -c 1 -W 2 -w 3 1.1.1.1 >/dev/null 2>&1; then
            nw_report PASS 'Internet connectivity' 'IPv4 ICMP response from 1.1.1.1 (BusyBox native deadline; limited evidence)'
        else nw_report WARN 'Internet connectivity' 'IPv4 ICMP probe failed/blocked within BusyBox native deadline; Internet status inconclusive'; fi
    else nw_report WARN 'Internet connectivity' 'No verified bounded ping capability; probe skipped'; fi
    if nw_has timeout && nw_has nslookup; then
        if timeout 5 nslookup openwrt.org >/dev/null 2>&1; then nw_report PASS 'DNS resolution' 'openwrt.org resolved using configured resolver'
        else nw_report WARN 'DNS resolution' 'Probe failed or timed out'; fi
    else nw_report WARN 'DNS resolution' 'timeout/nslookup unavailable; no verified native DNS bound; probe skipped'; fi
}

# BusyBox fancy ping advertises its native deadline. Invoke that same applet,
# not an unrelated ping in PATH. A numeric destination avoids resolver blocking.
# The simple ping build or missing/unknown help is deliberately not accepted.
nw_busybox_ping_bounded() {
    nw_has busybox || return 1
    nw_ping_help=$(busybox ping --help 2>&1)
    case "$nw_ping_help" in *BusyBox*) ;; *) return 1 ;; esac
    case "$nw_ping_help" in *'-c CNT'*) ;; *) return 1 ;; esac
    case "$nw_ping_help" in *'-W SEC'*) ;; *) return 1 ;; esac
    case "$nw_ping_help" in *'-w SEC'*) return 0 ;; *) return 1 ;; esac
}
