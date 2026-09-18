import copy
import json
import unittest
import subprocess
from test_doctor import BASE, ABI, FEED, HOME
import test_doctor

STATUS = '/usr/lib/opkg/status'
URL = 'https://example.invalid/kmods/' + ABI


class EdgeTests(unittest.TestCase):
    run_doctor = test_doctor.DoctorTests.run_doctor

    def test_duplicate_ordinary_then_kmods(self):
        f = copy.deepcopy(BASE)
        f['files'][FEED] = f'src/gz same https://example.invalid/packages\nsrc/gz same {URL}\n'
        r = self.run_doctor(f)
        self.assertIn('No configured kmods feed found', r.stdout)
        self.assertNotIn('PASS | ABI comparison', r.stdout)

    def test_duplicate_kmods_then_ordinary(self):
        f = copy.deepcopy(BASE)
        f['files'][FEED] = f'src/gz same {URL}\nsrc same https://example.invalid/packages\n'
        r = self.run_doctor(f)
        self.assertIn('kmods source name: same', r.stdout)
        self.assertIn('WARN | ABI comparison', r.stdout)

    def test_duplicate_across_config_files(self):
        f = copy.deepcopy(BASE)
        f['files']['/etc/opkg.conf'] += 'src/gz immortalwrt_kmods https://example.invalid/packages\n'
        r = self.run_doctor(f)
        self.assertIn('kmods feed URL: https://example.invalid/packages', r.stdout)
        self.assertNotIn('PASS | feed kernel ABI identifier', r.stdout)
        self.assertNotIn('PASS | ABI comparison', r.stdout)

    def test_unquoted_feed(self):
        self.check_feed(f'src/gz name {URL}\n')

    def test_quoted_url(self):
        self.check_feed(f'src/gz name "{URL}"\n')

    def test_quoted_name_and_url(self):
        self.check_feed(f'src/gz "source name" "{URL}"\n', 'source name')

    def check_feed(self, line, name='name'):
        f = copy.deepcopy(BASE)
        f['files'][FEED] = line
        r = self.run_doctor(f)
        self.assertIn('kmods source name: ' + name, r.stdout)
        self.assertIn('feed kernel ABI identifier: ' + ABI, r.stdout)
        self.assertIn('WARN | ABI comparison', r.stdout)

    def test_anonymous_xmm(self):
        f = copy.deepcopy(BASE)
        f['uci'] = {k.replace('network.cell.', 'network.@interface[0].'): v for k, v in f['uci'].items()}
        r = self.run_doctor(f)
        self.assertIn('XMM UCI selector: @interface[0]', r.stdout)
        self.assertIn('AT/control port (unverified): /dev/ttyUSB3', r.stdout)
        self.assertIn('XMM logical interface: unknown', r.stdout)
        self.assertNotIn('XMM runtime data interface (ubus):', r.stdout)

    def test_multiple_xmm(self):
        f = copy.deepcopy(BASE)
        f['uci'].update({'network.second.proto': 'xmm', 'network.second.control': '/dev/custom9'})
        f['ubus']['network.interface.second'] = {'l3_device': 'usbnet9', 'up': True}
        r = self.run_doctor(f)
        self.assertIn('XMM logical interface: cell', r.stdout)
        self.assertIn('XMM logical interface: second', r.stdout)
        self.assertIn('AT/control port (unverified): /dev/custom9', r.stdout)
        self.assertIn('XMM runtime data interface (ubus): usbnet9', r.stdout)

    def test_xmm_down(self):
        f = copy.deepcopy(BASE)
        f['ubus']['network.interface.cell']['up'] = False
        r = self.run_doctor(f)
        self.assertEqual(r.returncode, 0)
        self.assertIn('WARN | XMM runtime up: false', r.stdout)

    def test_missing_ubus_object(self):
        f = copy.deepcopy(BASE)
        del f['ubus']['network.interface.cell']
        r = self.run_doctor(f)
        self.assertIn('No ubus device evidence', r.stdout)
        self.assertNotIn('XMM runtime data interface (ubus):', r.stdout)

    def test_existing_commands_fail(self):
        f = copy.deepcopy(BASE)
        f['command_errors'] = {k: 2 for k in ['uci', 'ubus', 'jsonfilter', 'ip', 'df', 'pidof']}
        r = self.run_doctor(f)
        self.assertEqual(r.returncode, 0)
        self.assertIn('uci read failed', r.stdout)
        self.assertIn('unavailable (pidof error)', r.stdout)
        self.assertNotIn('XMM runtime data interface (ubus):', r.stdout)

    def test_no_ipv4_default(self):
        f = copy.deepcopy(BASE)
        f['routes4'] = ''
        r = self.run_doctor(f)
        self.assertEqual(r.returncode, 0)
        self.assertIn('WARN | IPv4 default route', r.stdout)

    def test_no_default_routes(self):
        f = copy.deepcopy(BASE)
        f['routes4'] = f['routes6'] = ''
        r = self.run_doctor(f)
        self.assertEqual(r.returncode, 0)
        self.assertIn('WARN | IPv4 default route', r.stdout)
        self.assertIn('WARN | IPv6 default route', r.stdout)
        self.assertIn('WARN | default WAN/data devices', r.stdout)

    def test_ipv6_only(self):
        f = copy.deepcopy(BASE)
        f['routes4'] = ''
        f['addresses'] = '    inet6 fd00::1/64 scope global\n'
        f['probe_exit'] = 1
        r = self.run_doctor(f)
        self.assertEqual(r.returncode, 0)
        self.assertIn('PASS | IPv6 default route', r.stdout)
        self.assertIn('IPv4 ICMP probe failed/blocked', r.stdout)

    def test_missing_status(self):
        f = copy.deepcopy(BASE)
        del f['files'][STATUS]
        r = self.run_doctor(f)
        self.assertIn('sing-box / sing-box-extended package: unknown', r.stdout)
        self.assertIn('Cannot establish feed/installed-kernel equality', r.stdout)

    def test_malformed_status(self):
        f = copy.deepcopy(BASE)
        f['files'][STATUS] += 'Package: broken\nStatus: nonsense\n\n'
        r = self.run_doctor(f)
        self.assertIn('package inventory: unknown', r.stdout)
        self.assertNotIn('PASS | ABI comparison', r.stdout)

    def test_not_installed_record(self):
        f = copy.deepcopy(BASE)
        f['files'][STATUS] = f['files'][STATUS].replace('Package: sing-box-extended\nVersion: 1.0\nStatus: install ok installed', 'Package: sing-box-extended\nVersion: 1.0\nStatus: deinstall ok config-files')
        r = self.run_doctor(f)
        self.assertIn('sing-box / sing-box-extended package: absent', r.stdout)
        self.assertIn('sing-box / sing-box-extended process: running', r.stdout)

    def test_installed_package_stopped(self):
        f = copy.deepcopy(BASE)
        f['processes'] = {}
        r = self.run_doctor(f)
        self.assertEqual(r.returncode, 0)
        self.assertIn('sing-box / sing-box-extended package: installed', r.stdout)
        self.assertIn('sing-box / sing-box-extended process: not-running', r.stdout)

    def test_init_script_does_not_imply_installed_package(self):
        f = copy.deepcopy(BASE)
        f['files']['/etc/init.d/zapret'] = 'never execute this file\n'
        r = self.run_doctor(f)
        self.assertIn('Zapret package: absent', r.stdout)
        self.assertIn('Zapret files:  init-script=zapret;', r.stdout)

    def test_empty_status(self):
        f = copy.deepcopy(BASE)
        f['files'][STATUS] = ''
        self.assertIn('package inventory: unknown', self.run_doctor(f).stdout)

    def test_duplicate_status_record(self):
        f = copy.deepcopy(BASE)
        f['files'][STATUS] *= 2
        self.assertIn('package inventory: unknown', self.run_doctor(f).stdout)

    def test_status_name_in_description_is_not_package(self):
        f = copy.deepcopy(BASE)
        f['files'][STATUS] = f'Package: kernel\nVersion: {ABI}\nStatus: install hold installed\nDescription: sing-box\n sing-box-extended\n'
        r = self.run_doctor(f)
        self.assertIn('WARN | ABI comparison', r.stdout)
        self.assertIn('sing-box / sing-box-extended package: absent', r.stdout)

    def test_json_sources_parse(self):
        for path in [HOME / 'manifests/schema.json', *sorted((HOME / 'tests/fixtures').glob('*.json'))]:
            self.assertIsInstance(json.loads(path.read_text()), dict)

    def test_data_path_overrides(self):
        f = copy.deepcopy(BASE)
        f['files']['/custom/main.conf'] = f['files'].pop('/etc/opkg.conf')
        f['files']['/custom/feeds/feed.conf'] = f['files'].pop(FEED)
        f['files']['/custom/status'] = f['files'].pop(STATUS)
        f['env'] = {'NANOWRT_OPKG_CONF': '/custom/main.conf', 'NANOWRT_OPKG_CONF_DIR': '/custom/feeds', 'NANOWRT_OPKG_STATUS': '/custom/status'}
        r = self.run_doctor(f)
        self.assertIn('WARN | ABI comparison', r.stdout)
        self.assertIn('package status database: /custom/status', r.stdout)

    def test_offline_root_not_mixed(self):
        f = copy.deepcopy(BASE)
        f['files']['/etc/opkg.conf'] += 'option offline_root /other-root\n'
        r = self.run_doctor(f)
        self.assertIn('offline_root is unsupported', r.stdout)
        self.assertNotIn('PASS | ABI comparison', r.stdout)

    def test_malformed_quoted_feed_is_ignored(self):
        f = copy.deepcopy(BASE)
        f['files'][FEED] = f'src/gz kmods "{URL}\n'
        r = self.run_doctor(f)
        self.assertIn('No configured kmods feed found', r.stdout)

    def test_invalid_fourth_field_does_not_shadow_source(self):
        data = f'src/gz same https://example.invalid/packages "trailing garbage"\nsrc/gz same {URL}\n'
        r = subprocess.run(['awk', '-f', str(HOME / 'lib/opkg-config.awk')], input=data, text=True, capture_output=True, check=True)
        self.assertEqual(r.stdout, 'src\tsame\t' + URL + '\n')


