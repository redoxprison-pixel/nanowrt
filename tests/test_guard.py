"""Conservative source guard, not a shell interpreter or filesystem sandbox.

Checks the explicit doctor graph and known mutators, including nested substitutions.
Dynamic behavior and utility side effects still require review/real validation.
"""
from pathlib import Path
import re
import shlex
import unittest

HOME = Path(__file__).resolve().parent.parent
MODULES = {"common", "inventory", "platform", "packages", "network", "modem"}
BANNED = {"opkg", "service", "ifup", "ifdown", "reboot", "sudo", "nft",
          "curl", "wget", "eval", "exec", "bash", "python", "python3", "perl",
          "jq", "ss", "pgrep", "rm", "mv", "cp", "mkdir", "touch", "tee", "mktemp"}
MUTATORS = {"set", "delete", "commit", "add", "replace", "flush", "del",
            "start", "stop", "restart", "enable", "disable", "import", "batch"}


def violations(source):
    lexer = shlex.shlex(source, posix=True, punctuation_chars="();|&<>")
    lexer.whitespace_split = True
    tokens = list(lexer)
    found = []
    for i, token in enumerate(tokens):
        if token.rsplit("/", 1)[-1] in BANNED:
            found.append("forbidden executable: " + token)
        if token in ("uci", "ip"):
            following = []
            for arg in tokens[i+1:]:
                if arg in (";", "|", "||", "&&", ")"):
                    break
                following.append(arg)
                if len(following) == 6:
                    break
            if MUTATORS.intersection(following):
                found.append("mutating arguments: " + token)
        if token in (">", ">>", ">&"):
            if i+1 == len(tokens) or tokens[i+1] not in ("/dev/null", "1", "2"):
                found.append("filesystem redirection")
        # shlex keeps substitutions inside double quotes in one token.
        for body in re.findall(r"\$\(([^()]*)\)", token):
            found.extend(violations(body))
        if "`" in token:
            found.append("backtick substitution requires explicit review")
    return found


class StaticGuardTests(unittest.TestCase):
    def test_doctor_graph(self):
        entry = (HOME / "nanowrt").read_text()
        modules = re.search(r"for nw_module in ([a-z ]+); do", entry).group(1).split()
        self.assertEqual(set(modules), MODULES)
        self.assertEqual({p.stem for p in (HOME / "lib").glob("*.sh")}, MODULES | {"kernel-identity", "manifest", "resolver"})
        self.assertEqual({p.name for p in (HOME / "lib").glob("*.awk")}, {"status.awk", "opkg-config.awk"})
        for path in [HOME / "nanowrt", *sorted((HOME / "lib").glob("*.sh"))]:
            self.assertEqual(violations(path.read_text()), [], str(path))
        for path in (HOME / "lib").glob("*.awk"):
            code = "\n".join(line for line in path.read_text().splitlines() if not line.lstrip().startswith("#"))
            self.assertNotRegex(code, r"\b(system|getline)\b|\b(print|printf)\b[^\n]*[>|]", str(path))

    def test_mutator_regressions(self):
        commands = ["opkg status kernel", "x=$(opkg list-installed)",
                    'printf "%s" "$(opkg print-architecture)"', "/bin/opkg status kernel",
                    "uci -q set network.x=y", "uci delete network.x", "uci commit",
                    "ifup wan", "ifdown wan", "reboot", "sudo reboot",
                    "nft add table inet x", "nft delete table inet x", "nft flush ruleset",
                    "ip route add default", "ip rule delete pref 1", "ip route replace default",
                    "curl URL | sh", "wget URL | sh", 'printf x > /etc/test']
        commands += ["service network " + action for action in ("start", "stop", "restart", "enable", "disable")]
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(violations(command))


if __name__ == "__main__":
    unittest.main(verbosity=2)
