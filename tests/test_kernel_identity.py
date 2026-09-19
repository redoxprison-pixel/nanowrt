"""Offline contracts: arguments are never interpolated into shell source."""
import itertools
import json
import os
from pathlib import Path
import shlex
import subprocess
import unittest

HOME = Path(__file__).resolve().parent.parent
HASH = '23375d261da0c0e9da36857794905cf7'
PKG = '6.6.133~' + HASH + '-r1'
ABI = '6.6.133-1-' + HASH


class KernelIdentityTests(unittest.TestCase):
    def call(self, function, args, fields):
        script = '. "$1/lib/kernel-identity.sh"; shift; ' + function + ' "$@"; '
        script += '; '.join('printf "%s\\n" "$' + field + '"' for field in fields)
        result = subprocess.run([*shlex.split(os.environ.get('NW_TEST_SHELL', '/bin/sh')),
                                 '-c', script, 'contract', str(HOME), *args],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout.splitlines()

    def evaluate(self, running='6.6.133', installed=PKG, metadata='valid',
                 dependency=None, feeds=(), platform='TRUE'):
        return self.call('nk_evaluate', ['ImmortalWrt', running, installed, metadata,
                        dependency if dependency is not None else 'kernel (= ' + PKG + ')',
                        platform, *feeds], ['nk_resolution_compatibility',
                        'nk_artifact_compatibility', 'nk_resolution_eligible',
                        'nk_installation_eligible', 'nk_execution_supported',
                        'nk_execution_authorized', 'nk_reasons'])

    def test_supported_identity(self):
        for distribution in ('OpenWrt', 'ImmortalWrt'):
            self.assertEqual(self.call('nk_parse_identity', [distribution, PKG],
                ['nk_parse_state', 'nk_raw_identity', 'nk_version', 'nk_release',
                 'nk_vermagic', 'nk_canonical_abi', 'nk_adapter_id', 'nk_adapter_version']),
                ['TRUE', PKG, '6.6.133', '1', HASH, ABI,
                 'openwrt-immortalwrt-kernel-package', '1'])

    def test_matching_version_is_only_consistency(self):
        r = self.evaluate()
        self.assertEqual(r[:6], ['COMPATIBLE', 'UNKNOWN', 'true', 'false', 'false', 'false'])
        self.assertIn('KERNEL_ABI_UNVERIFIED', r[6])
        self.assertIn('ARTIFACT_DIGEST_UNVERIFIED', r[6])
        self.assertIn('METADATA_ARTIFACT_BINDING_UNVERIFIED', r[6])

    def test_active_mismatch(self):
        r = self.evaluate(running='6.6.132')
        self.assertEqual(r[:4], ['INCOMPATIBLE', 'INCOMPATIBLE', 'false', 'false'])
        self.assertIn('ACTIVE_KERNEL_BINDING_MISMATCH', r[6])
        self.assertIn('KERNEL_VERSION_MISMATCH', r[6])

    def test_missing_installed(self):
        r = self.evaluate(installed='')
        self.assertEqual(r[:4], ['UNKNOWN', 'UNKNOWN', 'false', 'false'])
        self.assertIn('ACTIVE_KERNEL_BINDING_UNVERIFIED', r[6])
        self.assertIn('KERNEL_ABI_UNAVAILABLE', r[6])

    def test_malformed_identity(self):
        values = [PKG+'~x', PKG+'-r2', '~'+HASH+'-r1', '6.6.133~-r1',
                  '6.6.133~'+HASH+'-r', PKG+' ', ' '+PKG, PKG+'\n',
                  '$(exit 88)', '`exit 88`', '/etc/passwd', 'x'*4096,
                  '6.6.133~'+HASH+'-r0', '06.6.133~'+HASH+'-r1',
                  '6.6.133~'+HASH.upper()+'-r1', ABI, PKG+'; exit 88']
        for value in values:
            with self.subTest(value=value):
                r = self.evaluate(installed=value)
                self.assertEqual(r[0], 'UNKNOWN')
                self.assertIn('KERNEL_METADATA_FORMAT_UNSUPPORTED', r[6])
                self.assertEqual(r[3], 'false')

    def test_unsupported_distribution(self):
        self.assertEqual(self.call('nk_parse_identity', ['Other', PKG],
                                   ['nk_parse_state']), ['UNDETERMINED'])

    def test_feed_support_only(self):
        for feeds in ((ABI,), (ABI, ABI)):
            r = self.evaluate(feeds=feeds)
            self.assertEqual(r[0:2], ['COMPATIBLE', 'UNKNOWN'])
            self.assertEqual(r[3], 'false')
        self.assertEqual(self.evaluate(installed='', feeds=(ABI,))[0], 'UNKNOWN')

    def test_feed_mismatch(self):
        r = self.evaluate(feeds=('6.6.133-2-'+HASH,))
        self.assertEqual(r[0], 'INCOMPATIBLE')
        self.assertIn('KERNEL_ABI_MISMATCH', r[6])

    def test_feed_ambiguity_deterministic(self):
        feeds = (ABI, '6.6.133-2-'+HASH)
        a = self.evaluate(feeds=feeds)
        self.assertEqual(a, self.evaluate(feeds=tuple(reversed(feeds))))
        self.assertEqual(a[0], 'UNKNOWN')
        self.assertIn('AMBIGUOUS_KMOD_FEEDS', a[6])

    def test_invalid_feed(self):
        r = self.evaluate(feeds=('invalid',))
        self.assertEqual(r[0], 'UNKNOWN')
        self.assertIn('KERNEL_METADATA_FORMAT_UNSUPPORTED', r[6])

    def test_requirement_fields(self):
        dep = 'kernel (= '+PKG+')'
        self.assertEqual(self.call('nk_parse_requirement', ['ImmortalWrt', 'valid', dep],
            ['nk_raw_dependency', 'nk_requirement_version', 'nk_requirement_release',
             'nk_requirement_vermagic', 'nk_requirement_abi', 'nk_requirement_evidence']),
            [dep, '6.6.133', '1', HASH, ABI, 'unverified_metadata_only'])

    def test_requirement_mismatch(self):
        for identity in ('6.6.133~'+'a'*32+'-r1', '6.6.133~'+HASH+'-r2'):
            r = self.evaluate(dependency='kernel (= '+identity+')')
            self.assertEqual(r[0], 'INCOMPATIBLE')
            self.assertIn('KERNEL_DEPENDENCY_MISMATCH', r[6])

    def test_unsupported_dependency(self):
        for dep in ('', 'kernel (>= '+PKG+')', 'kernel (= '+PKG+'), libc',
                    'kernel (= '+PKG+') | other', 'kernel (= $(exit 88))',
                    'Depends: kernel (= '+PKG+')', 'kernel (= '+PKG+')\n'):
            r = self.evaluate(dependency=dep)
            self.assertEqual(r[0], 'UNKNOWN')
            self.assertIn('DEPENDENCY_SYNTAX_UNSUPPORTED', r[6])

    def test_metadata_states(self):
        for state, reason in [('unavailable', 'PACKAGE_METADATA_UNAVAILABLE'),
                              ('invalid', 'PACKAGE_METADATA_INVALID')]:
            r = self.evaluate(metadata=state)
            self.assertEqual(r[0], 'UNKNOWN')
            self.assertIn(reason, r[6])

    def test_uname_or_vermagic_only(self):
        for installed in ('', HASH):
            self.assertEqual(self.evaluate(installed=installed)[0], 'UNKNOWN')

    def test_aggregation(self):
        for predicates in itertools.product(('TRUE', 'FALSE', 'UNDETERMINED'), repeat=3):
            expected = ('INCOMPATIBLE' if 'FALSE' in predicates else
                        'UNKNOWN' if 'UNDETERMINED' in predicates else 'COMPATIBLE')
            self.assertEqual(self.call('nk_aggregate', list(predicates),
                                      ['nk_compatibility']), [expected])
        self.assertEqual(self.call('nk_aggregate', [], ['nk_compatibility']), ['UNKNOWN'])

    def test_platform_unknown_blocks_resolution(self):
        r = self.evaluate(platform='UNDETERMINED')
        self.assertEqual(r[:4], ['UNKNOWN', 'UNKNOWN', 'false', 'false'])

    def test_reference_fixture(self):
        f = json.loads((HOME/'tests/fixtures/compatibility/r5s.json').read_text())
        r = self.evaluate(running=f['running_kernel'], installed=f['installed_kernel'],
                          dependency=f['artifact_dependency'], feeds=f['feed_candidates'])
        self.assertEqual(r[0], 'COMPATIBLE')
        self.assertEqual(r[1], 'UNKNOWN')
        self.assertFalse(f['artifact_verified'])
