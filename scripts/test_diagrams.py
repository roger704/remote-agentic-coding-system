import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('diagrams', Path(__file__).with_name('check-diagrams.py'))
diagrams = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagrams)


class DiagramContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        (self.root / 'src').mkdir()
        (self.root / 'src/main.py').write_text('print(1)\n')
        (self.root / 'docs/diagrams').mkdir(parents=True)
        (self.root / 'docs/diagrams/README.md').write_text('# Architecture\n\n```mermaid\nflowchart LR\n A --> B\n```\n\n```mermaid\nsequenceDiagram\n A->>B: Request\n```\n\n[Source](../../src/main.py)\n')
        (self.root / '.nexus').mkdir()
        self.save({'schema_version': 1, 'documents': ['docs/diagrams/README.md'], 'source_fingerprint': '0' * 64})
        self.git('add', '.')
        diagrams.check(self.root, index=True, write=True)
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args])

    def save(self, value):
        (self.root / diagrams.MANIFEST).write_text(json.dumps(value))

    def test_index_stamp_matches_committed_tree(self):
        self.assertTrue(diagrams.check(self.root)['ok'])
        self.assertEqual(diagrams.fingerprint(self.root), diagrams.fingerprint(self.root, True))

    def test_source_change_requires_real_review_receipt(self):
        (self.root / 'src/main.py').write_text('print(2)\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'changed source')
        with self.assertRaisesRegex(ValueError, 'need source review'):
            diagrams.check(self.root)
        diagrams.check(self.root, index=True, write=True)
        self.git('add', '.')
        self.git('commit', '-qm', 'review diagram')
        self.assertTrue(diagrams.check(self.root)['ok'])

    def test_diagram_changelog_only_commits_do_not_retrigger(self):
        before = diagrams.fingerprint(self.root)
        (self.root / 'changelogs').mkdir()
        (self.root / 'changelogs/deploy.md').write_text('Deployment entry')
        with (self.root / 'docs/diagrams/README.md').open('a') as handle:
            handle.write('\nReviewed terminology.\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'diagrams and changelog')
        self.assertEqual(before, diagrams.fingerprint(self.root))

    def test_new_deleted_renamed_and_unicode_sources_change_fingerprint(self):
        before = diagrams.fingerprint(self.root)
        (self.root / 'src/ä.py').write_text('pass\n')
        self.git('add', '.')
        self.assertNotEqual(before, diagrams.fingerprint(self.root, True))
        (self.root / 'src/main.py').rename(self.root / 'src/renamed.py')
        self.git('add', '-A')
        changed = diagrams.fingerprint(self.root, True)
        self.git('commit', '-qm', 'renamed')
        self.assertEqual(changed, diagrams.fingerprint(self.root))

    def test_symlink_manifest_and_document_refused(self):
        p = self.root / 'docs/diagrams/README.md'
        p.unlink()
        p.symlink_to(self.root / 'src/main.py')
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            diagrams.check(self.root)

    def test_bad_manifest_paths_and_unknown_fields_refused(self):
        for path in ['docs/diagrams/../private.md', '.env', 'docs/diagrams/.private.md']:
            self.save({'schema_version': 1, 'documents': [path], 'source_fingerprint': '0' * 64})
            with self.assertRaises(ValueError):
                diagrams.check(self.root)
        self.save({'schema_version': 1, 'documents': [], 'source_fingerprint': '0' * 64, 'extra': True})
        with self.assertRaises(ValueError):
            diagrams.check(self.root)

    def test_unterminated_additional_diagram_is_rejected(self):
        p = self.root / 'docs/diagrams/README.md'
        p.write_text(p.read_text() + '\n```mermaid\nflowchart LR\n A --> B\n')
        with self.assertRaisesRegex(ValueError, 'Unterminated'):
            diagrams.check(self.root)

    def test_markdown_fence_variants_are_validated(self):
        self.assertEqual(len(diagrams.mermaid_blocks('~~~mermaid\nflowchart LR\n A --> B\n~~~\n')), 1)
        self.assertEqual(len(diagrams.mermaid_blocks('  ````mermaid\nflowchart LR\n A --> B\n  ````\n')), 1)

    def test_broken_evidence_and_active_directives_refused(self):
        p = self.root / 'docs/diagrams/README.md'
        original = p.read_text()
        p.write_text(original + '\n[Missing](../../absent.py)\n')
        with self.assertRaisesRegex(ValueError, 'Broken'):
            diagrams.check(self.root)
        p.write_text(original.replace(' A --> B', ' click A "javascript:alert(1)"'))
        with self.assertRaisesRegex(ValueError, 'Executable'):
            diagrams.check(self.root)


if __name__ == '__main__':
    unittest.main()
