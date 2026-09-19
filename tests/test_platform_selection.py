"""Offline host-contract and POSIX selector tests; all data passed as argv."""
import copy
import importlib.util
import itertools
import json
import os
from pathlib import Path
import shlex
import subprocess
import unittest

HOME = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('platform_manifest', HOME/'tools/platform_manifest.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
FIXTURES = HOME/'tests/fixtures/platform'
BASE = json.loads((FIXTURES/'r5s.json').read_text())
OBS = json.loads((FIXTURES/'observations-r5s.json').read_text())
ABI = BASE['identity']['kernel_abi']
SCRIPT = r'''
set -eu
. "$1/lib/kernel-identity.sh"
. "$1/lib/manifest.sh"
. "$1/lib/resolver.sh"
. "$1/lib/observations.sh"
. "$1/lib/verifiers.sh"
shift
np_reset
ns_reset
while [ "$#" -gt 0 ]; do
    kind=$1; shift
    case "$kind" in
        O) np_observe "$1" "$2" "$3" "$4" "$5" "$6"; shift 6 ;;
        N) ns_collect "$1" "$2" "$3" "$4"; shift 4 ;;
        V) ns_verify "$1"; ns_seal; np_load_snapshot; shift ;;
        M) np_add_manifest "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}" "${12}"; shift 12 ;;
        I) np_invalid_input "$1"; shift ;;
        *) exit 91 ;;
    esac
    if [ "$kind" = M ] || [ "$kind" = I ]; then
        printf 'C|%s|%s|%s|%s|%s|%s\n' "$np_candidate_id" "$np_candidate_class" "$np_candidate_kernel" "$np_kernel_predicate" "$np_candidate_reasons" "$np_candidate_predicates"
    fi
done
np_finish
printf 'S|%s|%s|%s|%s|%s|%s|%s|%s\n' "$np_selection" "$np_selected_id" "$np_base_compatibility" "$np_selected_kernel" "$np_selection_reason" "$np_installation_eligible" "$np_execution_supported" "$np_execution_authorized"
'''


class PlatformSelectionTests(unittest.TestCase):
    def run_selection(self, manifests=None, observations=None, records=None, script=SCRIPT):
        args = [str(HOME)]
        observations = OBS if observations is None else observations
        trusted = 'installed_kernel' in observations
        for field, o in observations.items():
            if trusted:
                args += ['N', 'claimed_abi' if field == 'kernel_abi' else field,
                         o['state'], o['value'], o['source']]
            else:
                args += ['O', field, o['state'], o['value'], o['source'],
                         o.get('verification', 'unverified'), o.get('method', '')]
        if trusted:
            args += ['V', observations['kernel_abi']['method']]
        if records is not None:
            for record in records:
                args += ['M', *record]
        else:
            for manifest in ([BASE] if manifests is None else manifests):
                text = manifest if isinstance(manifest, str) else json.dumps(manifest)
                try:
                    args += ['M', *host.normalize(text)]
                except host.ManifestInputError as exc:
                    args += ['I', exc.code]
        result = subprocess.run([*shlex.split(os.environ.get('NW_TEST_SHELL', '/bin/sh')),
                                 '-c', script, 'selection', *args],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        rows = [line.split('|') for line in result.stdout.splitlines()]
        self.assertTrue(rows and rows[-1][0] == 'S', result.stdout)
        self.assertEqual(rows[-1][-3:], ['false', 'false', 'false'])
        return rows[:-1], rows[-1][1:]

    def mismatch(self, field, value, reason):
        obs = copy.deepcopy(OBS); obs[field]['value'] = value
        c, s = self.run_selection(observations=obs)
        self.assertEqual(c[0][2], 'NO_MATCH')
        self.assertIn(reason, c[0][5].split())
        self.assertEqual(s[0], 'BLOCKED')
        self.assertEqual(s[4], 'MANIFEST_NOT_FOUND')

    def test_exact_r5s(self):
        c, s = self.run_selection()
        self.assertEqual(c[0][2], 'MATCH')
        self.assertEqual(s[:4], ['SELECTED', BASE['id'], 'COMPATIBLE', 'UNKNOWN'])

    def test_r3s_board(self):
        r3s = json.loads((FIXTURES/'r3s.json').read_text())
        c, s = self.run_selection([r3s])
        self.assertEqual(c[0][2], 'NO_MATCH')
        self.assertIn('BOARD_MISMATCH', c[0][5])
        self.assertEqual(s[0], 'BLOCKED')

    def test_distribution(self):
        self.mismatch('distribution', 'OpenWrt', 'DISTRIBUTION_MISMATCH')

    def test_release(self):
        self.mismatch('release', '24.10.5', 'RELEASE_MISMATCH')

    def test_revision_mismatch(self):
        self.mismatch('revision', 'r-other', 'REVISION_MISMATCH')

    def test_revision_missing(self):
        o = copy.deepcopy(OBS); o['revision']['state'] = 'missing'
        c, s = self.run_selection(observations=o)
        self.assertEqual(c[0][2], 'UNDETERMINED')
        self.assertEqual(s[4], 'MANIFEST_SELECTION_UNDETERMINED')

    def test_informational_revision(self):
        m = copy.deepcopy(BASE); m['identity']['revision'] = {
            'policy':'informational', 'value':None, 'rationale':'Reference release policy'}
        for state in ('known', 'missing', 'conflicting', 'unsupported'):
            o = copy.deepcopy(OBS); o['revision'].update(state=state, value='different')
            self.assertEqual(self.run_selection([m], o)[1][0], 'SELECTED')

    def test_informational_without_rationale(self):
        m = copy.deepcopy(BASE); m['identity']['revision']['policy'] = 'informational'
        c, s = self.run_selection([m])
        self.assertEqual(c[0][2], 'INVALID')
        self.assertEqual(s[4], 'MANIFEST_INVALID')

    def test_target(self):
        self.mismatch('target', 'rockchip/other', 'TARGET_MISMATCH')

    def test_architecture(self):
        self.mismatch('architecture', 'aarch64_other', 'ARCH_MISMATCH')

    def test_kernel_version(self):
        self.mismatch('kernel', '6.6.132', 'KERNEL_VERSION_MISMATCH')

    def uncertain(self, state, reason):
        for field in ('distribution', 'release', 'revision', 'board_name', 'target', 'architecture', 'kernel'):
            with self.subTest(field=field):
                o = copy.deepcopy(OBS); o[field]['state'] = state
                c, s = self.run_selection(observations=o)
                self.assertEqual(c[0][2], 'UNDETERMINED')
                self.assertIn(reason, c[0][5])
                self.assertEqual(s[0], 'BLOCKED')

    def test_missing_observation(self):
        self.uncertain('missing', 'IDENTITY_FIELD_UNAVAILABLE')

    def test_conflicting_observation(self):
        self.uncertain('conflicting', 'IDENTITY_EVIDENCE_CONFLICT')

    def test_unsupported_observation(self):
        self.uncertain('unsupported', 'IDENTITY_FIELD_UNAVAILABLE')

    def test_zero_manifests(self):
        self.assertEqual(self.run_selection([])[1][4], 'MANIFEST_NOT_FOUND')

    def test_zero_matches(self):
        m = copy.deepcopy(BASE); m['identity']['release'] = '25.1.1'
        self.assertEqual(self.run_selection([m])[1][4], 'MANIFEST_NOT_FOUND')

    def test_two_matches(self):
        m = copy.deepcopy(BASE); m['id'] = 'second'
        s = self.run_selection([BASE, m])[1]
        self.assertEqual(s[4], 'MANIFEST_SELECTION_AMBIGUOUS')
        self.assertEqual(s[1], '')

    def contenders(self):
        m = copy.deepcopy(BASE); m['id'] = 'informational'
        m['identity']['revision'] = {'policy':'informational', 'value':None, 'rationale':'Reference only'}
        o = copy.deepcopy(OBS); o['revision']['state'] = 'missing'
        return m, o

    def test_match_and_undetermined(self):
        m, o = self.contenders()
        c, s = self.run_selection([m, BASE], o)
        self.assertEqual([x[2] for x in c], ['MATCH', 'UNDETERMINED'])
        self.assertEqual(s[4], 'MANIFEST_SELECTION_UNDETERMINED')
        self.assertEqual(s[1], '')

    def test_only_undetermined(self):
        _, o = self.contenders()
        self.assertEqual(self.run_selection([BASE], o)[1][4], 'MANIFEST_SELECTION_UNDETERMINED')

    def test_invalid_active_set(self):
        c, s = self.run_selection([BASE, '{}'])
        self.assertEqual(c[1][2], 'INVALID')
        self.assertEqual(s[4], 'MANIFEST_INVALID')
        self.assertEqual(s[1], '')

    def test_duplicate_ids(self):
        c, s = self.run_selection([BASE, BASE])
        self.assertIn('MANIFEST_REFERENCE_INVALID', s[4])
        self.assertEqual(s[0], 'BLOCKED')

    def test_permutations(self):
        m, o = self.contenders()
        no = copy.deepcopy(BASE); no['id'] = 'no'; no['identity']['target'] = 'other/target'
        expected = None
        for manifests in itertools.permutations([m, BASE, no]):
            c, s = self.run_selection(manifests, o)
            semantic = (sorted(c), s)
            if expected is None: expected = semantic
            self.assertEqual(semantic, expected)

    def test_filename_irrelevant(self):
        # The API has no filename field; identical bytes via arbitrary host labels.
        outputs = [self.run_selection([json.dumps({name: BASE}[name])])
                   for name in ('z.json', '00-preferred.json', 'immortalwrt_kmods.json')]
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], outputs[2])

    def test_empty_is_not_wildcard(self):
        for field in ('release', 'board_name', 'kernel'):
            m = copy.deepcopy(BASE); m['identity'][field] = ''
            self.assertEqual(self.run_selection([m])[0][0][2], 'INVALID')
            o = copy.deepcopy(OBS); o[field]['value'] = ''
            self.assertEqual(self.run_selection(observations=o)[0][0][2], 'UNDETERMINED')

    def test_prefixes(self):
        for field, value, code in [('release','24.10','RELEASE_MISMATCH'),
            ('target','rockchip','TARGET_MISMATCH'),('architecture','aarch64','ARCH_MISMATCH'),
            ('kernel','6.6','KERNEL_VERSION_MISMATCH'),('board_name','friendlyarm,nanopi-r5','BOARD_MISMATCH')]:
            self.mismatch(field, value, code)

    def test_case_sensitive(self):
        self.mismatch('distribution', 'immortalwrt', 'DISTRIBUTION_MISMATCH')

    def test_abi_null(self):
        m = copy.deepcopy(BASE); m['identity']['kernel_abi'] = None
        o = self.verified()
        c, s = self.run_selection([m], o)
        self.assertEqual(s[0], 'SELECTED')
        self.assertEqual(c[0][4], 'UNDETERMINED')
        self.assertEqual(s[3], 'UNKNOWN')

    def test_feed_only_abi(self):
        o = copy.deepcopy(OBS); o['kernel_abi']['source'] = 'configured-feed'
        c, s = self.run_selection(observations=o)
        self.assertEqual(c[0][4], 'UNDETERMINED')
        self.assertIn('KERNEL_ABI_UNVERIFIED', c[0][5])

    def verified(self):
        o = copy.deepcopy(OBS)
        for field, obs in o.items():
            obs['source'] = 'caller-claim' if field == 'kernel_abi' else 'board-json'
        o['kernel_abi']['method'] = 'openwrt-immortalwrt-kernel-package-v1'
        o['installed_kernel'] = dict(state='known',
            value='6.6.133~23375d261da0c0e9da36857794905cf7-r1',
            source='installed-kernel-package')
        return o

    def test_verified_abi_equal(self):
        c, s = self.run_selection(observations=self.verified())
        self.assertEqual(c[0][4], 'TRUE')
        self.assertEqual(s[3], 'COMPATIBLE')

    def test_verified_abi_mismatch(self):
        o = self.verified(); o['kernel_abi']['value'] = ABI.replace('-1-', '-2-')
        o['installed_kernel']['value'] = o['installed_kernel']['value'].replace('-r1', '-r2')
        c, s = self.run_selection(observations=o)
        self.assertEqual(c[0][4], 'FALSE')
        self.assertEqual(s[0], 'SELECTED')
        self.assertEqual(s[3], 'INCOMPATIBLE')
        self.assertIn('KERNEL_ABI_MISMATCH', c[0][5])

    def test_unknown_abi(self):
        for state in ('missing', 'conflicting', 'unsupported'):
            o = copy.deepcopy(OBS); o['kernel_abi']['state'] = state
            self.assertEqual(self.run_selection(observations=o)[0][0][4], 'UNDETERMINED')

    def test_unknown_schema(self):
        m = copy.deepcopy(BASE); m['schema_version'] = 9
        s = self.run_selection([m])[1]
        self.assertIn('MANIFEST_INVALID', s[4])
        self.assertIn('MANIFEST_SCHEMA_UNSUPPORTED', s[4])

    def test_malformed_json_and_shape(self):
        for text in ('{', '[]', 'null', json.dumps(BASE)+' garbage',
                     json.dumps(BASE).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')):
            self.assertEqual(self.run_selection([text])[1][4], 'MANIFEST_INVALID')
        for key, value in [('schema_version',True),('extra','bad'),('identity',[]),('id',None)]:
            m = copy.deepcopy(BASE); m[key] = value
            self.assertEqual(self.run_selection([m])[1][4], 'MANIFEST_INVALID')

    def test_metacharacters_inert(self):
        for value in ('$(exit 88)', '`exit 88`', '; exit 88', '*', '../*', 'x\ny'):
            m = copy.deepcopy(BASE); m['identity']['release'] = value
            self.assertEqual(self.run_selection([m])[0][0][2], 'INVALID')
            o = copy.deepcopy(OBS); o['release']['value'] = value
            self.assertEqual(self.run_selection(observations=o)[0][0][2], 'UNDETERMINED')
        m = copy.deepcopy(BASE); m['identity']['revision']['rationale'] = '$(exit 88); harmless annotation'
        self.assertEqual(self.run_selection([m])[1][0], 'SELECTED')

    def test_overlong(self):
        for field in ('release', 'board_name', 'kernel'):
            m = copy.deepcopy(BASE); m['identity'][field] = 'a'*129
            self.assertEqual(self.run_selection([m])[0][0][2], 'INVALID')
        m = copy.deepcopy(BASE); m['id'] = 'a'*65
        self.assertEqual(self.run_selection([m])[0][0][2], 'INVALID')

    def test_router_contract_rejects_invalid_without_host(self):
        original = host.normalize(json.dumps(BASE))
        for index, value in [(0,'2'),(1,''),(3,'*'),(4,'automatic'),(5,''),(6,'x\ny'),(11,''),(11,'invalid')]:
            args = original.copy(); args[index] = value
            self.assertEqual(self.run_selection(records=[args])[0][0][2], 'INVALID')

    def test_missing_observation_record(self):
        o = copy.deepcopy(OBS); del o['target']
        self.assertEqual(self.run_selection(observations=o)[0][0][2], 'UNDETERMINED')

    def test_false_dominates_unknown(self):
        o = copy.deepcopy(OBS); o['target']['state'] = 'missing'; o['release']['value'] = 'other'
        self.assertEqual(self.run_selection(observations=o)[0][0][2], 'NO_MATCH')

    def test_verified_marker_requires_method(self):
        o = self.verified(); o['kernel_abi']['method'] = ''
        self.assertEqual(self.run_selection(observations=o)[0][0][4], 'UNDETERMINED')

    def test_invalid_verified_abi_is_not_mismatch(self):
        o = self.verified(); o['kernel_abi']['value'] = 'invalid'
        c, s = self.run_selection(observations=o)
        self.assertEqual(c[0][4], 'UNDETERMINED')
        self.assertIn('KERNEL_METADATA_FORMAT_UNSUPPORTED', c[0][5])

    def test_observation_change_after_candidate_blocks(self):
        script = SCRIPT.replace('np_finish\nprintf', 'np_observe release known other late-source\nnp_finish\nprintf')
        self.assertEqual(self.run_selection(script=script)[1][4], 'MANIFEST_SELECTION_UNDETERMINED')

    def test_reset_clears_previous_selection(self):
        script = SCRIPT.replace('np_finish\nprintf', 'np_finish\nnp_reset\nnp_finish\nprintf')
        s = self.run_selection(script=script)[1]
        self.assertEqual(s[1], '')
        self.assertEqual(s[4], 'MANIFEST_NOT_FOUND')

    def test_invalid_precedes_ambiguity(self):
        m = copy.deepcopy(BASE); m['id'] = 'second'
        for manifests in itertools.permutations([BASE, m, '{}']):
            s = self.run_selection(manifests)[1]
            self.assertEqual(s[4], 'MANIFEST_INVALID')
            self.assertEqual(s[1], '')

    def test_duplicate_and_unknown_schema_order(self):
        unsupported = copy.deepcopy(BASE); unsupported['schema_version'] = 9
        results = [self.run_selection(list(ms))[1] for ms in itertools.permutations([BASE, BASE, unsupported])]
        self.assertTrue(all(r == results[0] for r in results))
        self.assertIn('MANIFEST_REFERENCE_INVALID', results[0][4])
        self.assertIn('MANIFEST_SCHEMA_UNSUPPORTED', results[0][4])

    def test_host_input_limits_and_nonstandard_numbers(self):
        for text in (' '*16385, '{"schema_version":NaN}', '[[['*2000, '\ud800'):
            self.assertEqual(self.run_selection([text])[1][4], 'MANIFEST_INVALID')
