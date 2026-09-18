# All package data paths are centralized here. Overrides are paths inside NW_ROOT.
nw_inventory() {
    NW_OPKG_CONF=${NANOWRT_OPKG_CONF:-/etc/opkg.conf}
    NW_OPKG_CONF_DIR=${NANOWRT_OPKG_CONF_DIR:-${OPKG_CONF_DIR:-/etc/opkg}}
    NW_OPKG_STATUS=${NANOWRT_OPKG_STATUS:-/usr/lib/opkg/status}
    for nw_path in "$NW_OPKG_CONF" "$NW_OPKG_CONF_DIR" "$NW_OPKG_STATUS"; do
        case "$nw_path" in /*) ;; *) printf '%s\n' 'Package data paths must be absolute' >&2; exit 2 ;; esac
    done
    printf '\nPACKAGE DATA SOURCES\n'
    if ! nw_config=$(nw_config_read); then
        nw_config=''
        nw_report WARN 'package config' 'read failed; effective feeds and architectures unknown'
    fi
    nw_value 'package config file' "$NW_OPKG_CONF"
    nw_value 'package config directory' "$NW_OPKG_CONF_DIR"
    nw_value 'package status database' "$NW_OPKG_STATUS"
    # Alternate installation roots require explicit interpretation. Never mix identities.
    nw_other_root=$(printf '%s\n' "$nw_config" | awk -F '\t' '$1 == "option" && $2 == "offline_root" {print $3}')
    if [ -n "${OFFLINE_ROOT:-}$nw_other_root" ]; then
        nw_report WARN 'package config' 'offline_root is unsupported; package evidence ignored'
        nw_config=''
    fi
    nw_pkg_known=no nw_packages=''
    if [ -z "${OFFLINE_ROOT:-}$nw_other_root" ] && [ -r "$NW_ROOT$NW_OPKG_STATUS" ]; then
        if nw_packages=$(awk -f "$NW_HOME/lib/status.awk" "$NW_ROOT$NW_OPKG_STATUS" 2>/dev/null); then
            nw_pkg_known=yes
        else nw_packages=''; fi
    fi
    if [ "$nw_pkg_known" = yes ]; then nw_report PASS 'package inventory' 'read from status database'
    else nw_report WARN 'package inventory' 'unknown (missing, unreadable, malformed or unsupported status database)'; fi
}

nw_config_read() (
    # Enable expansion only for the known config-directory pattern in this subshell.
    LC_ALL=C
    export LC_ALL
    set +f
    set --
    nw_main_seen=''
    for nw_conf in "$NW_ROOT$NW_OPKG_CONF" "$NW_ROOT$NW_OPKG_CONF_DIR"/*.conf; do
        [ -f "$nw_conf" ] || continue
        [ -r "$nw_conf" ] || return 1
        if [ "$nw_conf" = "$nw_main_seen" ]; then continue; fi
        [ -n "$nw_main_seen" ] || nw_main_seen=$nw_conf
        set -- "$@" "$nw_conf"
    done
    [ "$#" -gt 0 ] || return 0
    awk -f "$NW_HOME/lib/opkg-config.awk" "$@" 2>/dev/null
)
