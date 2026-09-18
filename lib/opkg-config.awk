# Read-only subset of opkg configuration. Fields may be double quoted.
# First source name wins across src and src/gz BEFORE kmods filtering.
# No shell expansion, escapes or eval. Unknown directives are ignored.
function fields(line, out,    n, c, value, end) {
    n=0
    while (1) {
        sub(/^[ \t\r]+/, "", line)
        if (line == "") return n
        if (substr(line,1,1) == "\"") {
            line=substr(line,2)
            end=index(line,"\"")
            if (!end) return -1
            value=substr(line,1,end-1)
            line=substr(line,end+1)
            if (line != "" && line !~ /^[ \t\r]/) return -1
        } else {
            value=line
            sub(/[ \t\r].*$/, "", value)
            line=substr(line,length(value)+1)
        }
        if (value ~ /[\t\r\n]/) return -1
        out[++n]=value
    }
}
/^[ \t\r]*(#|$)/ {next}
{
    count=fields($0, f)
    # opkg accepts one optional fourth field; more trailing fields are ignored lines.
    if (count < 3 || count > 4 || f[2] == "" || f[3] == "") next
    # Unlike the first three fields, opkg's optional fourth field is not quoted.
    if (count == 4 && f[4] ~ /[ \t]/) next
    if (f[1] == "src" || f[1] == "src/gz") {
        if (!(f[2] in source)) {
            source[f[2]]=1
            print "src\t" f[2] "\t" f[3]
        }
    } else if (f[1] == "arch" && f[3] ~ /^[0-9]+$/) {
        print "arch\t" f[2] "\t" f[3]
    } else if (f[1] == "option" && f[2] == "offline_root") {
        print "option\t" f[2] "\t" f[3]
    }
}
