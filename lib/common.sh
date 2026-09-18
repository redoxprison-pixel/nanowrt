# POSIX shell helpers. Configuration is data: never source/eval device files.
nw_has() { command -v "$1" >/dev/null 2>&1; }
nw_report() {
    printf '%s | %s: %s\n' "$1" "$2" "$3"
    case "$1" in WARN) nw_warn=$((nw_warn + 1)) ;; FAIL) nw_fail=$((nw_fail + 1)) ;; esac
}
nw_value() {
    if [ -n "$2" ]; then nw_report PASS "$1" "$2"; else nw_report WARN "$1" unknown; fi
}
nw_file() { [ -r "$NW_ROOT$1" ] && cat "$NW_ROOT$1"; }
nw_kv() {
    awk -v key="$1" '
        index($0, key "=") == 1 {
            v = substr($0, length(key) + 2)
            q = sprintf("%c", 39)
            if ((substr(v,1,1) == q && substr(v,length(v),1) == q) ||
                (substr(v,1,1) == "\"" && substr(v,length(v),1) == "\""))
                v = substr(v,2,length(v)-2)
            print v; exit
        }'
}
nw_json() {
    nw_has jsonfilter || return 1
    jsonfilter -e "$1" 2>/dev/null
}
nw_uci() {
    nw_has uci || return 1
    uci -q get "$1" 2>/dev/null
}
nw_status() {
    nw_has ubus || return 1
    ubus call "network.interface.$1" status 2>/dev/null
}
nw_compare_evidence() {
    if [ -n "$2" ] && [ -n "$3" ] && [ "$2" != "$3" ]; then
        nw_report WARN "$1 evidence conflict" "primary=$2; secondary=$3"
    fi
}
