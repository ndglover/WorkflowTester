"""Tests the actual workflow shell step. Does not push packages or use credentials.

Requires .NET 10, bash, curl, jq, and openssl. Downloads existing public fixtures.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import urllib.request
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('--fixtures', type=Path)
args, test_args = parser.parse_known_args()
ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / 'workflows/csharp_release.yaml'
# ROOT is .github; use its workflow, rather than duplicating production logic.
lines = WORKFLOW.read_text().splitlines()
start = lines.index('      - name: Verify published NuGet package matches approved package')
run_start = lines.index('        run: |', start) + 1
run_end = lines.index('        env:', run_start)
SCRIPT = '\n'.join(line[10:] for line in lines[run_start:run_end]) + '\n'
BASH = r'C:\Program Files\Git\bin\bash.exe' if os.name == 'nt' else 'bash'
FIXTURES = args.fixtures or Path(tempfile.mkdtemp(prefix='nuget-verification-fixtures-'))
FIXTURES.mkdir(parents=True, exist_ok=True)
APPROVED = FIXTURES / 'approved.3.0.0.nupkg'
PUBLISHED = FIXTURES / 'published.3.0.0.nupkg'
if not APPROVED.exists():
    with urllib.request.urlopen('https://api.github.com/repos/ndglover/WorkflowTester/releases/tags/dotnet/v3.0.0', timeout=30) as response:
        release = json.load(response)
    url = next(asset['browser_download_url'] for asset in release['assets']
               if asset['name'] == 'WorkflowTester.Lib.3.0.0.nupkg')
    urllib.request.urlretrieve(url, APPROVED)
if not PUBLISHED.exists():
    urllib.request.urlretrieve('https://api.nuget.org/v3-flatcontainer/workflowtester.lib/3.0.0/workflowtester.lib.3.0.0.nupkg', PUBLISHED)


def modify(source, destination, entry_name, transform):
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, 'w') as changed:
        for entry in original.infolist():
            content = original.read(entry)
            if entry.filename == entry_name:
                content = transform(content)
            attributes = entry.external_attr
            changed.writestr(entry, content)
            changed.filelist[-1].external_attr = attributes


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'artifacts').mkdir()
        self.bin = self.root / 'test-bin'
        self.bin.mkdir()
        shutil.copyfile(APPROVED, self.root / 'artifacts/approved.nupkg')
        self.environment = dict(os.environ, PACKAGE_NAME='approved.nupkg',
                                RELEASE_VERSION='3.0.0', DOTNET_CLI_UI_LANGUAGE='en-US',
                                GITHUB_STEP_SUMMARY=(self.root / 'summary.md').as_posix(),
                                DOWNLOADED_FIXTURE=PUBLISHED.resolve().as_posix())
        # Mock only transport for deterministic error fixtures. Real dotnet
        # signature verification, hashes, jq and workflow shell still execute.
        curl = self.bin / 'curl'
        curl.write_text('''#!/usr/bin/env bash
set -euo pipefail
if [[ "${TRANSPORT_MODE:-}" == failure ]]; then exit 22; fi
if [[ "${@: -1}" == https://api.nuget.org/v3/index.json ]]; then
  if [[ "${TRANSPORT_MODE:-}" == badindex ]]; then echo '{}'; else
    echo '{"resources":[{"@type":"PackageBaseAddress/3.0.0","@id":"https://api.nuget.org/v3-flatcontainer/"}]}'
  fi
  exit 0
fi
while [[ $# -gt 0 ]]; do
  if [[ "$1" == --output ]]; then output=$2; break; fi
  shift
done
cp "$DOWNLOADED_FIXTURE" "$output"
''', newline='\n')
        curl.chmod(0o755)
        self.environment['PATH'] = str(self.bin) + os.pathsep + os.environ['PATH']

    def tearDown(self):
        self.temp.cleanup()

    def verify(self, succeeds, message=None):
        prefix = ''
        if self.environment.get('REAL_TRANSPORT') != 'true':
            self.environment['TEST_BIN'] = self.bin.as_posix()
            prefix = 'export PATH="$(cygpath -u "$TEST_BIN"):$PATH"\n' if os.name == 'nt' else 'export PATH="$TEST_BIN:$PATH"\n'
        result = subprocess.run([BASH, '--noprofile', '--norc', '-e', '-o', 'pipefail', '-c', prefix + SCRIPT],
                                cwd=self.root, env=self.environment,
                                text=True, capture_output=True, timeout=90)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode == 0, succeeds, output)
        if message:
            self.assertIn(message, output)
        summary = self.root / 'summary.md'
        self.assertEqual(summary.exists(), succeeds)

    def test_real_download_and_signed_match(self):
        # Exercise the real NuGet service-index lookup and package download too.
        self.environment['PATH'] = os.environ['PATH']
        self.environment['REAL_TRANSPORT'] = 'true'
        self.verify(True)

    def test_repository_signature_changes_raw_archive_hash(self):
        self.assertNotEqual(hashlib.sha512(APPROVED.read_bytes()).digest(),
                            hashlib.sha512(PUBLISHED.read_bytes()).digest())

    def test_matching_signed_package(self):
        self.verify(True)

    def test_conflicting_dll_same_identity(self):
        modify(APPROVED, self.root / 'artifacts/approved.nupkg', 'lib/net8.0/WorkflowTester.Lib.dll',
               lambda data: data[:-1] + bytes([data[-1] ^ 1]))
        self.verify(False, 'does not match the approved package')

    def test_conflicting_metadata_same_identity(self):
        with zipfile.ZipFile(APPROVED) as package:
            entry = next(name for name in package.namelist() if name.endswith('.nuspec'))
        modify(APPROVED, self.root / 'artifacts/approved.nupkg', entry,
               lambda data: data.replace(b'</metadata>', b'<summary>Changed</summary></metadata>'))
        self.verify(False, 'does not match the approved package')

    def test_tampered_signature(self):
        tampered = self.root / 'tampered.nupkg'
        modify(PUBLISHED, tampered, 'lib/net8.0/WorkflowTester.Lib.dll',
               lambda data: data[:-1] + bytes([data[-1] ^ 1]))
        self.environment['DOWNLOADED_FIXTURE'] = tampered.as_posix()
        self.verify(False)

    def test_unsigned_download(self):
        self.environment['DOWNLOADED_FIXTURE'] = APPROVED.resolve().as_posix()
        self.verify(False)

    def test_malformed_download(self):
        invalid = self.root / 'invalid.nupkg'
        invalid.write_text('HTTP error document')
        self.environment['DOWNLOADED_FIXTURE'] = invalid.as_posix()
        self.verify(False)

    def test_transport_failure(self):
        self.environment['TRANSPORT_MODE'] = 'failure'
        self.verify(False)

    def test_service_index_failure(self):
        self.environment['TRANSPORT_MODE'] = 'badindex'
        self.verify(False)

    def test_missing_approved_package(self):
        (self.root / 'artifacts/approved.nupkg').unlink()
        self.verify(False)

    def test_missing_reported_content_hash(self):
        fake = self.bin / 'dotnet'
        fake.write_text('#!/usr/bin/env bash\necho "No content hash provided"\n', newline='\n')
        fake.chmod(0o755)
        self.verify(False)

    def test_multiple_reported_content_hashes(self):
        fake = self.bin / 'dotnet'
        fake.write_text('#!/usr/bin/env bash\nprintf "Content hash: a\\nContent hash: b\\n"\n', newline='\n')
        fake.chmod(0o755)
        self.verify(False)


if __name__ == '__main__':
    unittest.main(argv=[__file__] + test_args, verbosity=2)
