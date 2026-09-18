"""Fixture-based integration tests: no router, real network or package operations."""
import copy
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

HOME = Path(__file__).resolve().parent.parent
BASE = json.loads((HOME / "tests/fixtures/r5s.json").read_text())
ABI = BASE["kernel_package"]
FEED = "/etc/opkg/distfeeds.conf"


class DoctorTests(unittest.TestCase):
    def run_doctor(self, fixture=None, missing=()):
        fixture = copy.deepcopy(BASE if fixture is None else fixture)
        with tempfile.TemporaryDirectory(prefix="nanowrt-test-") as tmp:
            tmp = Path(tmp)
            root, binary = tmp / "root", tmp / "bin"
            root.mkdir()
            binary.mkdir()
            for path, content in fixture["files"].items():
                target = root / path.lstrip("/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            for cmd in ("cat", "awk", "sort", "dirname"):
                (binary / cmd).symlink_to(shutil.which(cmd))
            mock = "#!" + sys.executable + "\n" + (HOME / "tests/mock_command.py").read_text()
            for cmd in ("uci", "ubus", "opkg", "service", "ifup", "ifdown", "reboot", "sudo", "nft", "curl", "wget", "jsonfilter", "ip", "df", "pidof", "timeout", "ping", "nslookup", "uname", "busybox"):
                if cmd not in missing:
                    target = binary / cmd
                    target.write_text(mock)
                    target.chmod(0o755)
            fixture_path, log_path = tmp / "fixture.json", tmp / "calls.jsonl"
            fixture_path.write_text(json.dumps(fixture))
            env = dict(os.environ, PATH=str(binary), NANOWRT_ROOT=str(root),
                       NW_FIXTURE=str(fixture_path), NW_LOG=str(log_path), LC_ALL="C")
            for key in ('OFFLINE_ROOT', 'OPKG_CONF_DIR', 'NANOWRT_OPKG_CONF', 'NANOWRT_OPKG_CONF_DIR', 'NANOWRT_OPKG_STATUS'):
                env.pop(key, None)
            env.update(fixture.get('env', {}))
            shell = shlex.split(os.environ.get("NW_TEST_SHELL", "/bin/sh"))
            result = subprocess.run([*shell, str(HOME / "nanowrt"), "doctor"], env=env,
                                    capture_output=True, text=True, timeout=30)
            calls = log_path.read_text() if log_path.exists() else ""
            self.assertNotIn('"FORBIDDEN"', calls)
            self.assertNotIn('network.interface.@', calls)
            self.assertEqual(result.stderr, "")
            after = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after, "doctor modified fixture filesystem")
            self.assertNotIn("SECRET_PASSWORD", result.stdout)
            return result

    def test_platform_and_resources(self):
        result = self.run_doctor()
        self.assertEqual(result.returncode, 0)
        for text in ("distribution: ImmortalWrt", "release: 24.10.6", "revision: r33869-cf234f8de6d5",
                     "board_name: friendlyarm,nanopi-r5s", "target: rockchip/armv8",
                     "package architecture: aarch64_generic", "kernel version: 6.6.133",
                     "root filesystem type: squashfs", "overlay: total=100000 KiB free=80000 KiB",
                     "RAM available: 3000000 KiB", "192.168.1.1/24", "default via 10.0.0.1",
                     "PASS | Internet connectivity", "PASS | DNS resolution", "process=sing-box PID=123",
                     "AmneziaWG loaded module: amneziawg"):
            self.assertIn(text, result.stdout)

    def test_abi_extraction(self):
        result = self.run_doctor()
        self.assertIn("feed kernel ABI identifier: " + ABI, result.stdout)
        self.assertIn("https://downloads.immortalwrt.org/releases/24.10.6/targets/rockchip/armv8/kmods/" + ABI, result.stdout)
        self.assertIn("WARN | ABI comparison", result.stdout)
        self.assertIn("No manifest/package artifact verified", result.stdout)

    def test_missing_feed(self):
        fixture = copy.deepcopy(BASE)
        del fixture["files"][FEED]
        result = self.run_doctor(fixture)
        self.assertEqual(result.returncode, 0)
        self.assertIn("No configured kmods feed found; ABI unknown", result.stdout)

    def test_unknown_board(self):
        fixture = copy.deepcopy(BASE)
        fixture["files"]["/tmp/sysinfo/board_name"] = "vendor,unknown"
        result = self.run_doctor(fixture)
        self.assertEqual(result.returncode, 0)
        self.assertIn("WARN | board profile: Unknown board", result.stdout)

    def test_missing_optional_commands(self):
        result = self.run_doctor(missing=("uci", "ubus", "opkg", "service", "ifup", "ifdown", "reboot", "sudo", "nft", "curl", "wget", "jsonfilter", "ip", "df", "pidof", "timeout", "ping", "nslookup"))
        self.assertEqual(result.returncode, 0)
        self.assertIn("ip unavailable", result.stdout)
        self.assertIn("uci unavailable", result.stdout)
        self.assertIn("probe skipped", result.stdout)
        self.assertIn("pidof unavailable", result.stdout)
        self.assertIn("feed kernel ABI identifier: " + ABI, result.stdout)

    def test_r5s_modem(self):
        result = self.run_doctor()
        self.assertIn("AT/control port (unverified): /dev/ttyUSB3", result.stdout)
        self.assertIn("XMM runtime data interface (ubus): eth3", result.stdout)

    def test_r3s_modem(self):
        fixture = copy.deepcopy(BASE)
        r3s = json.loads((HOME / "tests/fixtures/r3s.json").read_text())
        fixture["files"]["/tmp/sysinfo/board_name"] = r3s["board"]
        fixture["files"]["/tmp/sysinfo/model"] = r3s["model"]
        fixture["uci"]["network.cell.device"] = r3s["control"]
        fixture["ubus"]["network.interface.cell"]["l3_device"] = r3s["data"]
        result = self.run_doctor(fixture)
        self.assertIn("AT/control port (unverified): /dev/ttyACM0", result.stdout)
        self.assertIn("XMM runtime data interface (ubus): wwan0", result.stdout)

    def test_modem_not_hardcoded_and_no_secret_output(self):
        fixture = copy.deepcopy(BASE)
        fixture["uci"]["network.cell.device"] = "/dev/customAT7"
        fixture["uci"]["network.cell.password"] = "SECRET_PASSWORD"
        fixture["ubus"]["network.interface.cell"]["l3_device"] = "usbnet9"
        result = self.run_doctor(fixture)
        self.assertIn("/dev/customAT7", result.stdout)
        self.assertIn("XMM runtime data interface (ubus): usbnet9", result.stdout)

    def test_missing_runtime_modem_evidence(self):
        result = self.run_doctor(missing=("ubus", "jsonfilter"))
        self.assertIn("No ubus device evidence", result.stdout)
        self.assertNotIn("XMM runtime data interface (ubus):", result.stdout)

    def test_kernel_abi_mismatch_remains_unverified(self):
        fixture = copy.deepcopy(BASE)
        fixture["files"]["/usr/lib/opkg/status"] = fixture["files"]["/usr/lib/opkg/status"].replace(ABI, "6.6.133-1-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        result = self.run_doctor(fixture)
        self.assertEqual(result.returncode, 0)
        self.assertIn("WARN | ABI comparison: Not verified", result.stdout)

    def test_multiple_feeds_not_selected(self):
        fixture = copy.deepcopy(BASE)
        fixture["files"]["/etc/opkg/customfeeds.conf"] = "src/gz other_kmods https://example.invalid/kmods/6.6.133-1-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        result = self.run_doctor(fixture)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Multiple distinct valid ABI identifiers", result.stdout)
        self.assertNotIn("PASS | ABI comparison", result.stdout)

    def test_generic_feed_does_not_invent_abi(self):
        fixture = copy.deepcopy(BASE)
        fixture["files"][FEED] = "src/gz kmods https://example.invalid/kmods/\n"
        result = self.run_doctor(fixture)
        self.assertIn("No ABI-capable effective feed", result.stdout)

    def test_failed_probes_are_warnings(self):
        fixture = copy.deepcopy(BASE)
        fixture["probe_exit"] = 124
        fixture["routes4"] = ""
        result = self.run_doctor(fixture)
        self.assertEqual(result.returncode, 0)
        self.assertIn("WARN | Internet connectivity", result.stdout)
        self.assertIn("WARN | DNS resolution", result.stdout)

    def test_config_is_never_executed(self):
        fixture = copy.deepcopy(BASE)
        fixture["files"]["/etc/openwrt_release"] += "\nexit 98\nDANGEROUS=$(reboot)\n"
        self.assertEqual(self.run_doctor(fixture).returncode, 0)

    def test_ubus_and_arch_fallback(self):
        fixture = copy.deepcopy(BASE)
        for path in ("/etc/openwrt_release", "/tmp/sysinfo/board_name", "/tmp/sysinfo/model"):
            del fixture["files"][path]
        result = self.run_doctor(fixture)
        self.assertIn("distribution: ImmortalWrt", result.stdout)
        self.assertIn("package architecture: aarch64_generic", result.stdout)
        self.assertIn("board_name: friendlyarm,nanopi-r5s", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
