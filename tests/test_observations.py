"""Production shell trust boundary; no Python implementation of the verifier."""
import copy
import itertools
import hashlib
import json
import os
import shlex
import subprocess
import unittest

from test_platform_selection import ABI, BASE, HOME, OBS, host

VERIFIER = 'openwrt-immortalwrt-kernel-package-v1'
INSTALLED = '6.6.133~23375d261da0c0e9da36857794905cf7-r1'
SCRIPT = r'''
set -eu
. "$1/lib/kernel-identity.sh"
. "$1/lib/manifest.sh"
. "$1/lib/observations.sh"
. "$1/lib/verifiers.sh"
. "$1/lib/resolver.sh"
shift
ns_reset
np_reset
while [ "$#" -gt 0 ]; do
    kind=$1; shift
    case "$kind" in
        A) ns_collect "$1" "$2" "$3" "$4" || printf 'E|%s\n' "$ns_fault"; shift 4 ;;
        V) ns_verify "$1" || printf 'E|%s\n' "$ns_fault"; shift ;;
        X) ns_verify "$1" verified forged || printf 'E|%s\n' "$ns_fault"; shift ;;
        S) ns_seal || printf 'E|%s\n' "$ns_fault" ;;
        R) ns_reset ;;
        L) np_load_snapshot ;;
        O) np_observe "$1" "$2" "$3" "$4" "$5" "$6"; shift 6 ;;
        M) np_add_manifest "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}" "${12}"; shift 12 ;;
        G) ns_get "$1"; printf 'G|%s|%s|%s|%s|%s\n' "$1" "$ns_state" "$ns_value" "$ns_provenance" "$ns_observation"; shift ;;
        *) exit 91 ;;
    esac
done
printf 'R|%s|%s|%s|%s|%s|%s|%s|%s\n' "$ns_phase" "$ns_fault" "$ns_verifier" "$ns_verification" "$ns_binding" "$ns_abi" "$ns_reasons" "$ns_feed_check"
np_finish
printf 'P|%s|%s|%s|%s|%s|%s|%s\n' "$np_selection" "$np_selected_id" "$np_selected_kernel" "$np_selection_reason" "$np_installation_eligible" "$np_execution_supported" "$np_execution_authorized"
'''


def evidence():
    data = [(f, o['state'], o['value'], 'board-json') for f, o in OBS.items() if f != 'kernel_abi']
    return data + [('installed_kernel', 'known', INSTALLED, 'installed-kernel-package')]