def identity_case(field, key, changed):
    def test(self):
        f = copy.deepcopy(BASE)
        if key:
            lines = f['files']['/etc/openwrt_release'].splitlines()
            f['files']['/etc/openwrt_release'] = '\n'.join(f"{key}='{changed}'" if line.startswith(key+'=') else line for line in lines) + '\n'
        else:
            path = '/proc/sys/kernel/osrelease' if field == 'kernel' else '/tmp/sysinfo/board_name'
            f['files'][path] = changed + '\n'
        r = self.run_doctor(f)
        self.assertEqual(r.returncode, 0)
        self.assertIn(changed, r.stdout)
        self.assertIn('WARN | ' + field + ' evidence conflict', r.stdout)
        self.assertIn('feed kernel ABI identifier: ' + ABI, r.stdout)
        self.assertIn('No manifest/package artifact verified', r.stdout)
    return test


for field, key, value in [
    ('distribution', 'DISTRIB_ID', 'OpenWrt'),
    ('release', 'DISTRIB_RELEASE', '24.10.5'),
    ('revision', 'DISTRIB_REVISION', 'r00000-other'),
    ('target', 'DISTRIB_TARGET', 'other/target'),
    ('arch', 'DISTRIB_ARCH', 'other_arch'),
    ('kernel', None, '6.6.132'),
    ('board', None, 'vendor,other'),
]:
    setattr(EdgeTests, 'test_independent_' + field, identity_case(field, key, value))
