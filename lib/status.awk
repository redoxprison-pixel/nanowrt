# Parse complete RFC822-like records; discard ALL evidence on malformed input.
# Buffer output until validation finishes, including duplicate package records.
BEGIN { RS=""; FS="\n"; bad=0; records=0; installed=0 }
{
    package=""; version=""; status=""; pc=0; vc=0; sc=0
    records++
    for (i=1; i<=NF; i++) {
        line=$i
        sub(/\r$/, "", line)
        # BusyBox awk can retain the final newline as an empty last field.
        if (i == NF && line == "") continue
        if (line ~ /^[ \t]/) continue
        if (line !~ /^[A-Za-z0-9-]+:/) {bad=1; continue}
        value=line; sub(/^[^:]+:[ \t]*/, "", value)
        if (line ~ /^Package:/) {package=value; pc++}
        if (line ~ /^Version:/) {version=value; vc++}
        if (line ~ /^Status:/) {status=value; sc++}
    }
    if (pc != 1 || sc != 1 || vc > 1 || package !~ /^[A-Za-z0-9][A-Za-z0-9+._-]*$/ || package in seen) bad=1
    seen[package]=1
    n=split(status, state, /[ \t]+/)
    if (n != 3 || state[1] !~ /^(unknown|install|deinstall|purge)$/ || state[3] !~ /^(not-installed|unpacked|half-configured|installed|half-installed|config-files|post-inst-failed|removal-failed)$/) bad=1
    if (state[1] == "install" && state[3] == "installed") {
        if (vc != 1 || version == "" || version ~ /[ \t]/) bad=1
        output[++installed]=package "\t" version
    }
}
END {
    if (bad || !records) exit 1
    for (i=1; i<=installed; i++) print output[i]
}
