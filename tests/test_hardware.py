import copy
import json
import unittest
import test_doctor
from test_doctor import BASE, ABI, FEED, HOME

URL = 'https://example.invalid/kmods/' + ABI
HELP = 'BusyBox v1.36.1\nUsage: ping [OPTIONS] HOST\n-c CNT\n-W SEC\n-w SEC\n'


class HardwareRegressions(unittest.TestCase):
    run_doctor = test_doctor.DoctorTests.run_doctor

    def test_first_hardware_observations(self):
        f = json.loads((HOME / 'tests/fixtures/r5s-hardware.json').read_text())
        r = self.run_doctor(f, missing=('timeout',))
        self.assertEqual(r.returncode, 0)
        self.assertIn('selected ABI identity candidate: ' + ABI, r.stdout)
        self.assertIn('additional kmods-like feeds: 1', r.stdout)
        self.assertIn('6.6.133~23375d261da0c0e9da36857794905cf7-r1', r.stdout)
        self.assertIn('WARN | ABI comparison: Not verified', r.stdout)
        self.assertIn('BusyBox native deadline', r.stdout)
        self.assertIn('XMM logical interface: fibocom', r.stdout)
        self.assertIn('Zapret process: running', r.stdout)
        self.assertNotIn('ambiguous', r.stdout)

    def test_same_abi_multiple_sources(self):
        f = copy.deepcopy(BASE)
        f['files'][FEED] = f'src/gz one {URL}\nsrc/gz two https://other.invalid/kmods/{ABI}\n'
        r = self.run_doctor(f)
        self.assertIn('kmods source name: one', r.stdout)
        self.assertIn('kmods source name: two', r.stdout)
        self.assertIn('selected ABI identity candidate: ' + ABI, r.stdout)
        self.assertNotIn('ambiguous', r.stdout)

    def test_different_valid_abis(self):
        f = copy.deepcopy(BASE)
        f['files'][FEED] += 'src/gz other https://example.invalid/kmods/6.6.133-1-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n'
        r = self.run_doctor(f)
        self.assertIn('ambiguous, no identity selected', r.stdout)
        self.assertNotIn('selected ABI identity candidate:', r.stdout)

    def test_candidate_name_and_domain_do_not_select(self):
        f = copy.deepcopy(BASE)
        f['files'][FEED] = f'src/gz arbitrary {URL}\nsrc/gz immortalwrt_kmods https://downloads.immortalwrt.org/packages\n'
        r = self.run_doctor(f)
        self.assertIn('selected ABI identity candidate: ' + ABI, r.stdout)
        self.assertIn('additional kmods-like feeds: 1', r.stdout)

    def test_malformed_identifier_not_abi_capable(self):
        f = copy.deepcopy(BASE)
        f['files'][FEED] = 'src/gz one https://example.invalid/kmods/6.6.133-1-abc\n'
        r = self.run_doctor(f)
        self.assertIn('No ABI-capable effective feed', r.stdout)
        self.assertNotIn('selected ABI identity candidate:', r.stdout)

    def test_modern_metadata_is_not_normalized_to_pass(self):
        f = copy.deepcopy(BASE)
        f['files']['/usr/lib/opkg/status'] = f['files']['/usr/lib/opkg/status'].replace(ABI, '6.6.133~ffffffffffffffffffffffffffffffff-r1')
        r = self.run_doctor(f)
        self.assertIn('WARN | ABI comparison: Not verified', r.stdout)
        self.assertNotIn('PASS | ABI comparison', r.stdout)

    def test_busybox_native_ping_without_timeout_or_ping_symlink(self):
        f = copy.deepcopy(BASE)
        f['busybox_ping_help'] = HELP
        r = self.run_doctor(f, missing=('timeout', 'ping'))
        self.assertIn('PASS | Internet connectivity', r.stdout)
        self.assertIn('BusyBox native deadline', r.stdout)
        self.assertIn('no verified native DNS bound; probe skipped', r.stdout)

    def test_busybox_native_ping_failure_warns(self):
        f = copy.deepcopy(BASE)
        f['busybox_ping_help'] = HELP
        f['probe_exit'] = 1
        r = self.run_doctor(f, missing=('timeout',))
        self.assertEqual(r.returncode, 0)
        self.assertIn('WARN | Internet connectivity', r.stdout)
        self.assertIn('within BusyBox native deadline', r.stdout)

    def test_busybox_without_deadline_skips(self):
        f = copy.deepcopy(BASE)
        f['busybox_ping_help'] = HELP.replace('-w SEC', '')
        r = self.run_doctor(f, missing=('timeout',))
        self.assertIn('No verified bounded ping capability; probe skipped', r.stdout)

    def test_nonbusybox_help_does_not_enable_probe(self):
        f = copy.deepcopy(BASE)
        f['busybox_ping_help'] = HELP.replace('BusyBox v1.36.1', 'Unknown ping')
        r = self.run_doctor(f, missing=('timeout',))
        self.assertIn('No verified bounded ping capability; probe skipped', r.stdout)

    def test_architecture_file(self):
        f = copy.deepcopy(BASE)
        f['files']['/etc/opkg.conf'] = 'dest root /\n'
        f['files']['/etc/opkg/arch.conf'] = (HOME / 'tests/fixtures/opkg-architectures.conf').read_text()
        r = self.run_doctor(f)
        self.assertIn('opkg configured architectures: arch all 1', r.stdout)
        self.assertIn('arch aarch64_generic 10', r.stdout)

    def test_missing_arch_declarations_not_invented(self):
        f = copy.deepcopy(BASE)
        f['files']['/etc/opkg.conf'] = 'dest root /\n'
        r = self.run_doctor(f)
        self.assertIn('package architecture: aarch64_generic', r.stdout)
        self.assertIn('unknown: no readable arch declarations; compiled-in defaults are not queried', r.stdout)

    def test_optional_absence_not_double_warn(self):
        r = self.run_doctor()
        self.assertIn('WARN | Forkop package: absent', r.stdout)
        self.assertIn('INFO | Forkop process: not-running', r.stdout)
        self.assertNotIn('WARN | Forkop process:', r.stdout)