class ObservationTests(unittest.TestCase):
    def run_shell(self, data=None, method=VERIFIER, tail=(), verify=True, seal=True, prefix=(), env=None, script=SCRIPT):
        args = list(prefix)
        for row in evidence() if data is None else data:
            args += ['A', *row]
        if verify: args += ['V', method]
        if seal: args += ['S']
        args += list(tail)
        proc = subprocess.run([*shlex.split(os.environ.get('NW_TEST_SHELL', '/bin/sh')),
                               '-c', script, 'snapshot', str(HOME), *args],
                              capture_output=True, text=True, timeout=5, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, '')
        rows = [line.split('|') for line in proc.stdout.splitlines()]
        result = next(row[1:] for row in rows if row[0] == 'R')
        plan = next(row[1:] for row in rows if row[0] == 'P')
        self.assertEqual(plan[-3:], ['false'] * 3)
        return result, plan, rows

    def changed(self, field, state, value):
        return [(f, state if f == field else s, value if f == field else v, p)
                for f, s, v, p in evidence()]

    def resolve(self, manifest=BASE):
        return ['L', 'M', *host.normalize(json.dumps(manifest))]

    def not_verified(self, data=None, method=VERIFIER, reason=None):
        r, p, rows = self.run_shell(data, method, tail=self.resolve())
        self.assertNotEqual(r[3], 'verified')
        self.assertEqual(r[5], '')
        self.assertNotEqual(p[2], 'COMPATIBLE')
        if reason: self.assertIn(reason, r[6].split())
        return r

    def test_r5s_binding(self):
        r, p, _ = self.run_shell(tail=self.resolve())
        self.assertEqual(r, ['sealed', '', VERIFIER, 'verified', 'TRUE', ABI, '', 'UNDETERMINED'])
        self.assertEqual(p[:3], ['SELECTED', BASE['id'], 'COMPATIBLE'])

    def test_feed_match_corroborates(self):
        r, _, _ = self.run_shell(evidence() + [('feed_abi', 'known', ABI, 'configured-kmods-feed')])
        self.assertEqual(r[3], 'verified'); self.assertEqual(r[7], 'TRUE')

    def test_missing_feed_is_not_match(self):
        r, _, _ = self.run_shell()
        self.assertEqual(r[3], 'verified'); self.assertEqual(r[7], 'UNDETERMINED')

    def test_known_claim_does_not_replace_derived(self):
        r, _, _ = self.run_shell(evidence() + [('claimed_abi', 'known', ABI, 'caller-claim')])
        self.assertEqual(r[5], ABI)

    def test_fake_verified_marker(self):
        for method in ('foo', VERIFIER, ''):
            tail = []
            for f, o in OBS.items():
                tail += ['O', f, o['state'], o['value'], o['source'], 'verified', method]
            tail += ['M', *host.normalize(json.dumps(BASE))]
            _, p, _ = self.run_shell([], verify=False, tail=tail)
            self.assertEqual(p[2], 'UNKNOWN')

    def test_registered_id_preforged_result_rejected(self):
        r, p, rows = self.run_shell(verify=False, seal=False,
            tail=['X', VERIFIER, 'S', *self.resolve()])
        self.assertEqual(r[1], 'OBSERVATION_INVALID')
        self.assertEqual(p[0], 'BLOCKED')
        self.assertTrue(any(row[0] == 'E' for row in rows))

    def test_registry_module_unavailable(self):
        env=dict(os.environ, nv_verification='verified', nv_binding='TRUE', nv_abi=ABI)
        script=SCRIPT.replace('. "$1/lib/verifiers.sh"', '')
        r,p,_=self.run_shell(script=script, env=env, tail=self.resolve())
        self.assertEqual(r[3:7], ['unverified','UNDETERMINED','','VERIFIER_UNAVAILABLE'])
        self.assertEqual(p[2], 'UNKNOWN')

    def test_parser_module_unavailable(self):
        env=dict(os.environ, nk_parse_state='TRUE', nk_canonical_abi=ABI)
        script=SCRIPT.replace('. "$1/lib/kernel-identity.sh"', '')
        r,_,_=self.run_shell(script=script, env=env)
        self.assertEqual(r[3:7], ['unverified','UNDETERMINED','','VERIFIER_UNAVAILABLE'])

    def test_unknown_verifier(self):
        self.not_verified(method='foo', reason='VERIFIER_UNKNOWN')

    def test_empty_verifier(self):
        self.not_verified(method='', reason='VERIFIER_UNAVAILABLE')

    def test_verifier_injection(self):
        for value in ('$(exit 88)', '`exit 88`', ';exit 88', VERIFIER+'\n', '../../lib/resolver.sh', 'a'*1024):
            self.not_verified(method=value, reason='VERIFIER_UNKNOWN')

    def test_provenance_injection(self):
        for source in ('$(exit 88)', '`exit 88`', '../file', 'uname-r; exit 88', 'board-json\n'):
            r, p, _ = self.run_shell(evidence()+[('kernel', 'known', '6.6.133', source)], tail=self.resolve())
            self.assertEqual(r[1], 'OBSERVATION_INVALID'); self.assertEqual(p[0], 'BLOCKED')

    def test_abi_injection(self):
        for value in ('$(exit 88)', '`exit 88`', ';exit 88', '*', '?', '[abc]', '\\', '"', "'", 'a b', 'a\tb', 'a\nb'):
            self.not_verified(evidence()+[('claimed_abi','known',value,'caller-claim')])

    def test_malformed_package(self):
        self.not_verified(self.changed('installed_kernel','known','malformed'), reason='KERNEL_METADATA_FORMAT_UNSUPPORTED')

    def test_unsupported_package_grammar(self):
        for value in (ABI, INSTALLED.upper(), INSTALLED.replace('-r1','-r01'), '6.6.133-r1'):
            self.not_verified(self.changed('installed_kernel','known',value), reason='KERNEL_METADATA_FORMAT_UNSUPPORTED')

    def test_missing_running(self):
        self.not_verified(self.changed('kernel','missing',''), reason='ACTIVE_KERNEL_BINDING_UNVERIFIED')

    def test_unsupported_running_state(self):
        self.not_verified(self.changed('kernel','unsupported','6.6.133'), reason='IDENTITY_FIELD_UNAVAILABLE')

    def test_unsupported_running_syntax(self):
        for value in ('6.6', '6.6.133-custom', '06.6.133', '-6.6.133', '../6.6.133'):
            self.not_verified(self.changed('kernel','known',value), reason='KERNEL_METADATA_FORMAT_UNSUPPORTED')

    def test_running_mismatch(self):
        r = self.not_verified(self.changed('kernel','known','6.6.132'), reason='ACTIVE_KERNEL_BINDING_MISMATCH')
        self.assertEqual(r[3:5], ['rejected','FALSE'])

    def test_supplied_abi_mismatch(self):
        self.not_verified(evidence()+[('claimed_abi','known',ABI.replace('-1-','-2-'),'caller-claim')], reason='KERNEL_ABI_MISMATCH')

    def test_feed_mismatch(self):
        r = self.not_verified(evidence()+[('feed_abi','known',ABI.replace('-1-','-2-'),'configured-kmods-feed')], reason='KERNEL_ABI_MISMATCH')
        self.assertEqual(r[7], 'FALSE')

    def test_feed_only(self):
        d = [row for row in evidence() if row[0] != 'installed_kernel']
        self.not_verified(d+[('feed_abi','known',ABI,'configured-kmods-feed')], reason='KERNEL_ABI_UNAVAILABLE')

    def test_conflicting_feeds(self):
        d = evidence()+[('feed_abi','known',a,'configured-kmods-feed') for a in (ABI,ABI.replace('-1-','-2-'))]
        self.not_verified(d, reason='AMBIGUOUS_KMOD_FEEDS')

    def test_conflicting_observation(self):
        for field, _, _, _ in evidence():
            self.not_verified(self.changed(field,'conflicting',''), reason='IDENTITY_EVIDENCE_CONFLICT')

    def test_unsupported_observation(self):
        for field, _, _, _ in evidence():
            self.not_verified(self.changed(field,'unsupported',''), reason='IDENTITY_FIELD_UNAVAILABLE')

    def test_invalid_state(self):
        self.not_verified(self.changed('kernel','verified','6.6.133'), reason='OBSERVATION_STATE_INVALID')

    def test_known_missing_merge(self):
        for order in itertools.permutations([('kernel','known','6.6.133','uname-r'),('kernel','missing','','proc-kernel-osrelease')]):
            d = [row for row in evidence() if row[0] != 'kernel'] + list(order)
            r, _, rows = self.run_shell(d, tail=['G','kernel'])
            self.assertEqual(r[3], 'verified')
            self.assertIn(['G','kernel','known','6.6.133','proc-kernel-osrelease uname-r','observed'], rows)

    def test_conflict_sticky(self):
        d=evidence()+[('kernel','known',v,'uname-r') for v in ('6.6.132','6.6.133','6.6.132')]
        self.not_verified(d, reason='IDENTITY_EVIDENCE_CONFLICT')

    def test_unsupported_sticky(self):
        d=evidence()+[('kernel','unsupported','','uname-r'),('kernel','known','6.6.133','uname-r')]
        self.not_verified(d, reason='IDENTITY_FIELD_UNAVAILABLE')

    def mutation(self, row):
        r, p, rows = self.run_shell(tail=[*self.resolve(),'A',*row,'G','kernel'])
        self.assertEqual(r[1], 'SNAPSHOT_MUTATION_REJECTED')
        self.assertEqual(r[3:6], ['verified','TRUE',ABI])  # sealed data remains unchanged
        self.assertIn(['G','kernel','known','6.6.133','board-json','observed'], rows)
        self.assertEqual(p[0], 'BLOCKED')
        self.assertEqual(p[1], '')
        self.assertIn(['E','SNAPSHOT_MUTATION_REJECTED'], rows)

    def test_mutate_value(self):
        self.mutation(('kernel','known','6.6.132','board-json'))

    def test_mutate_state(self):
        self.mutation(('kernel','missing','','board-json'))

    def test_mutate_provenance(self):
        self.mutation(('kernel','known','6.6.133','uname-r'))

    def test_late_new_evidence(self):
        self.mutation(('feed_abi','known',ABI,'configured-kmods-feed'))

    def test_overwrite_verifier(self):
        r, p, _ = self.run_shell(tail=[*self.resolve(),'V',VERIFIER])
        self.assertEqual(r[1], 'SNAPSHOT_MUTATION_REJECTED'); self.assertEqual(p[0], 'BLOCKED')

    def test_verify_twice_before_seal(self):
        r, _, _ = self.run_shell(seal=False, tail=['V',VERIFIER,'S'])
        self.assertEqual(r[1], 'SNAPSHOT_MUTATION_REJECTED')

    def test_collect_after_binding(self):
        r, _, _ = self.run_shell(seal=False,tail=['A','kernel','known','6.6.133','uname-r','S'])
        self.assertEqual(r[1], 'SNAPSHOT_MUTATION_REJECTED')

    def test_seal_without_verifier(self):
        r, p, _ = self.run_shell(verify=False, tail=self.resolve())
        self.assertEqual(r[3], 'unverified'); self.assertEqual(p[2], 'UNKNOWN')

    def test_load_unsealed_snapshot(self):
        _, p, _ = self.run_shell(seal=False, tail=self.resolve())
        self.assertEqual(p[0], 'BLOCKED')

    def test_reset_invalidates_consumed_generation(self):
        _, p, _ = self.run_shell(tail=[*self.resolve(),'R','V',VERIFIER,'S'])
        self.assertEqual(p[0], 'BLOCKED')

    def test_input_order(self):
        d=evidence()
        expected=self.run_shell(d,tail=self.resolve())[:2]
        for rows in (list(reversed(d)), d[3:]+d[:3],d[::2]+d[1::2]):
            self.assertEqual(self.run_shell(rows,tail=self.resolve())[:2], expected)

    def test_duplicate_evidence_idempotent(self):
        self.assertEqual(self.run_shell()[0],self.run_shell(evidence()*2)[0])

    def test_duplicate_conflicting_order(self):
        d=[row for row in evidence() if row[0]!='kernel']
        for values in itertools.permutations(['6.6.133','6.6.132','6.6.133']):
            r, _, rows=self.run_shell(d+[('kernel','known',v,'uname-r') for v in values],tail=['G','kernel'])
            self.assertEqual(r[6], 'IDENTITY_EVIDENCE_CONFLICT')
            self.assertIn(['G','kernel','conflicting','','uname-r','observed'],rows)

    def test_reason_order(self):
        d=self.changed('kernel','known','6.6.132')+[('feed_abi','known',ABI.replace('-1-','-2-'),'configured-kmods-feed')]
        for data in (d,list(reversed(d))):
            r=self.not_verified(data)
            self.assertEqual(r[6], 'KERNEL_VERSION_MISMATCH ACTIVE_KERNEL_BINDING_MISMATCH KERNEL_ABI_MISMATCH')

    def test_environment_not_verification(self):
        env=dict(os.environ, verification='verified', method=VERIFIER, ABI='forged', IFS=';',
                 ns_phase='sealed', ns_verification='verified', ns_abi='forged', ns_generation='99')
        self.assertEqual(self.run_shell(env=env)[0],self.run_shell()[0])

    def test_sourcing_does_not_import_forged_snapshot(self):
        env=dict(os.environ, ns_phase='sealed', ns_fault='', ns_verification='verified',
                 ns_abi=ABI, ns_binding='TRUE', ns_generation='99')
        script=SCRIPT.replace('shift\nns_reset\nnp_reset', 'shift\nnp_reset')
        r,p,_=self.run_shell([], verify=False, seal=False, env=env, script=script,
                             tail=self.resolve())
        self.assertEqual(r[:2], ['collecting',''])
        self.assertEqual(r[3:6], ['unverified','UNDETERMINED',''])
        self.assertEqual(p[0], 'BLOCKED')

    def test_overlong_field(self):
        r,p,_=self.run_shell(self.changed('kernel','known','a'*129),tail=self.resolve())
        self.assertEqual(r[1], 'OBSERVATION_INVALID'); self.assertEqual(p[0],'BLOCKED')

    def test_unknown_field(self):
        r,p,_=self.run_shell(evidence()+[('verification','known','verified','caller-claim')],tail=self.resolve())
        self.assertEqual(r[1],'OBSERVATION_INVALID'); self.assertEqual(p[0],'BLOCKED')

    def test_derived_field_not_writable(self):
        r,_,_=self.run_shell(evidence()+[('kernel_abi','known',ABI,'caller-claim')])
        self.assertEqual(r[1],'OBSERVATION_INVALID')

    def test_null_manifest_not_wildcard(self):
        m=copy.deepcopy(BASE);m['identity']['kernel_abi']=None
        _,p,_=self.run_shell(tail=self.resolve(m))
        self.assertEqual(p[:3],['SELECTED',BASE['id'],'UNKNOWN'])

    def test_missing_platform_not_filled_by_kernel(self):
        _,p,_=self.run_shell(self.changed('target','missing',''),tail=self.resolve())
        self.assertEqual(p[0],'BLOCKED')

    def test_empty_known(self):
        self.not_verified(self.changed('installed_kernel','known',''),reason='IDENTITY_FIELD_UNAVAILABLE')

    def test_foreign_distribution(self):
        self.not_verified(self.changed('distribution','known','OtherWrt'),reason='KERNEL_METADATA_FORMAT_UNSUPPORTED')

    def test_supported_openwrt_adapter(self):
        r,_,_=self.run_shell(self.changed('distribution','known','OpenWrt'))
        self.assertEqual(r[3:6],['verified','TRUE',ABI])

    def test_missing_distribution(self):
        self.not_verified(self.changed('distribution','missing',''),reason='ACTIVE_KERNEL_BINDING_UNVERIFIED')

    def test_nonparser_long_but_bounded_package(self):
        self.not_verified(self.changed('installed_kernel','known','x'*128),reason='KERNEL_METADATA_FORMAT_UNSUPPORTED')

    def test_double_seal_rejected(self):
        r,_,_=self.run_shell(tail=['S'])
        self.assertEqual(r[1],'SNAPSHOT_MUTATION_REJECTED')

    def test_read_only_doctor_unchanged(self):
        # Frozen source digests from accepted 8d9354f; also works without git.
        expected = {
            'nanowrt':
                '54fce57c5a603249ecefb4679e30a32e95125f231f9f6b7f83e5c983b174ef0c',
            'lib/common.sh':
                'cec2209fdb5b129309ef79689d1350c1d39022d21628220953b8df9d4fb93a87',
            'lib/inventory.sh':
                'b43b5a33b5f37f8e53da9304751a4f6715f51586f6e6b13cac578b938c24d253',
            'lib/platform.sh':
                '8487c51161ca07c0f3d00997ed3c5039a9b4c02f552cffbf1316a20e2f21ed66',
            'lib/packages.sh':
                'a6d43d7c26c43b58f34de2eac68704a75260d412f7a306587abefe68c88aa6bb',
            'lib/network.sh':
                '86b369b12b658dd768b96357cc4a8bc7dce055492ea810e62ed389172dcf7814',
            'lib/modem.sh':
                'd3ef026a32c4d13c5f4868749f6799576d848bf52f671ff061fe35e4fa0fe658',
            'lib/opkg-config.awk':
                '8a441843d9f2e723d5fde4c12a8540d29a88f59a2aa094bd6b9a9ff0d3312495',
            'lib/status.awk':
                '1d3f6a4f4216f94e68af7a307e74ef39dc65439f75687018d7e65e3b6cc812ac',
        }
        for path, digest in expected.items():
            self.assertEqual(hashlib.sha256((HOME/path).read_bytes()).hexdigest(), digest)
