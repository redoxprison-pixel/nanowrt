"""Host-only validation of the documented macOS tar command."""
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


@unittest.skipUnless(sys.platform == 'darwin', 'macOS deployment archive check')
class MacPackagingTests(unittest.TestCase):
    def test_appledouble_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('nanowrt', '._nanowrt', '.DS_Store', 'lib/common.sh',
                         'lib/._common.sh', 'lib/.DS_Store', 'profiles/r5s.conf'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture\n')
            subprocess.run(['tar', '--no-xattrs', '--no-acls', '--exclude=._*',
                            '--exclude=.DS_Store', '-czf', str(root / 'deploy.tar.gz'),
                            'nanowrt', 'lib', 'profiles'], cwd=root,
                           env=dict(os.environ, COPYFILE_DISABLE='1'), check=True)
            with tarfile.open(root / 'deploy.tar.gz') as archive:
                names = archive.getnames()
            self.assertIn('nanowrt', names)
            self.assertIn('lib/common.sh', names)
            self.assertFalse(any(Path(name).name.startswith('._') or Path(name).name == '.DS_Store' for name in names))
