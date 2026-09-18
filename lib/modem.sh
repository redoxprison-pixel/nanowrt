nw_modem() {
    printf '\nMODEM\n'
    if ! nw_has uci; then nw_report WARN 'XMM detection' 'uci unavailable'; return; fi
    # Read only proto fields, never print full UCI configuration (may contain secrets).
    if ! nw_network_config=$(uci -q show network 2>/dev/null); then
        nw_report WARN 'XMM detection' 'uci read failed; configuration unknown'
        return
    fi
    nw_xmm=$(printf '%s\n' "$nw_network_config" | awk '
        /^network\.[^.]+\.proto=/ {
            line=$0; sub(/^[^=]*=/,"",line); gsub(/[\047\042]/,"",line)
            if (tolower(line) == "xmm") {split($0,a,"."); print a[2]}
        }')
    if [ -z "$nw_xmm" ]; then nw_report WARN XMM 'No configured XMM UCI interface found'; return; fi
    for nw_iface in $nw_xmm; do
        nw_value 'XMM UCI selector' "$nw_iface"
        nw_logical=''
        case "$nw_iface" in
            @*)
                nw_report WARN 'XMM section identity' 'anonymous selector; canonical identity not established'
                nw_report WARN 'XMM logical interface' 'unknown; no unambiguous netifd mapping'
                ;;
            *[!a-zA-Z0-9_]*|'')
                nw_report WARN 'XMM section identity' 'invalid section name; skipped'
                continue ;;
            *)
                nw_logical=$nw_iface
                nw_value 'XMM section identity' "$nw_iface"
                nw_value 'XMM logical interface' "$nw_logical" ;;
        esac
        nw_port=$(nw_uci "network.$nw_iface.device")
        [ -n "$nw_port" ] || nw_port=$(nw_uci "network.$nw_iface.control")
        [ -n "$nw_port" ] || nw_port=$(nw_uci "network.$nw_iface.at_port")
        nw_value 'configured AT/control port (unverified)' "$nw_port"
        nw_modem_json=''
        if [ -n "$nw_logical" ]; then nw_modem_json=$(nw_status "$nw_logical"); fi
        nw_up=$(printf '%s\n' "$nw_modem_json" | nw_json '@.up')
        case "$nw_up" in
            true) nw_report PASS 'XMM runtime up' true ;;
            false) nw_report WARN 'XMM runtime up' 'false (optional interface down)' ;;
            *) nw_report WARN 'XMM runtime up' unknown ;;
        esac
        nw_data=$(printf '%s\n' "$nw_modem_json" | nw_json '@.l3_device')
        [ -n "$nw_data" ] || nw_data=$(printf '%s\n' "$nw_modem_json" | nw_json '@.device')
        if [ -n "$nw_data" ]; then
            nw_value 'XMM runtime data interface (ubus)' "$nw_data"
        else
            nw_config_data=$(nw_uci "network.$nw_iface.ifname")
            nw_value 'XMM configured data interface (not runtime proof)' "$nw_config_data"
            nw_report WARN 'XMM runtime data interface' 'No ubus device evidence; no interface guessed from board or default route'
        fi
    done
}
