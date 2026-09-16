"""Deterministic tests; no deployment, network access or real credentials."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load('check-documentation')
wrapper = load('deploy-with-documentation')


class DocumentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Documentation test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('remote', 'add', 'origin', 'https://github.com/roger704/example.git')
        (self.root / '.nexus').mkdir()
        (self.root / 'docs').mkdir()
        (self.root / 'changelogs').mkdir()
        for name in ['README.md', 'docs/API.md', 'changelogs/README.md']:
            (self.root / name).write_text('# Example\n\nA meaningful fixture document with setup and operational instructions.\n')
        self.config = {'schema_version': 1, 'documentation': {'required': ['README.md'], 'api': ['docs/API.md'], 'operational_notes': []}, 'deployments': [], 'manual_environments': ['test']}
        self.save_config()
        self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()

    def save_config(self):
        (self.root / '.nexus/project.json').write_text(json.dumps(self.config))

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        return self.git('rev-parse', 'HEAD')

    def call(self, arguments, sender):
        with patch.dict(os.environ, {wrapper.TOKEN_NAME: 'test-only-token'}), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return wrapper.main(['--root', str(self.root), *arguments], sender=sender)

    def run_args(self, code='pass'):
        return ['run', '--environment', 'test', '--evidence-url', 'https://example.invalid/run/1', '--operational-notes', 'No migration; test fixture only.', '--', sys.executable, '-c', code]

    def receipts(self):
        return list((self.root / '.git/nexus-deployment-outbox').glob('*.json'))

    def test_required_api_and_changelog_content_checked(self):
        self.assertTrue(gate.check(self.root)['ok'])
        for name in ['README.md', 'docs/API.md', 'changelogs/README.md']:
            path = self.root / name
            before = path.read_text()
            path.write_text('<!-- ' + 'placeholder' * 20 + ' -->')
            with self.assertRaises(ValueError):
                gate.check(self.root)
            path.write_text(before)

    def test_missing_declared_api_fails(self):
        (self.root / 'docs/API.md').unlink()
        with self.assertRaises(ValueError):
            gate.check(self.root)

    def test_symlink_and_traversal_are_rejected(self):
        path = self.root / 'docs/API.md'
        path.unlink()
        path.symlink_to(self.root / 'README.md')
        with self.assertRaises(ValueError):
            gate.check(self.root)
        self.config['documentation']['api'] = ['docs/../README.md']
        self.save_config()
        with self.assertRaises(ValueError):
            gate.check(self.root)

    def test_config_symlink_is_rejected(self):
        path = self.root / '.nexus/project.json'
        copy = self.root / 'config.json'
        copy.write_text(path.read_text())
        path.unlink()
        path.symlink_to(copy)
        with self.assertRaises(ValueError):
            gate.check(self.root)

    def test_changed_api_and_migration_signal_review_without_semantic_claim(self):
        before = self.git('rev-parse', 'HEAD')
        (self.root / 'routes.py').write_text('# changed API\n')
        (self.root / 'migrations.sql').write_text('-- migration\n')
        self.commit()
        report = gate.check(self.root, before)
        self.assertTrue(report['documentation_review_required'])
        self.assertTrue(report['api_review_required'])
        self.assertTrue(report['operational_review_required'])
        self.assertEqual(report['documentation_changed'], [])

    def test_invalid_base_fails_closed(self):
        with self.assertRaises(ValueError):
            gate.check(self.root, '--help')
        with self.assertRaises(ValueError):
            gate.check(self.root, '0' * 40)

    def test_dirty_or_unenrolled_prevents_command_and_report(self):
        marker = self.root / 'executed'
        (self.root / 'untracked').write_text('dirty')
        calls = []
        args = self.run_args('from pathlib import Path; Path("executed").touch()')
        self.assertEqual(self.call(args, lambda *x: calls.append(x)), 3)
        self.assertFalse(marker.exists())
        (self.root / 'untracked').unlink()
        self.config['manual_environments'] = []
        self.save_config()
        self.commit()
        self.assertEqual(self.call(args, lambda *x: calls.append(x)), 3)
        self.assertFalse(marker.exists())
        self.assertEqual(calls, [])

    def test_success_token_not_forwarded_and_exact_source_recorded(self):
        calls = []
        sha = self.git('rev-parse', 'HEAD')
        result = self.call(self.run_args('import os; assert "NEXUS_DEPLOYMENT_REPORT_TOKEN" not in os.environ'), lambda body, token: calls.append(dict(body)))
        self.assertEqual(result, 0)
        self.assertEqual(calls[0]['source_sha'], sha)
        self.assertEqual(calls[0]['outcome'], 'success')
        self.assertEqual(calls[0]['repository'], 'roger704/example')
        self.assertEqual(json.loads(self.receipts()[0].read_text())['state'], 'accepted')

    def test_source_mutation_cannot_claim_success_for_original_revision(self):
        calls = []
        result = self.call(self.run_args('from pathlib import Path; Path("README.md").write_text("changed source")'), lambda body, token: calls.append(dict(body)))
        self.assertNotEqual(result, 0)
        self.assertEqual(calls[0]['outcome'], 'failure')
        self.assertIn('requires reconciliation', calls[0]['operational_notes'])

    def test_failed_command_is_reported_as_failure(self):
        calls = []
        result = self.call(self.run_args('raise SystemExit(7)'), lambda body, token: calls.append(dict(body)))
        self.assertEqual(result, 7)
        self.assertEqual(calls[0]['outcome'], 'failure')

    def test_report_failure_retains_receipt_and_replay_never_reruns(self):
        marker = self.root / '.git/command-count'
        code = 'from pathlib import Path; p=Path(".git/command-count"); p.write_text(p.read_text()+"x" if p.exists() else "x")'
        def unavailable(body, token):
            raise ValueError('unavailable')
        self.assertEqual(self.call(self.run_args(code), unavailable), 3)
        record = json.loads(self.receipts()[0].read_text())
        self.assertEqual(record['state'], 'pending')
        calls = []
        self.assertEqual(self.call(['replay', record['body']['deployment_id']], lambda body, token: calls.append(dict(body))), 0)
        self.assertEqual(marker.read_text(), 'x')
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.call(['replay', record['body']['deployment_id']], lambda *x: calls.append(x)), 0)
        self.assertEqual(len(calls), 1)

    def test_running_receipt_cannot_be_replayed_as_success(self):
        folder = self.root / '.git/nexus-deployment-outbox'
        folder.mkdir()
        deployment_id = '00000000-0000-0000-0000-000000000001'
        (folder / (deployment_id + '.json')).write_text(json.dumps({'state': 'running', 'body': {}}))
        calls = []
        self.assertEqual(self.call(['replay', deployment_id], lambda *x: calls.append(x)), 3)
        self.assertEqual(calls, [])

    def test_evidence_url_rejects_plain_http_or_credentials(self):
        for url in ['http://example.invalid', 'https://secret@example.invalid']:
            with self.assertRaises(ValueError):
                wrapper.validate_evidence(url)

    def test_report_redirect_refused(self):
        with self.assertRaises(ValueError):
            wrapper.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid')


if __name__ == '__main__':
    unittest.main()
