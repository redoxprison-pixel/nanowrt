"""Strict read-only command doubles. Unknown invocations fail the test harness."""
import json
import os
import sys
from pathlib import Path

name = Path(sys.argv[0]).name
args = sys.argv[1:]
fixture = json.loads(Path(os.environ["NW_FIXTURE"]).read_text())
with open(os.environ["NW_LOG"], "a") as log:
    log.write(json.dumps([name, *args]) + "\n")


def output(value):
    if value is None:
        sys.exit(1)
    if isinstance(value, (dict, list, bool)):
        value = json.dumps(value)
    print(value)
    sys.exit(0)


if name in fixture.get("command_errors", {}):
    sys.exit(fixture["command_errors"][name])

if name == "uci":
    if args == ["-q", "show", "network"]:
        output("\n".join(f"{k}='{v}'" for k, v in fixture["uci"].items()))
    if len(args) == 3 and args[:2] == ["-q", "get"]:
        output(fixture["uci"].get(args[2]))
elif name == "ubus":
    if len(args) == 3 and args[0] == "call" and (
        (args[1] == "system" and args[2] == "board")
        or (args[1].startswith("network.interface.") and args[2] == "status")
    ):
        output(fixture["ubus"].get(args[1]))
elif name == "jsonfilter":
    if len(args) == 2 and args[0] == "-e" and args[1].startswith("@."):
        try:
            value = json.load(sys.stdin)
            for key in args[1][2:].split("."):
                value = value[key]
            output(value)
        except (ValueError, KeyError, TypeError):
            sys.exit(1)
elif name == "ip":
    if args == ["-4", "route", "show", "default"]:
        output(fixture.get("routes4", ""))
    if args == ["-6", "route", "show", "default"]:
        output(fixture.get("routes6", ""))
    if len(args) == 4 and args[:3] == ["addr", "show", "dev"]:
        output(fixture.get("addresses", ""))
elif name == "df":
    if len(args) == 2 and args[0] == "-Pk" and args[1].endswith("/overlay"):
        output("Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/loop0 100000 20000 80000 20% /overlay")
elif name == "pidof":
    if len(args) == 1:
        output(fixture.get("processes", {}).get(args[0]))
elif name == "timeout":
    if args in (["5", "ping", "-c", "1", "-W", "2", "1.1.1.1"], ["5", "nslookup", "openwrt.org"]):
        sys.exit(fixture.get("probe_exit", 0))
elif name == "busybox":
    if args == ["ping", "--help"]:
        output(fixture.get("busybox_ping_help", ""))
    if args == ["ping", "-c", "1", "-W", "2", "-w", "3", "1.1.1.1"]:
        sys.exit(fixture.get("probe_exit", 0))
elif name == "uname" and args == ["-r"]:
    output("fixture-kernel")

with open(os.environ["NW_LOG"], "a") as log:
    log.write(json.dumps(["FORBIDDEN", name, *args]) + "\n")
sys.exit(97)
