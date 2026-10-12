#!/usr/bin/env python3
"""Behavior checks using an isolated temporary repository; no user-file deletion."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import audit_paths as audit


class AuditBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mac-dev-cleanup-validation-')
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root/'project'
        self.repo.mkdir()
        self.cache = self.repo/'.cache'
        self.cache.mkdir()
        self.output = self.cache/'generated.bin'
        self.output.write_bytes(b'regenerable sample')
        (self.repo/'.gitignore').write_text('.cache/\n')
        self.source = self.repo/'source.txt'
        self.source.write_text('source remains intact\n')
        self.git('init', '-q')
        self.git('add', '.gitignore', 'source.txt')
        self.git('-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null',
                 '-c', 'user.name=Cleanup Validation', '-c', 'user.email=cleanup-test@example.invalid',
                 'commit', '-qm', 'Isolated validation fixture')

    def tearDown(self):
        # TemporaryDirectory owns only the fixtures created by this test.
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args],
                              check=True, capture_output=True)

    def snapshot(self, path):
        result = audit.audit([str(path)], 1000)
        self.assertFalse(result['errors'], result['errors'])
        return result

    def test_ignored_generated_cache_is_read_only(self):
        before = self.output.read_bytes()
        result = self.snapshot(self.cache)
        self.assertTrue(result['items'][0]['review_ready'], result['items'][0])
        self.assertEqual(before, self.output.read_bytes())
        self.assertEqual(self.source.read_text(), 'source remains intact\n')

    def test_tracked_file_is_blocked(self):
        item = self.snapshot(self.source)['items'][0]
        self.assertFalse(item['review_ready'])
        self.assertEqual(item['tracked_count'], 1)

    def test_unignored_directory_is_blocked(self):
        output = self.repo/'unconfirmed-output'
        output.mkdir()
        (output/'file.bin').write_bytes(b'could be user work')
        item = self.snapshot(output)['items'][0]
        self.assertFalse(item['review_ready'])
        self.assertFalse(item['all_files_git_ignored'])

    def test_result_bundle_and_dependencies_block_parent(self):
        for name in ('Test.xcresult', 'SourcePackages', 'node_modules'):
            protected = self.cache/name
            protected.mkdir()
            (protected/'keep.bin').write_bytes(b'valuable')
        item = self.snapshot(self.cache)['items'][0]
        self.assertFalse(item['review_ready'])
        self.assertEqual(len(item['protected']), 3)
        self.assertTrue((self.cache/'Test.xcresult/keep.bin').exists())

    def test_case_variants_and_windows_release_outputs_are_preserved(self):
        for name in ('NODE_MODULES', 'NuGet-packages', 'Published'):
            folder = self.cache/name
            folder.mkdir()
            (folder/'release.EXE').write_bytes(b'unique release')
        item = self.snapshot(self.cache)['items'][0]
        self.assertFalse(item['review_ready'])
        self.assertTrue(item['protected'])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows directory junction boundary')
    def test_windows_junction_is_not_followed(self):
        target = self.root/'valuable-folder'
        target.mkdir()
        (target/'keep.txt').write_text('unique data')
        link = self.cache/'junction'
        subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(target)],
                       check=True, capture_output=True)
        try:
            item = self.snapshot(self.cache)['items'][0]
            self.assertFalse(item['review_ready'])
            self.assertIn(str(link), item['symlinks'])
            self.assertEqual((target/'keep.txt').read_text(), 'unique data')
        finally:
            link.rmdir()

    def test_untracked_content_change_is_detected(self):
        draft = self.repo/'unfinished.txt'
        draft.write_text('original uncommitted work')
        before = self.snapshot(self.cache)
        draft.write_text('changed uncommitted work')
        after = self.snapshot(self.cache)
        self.assertNotEqual(before['repository_states'], after['repository_states'])

    @unittest.skipIf(sys.platform == 'win32', 'Creating symlinks needs Windows privileges; production reparse checks still apply')
    def test_nested_symlink_is_not_followed(self):
        target = self.root/'valuable-outside.bin'
        target.write_bytes(b'valuable')
        (self.cache/'shortcut').symlink_to(target)
        item = self.snapshot(self.cache)['items'][0]
        self.assertFalse(item['review_ready'])
        self.assertEqual(item['symlinks'], [str(self.cache/'shortcut')])
        self.assertEqual(target.read_bytes(), b'valuable')

    def test_open_file_is_blocked(self):
        with self.output.open('rb'):
            item = self.snapshot(self.cache)['items'][0]
            self.assertFalse(item['review_ready'])
            self.assertTrue(any(f['path'] == str(self.output) for f in item['open_files']))

    def test_open_writer_is_blocked(self):
        with self.output.open('ab'):
            item = self.snapshot(self.cache)['items'][0]
            self.assertFalse(item['review_ready'])
            self.assertTrue(any(f['path'] == str(self.output) for f in item['open_files']))

    def test_unknown_open_file_state_blocks_every_candidate(self):
        with patch.object(audit, 'open_files', side_effect=RuntimeError('inventory unavailable')):
            result = audit.audit([str(self.cache)], 1000)
        self.assertTrue(result['errors'])
        self.assertFalse(result['items'][0]['review_ready'])

    def test_verify_refuses_changed_output_or_source(self):
        script = Path(audit.__file__).resolve()
        for change in ('output', 'source'):
            before = self.snapshot(self.cache)
            report = self.root/f'{change}-audit.json'
            audit.save(report, before, [str(self.cache)])
            good = subprocess.run([sys.executable, str(script), 'verify', '--audit', str(report)],
                                  capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
            if change == 'output':
                self.output.write_bytes(b'new build changed candidate')
            else:
                self.source.write_text('new uncommitted work\n')
            refused = subprocess.run([sys.executable, str(script), 'verify', '--audit', str(report)],
                                     capture_output=True, text=True)
            self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
            self.assertFalse(json.loads(refused.stdout)['unchanged_and_review_ready'])

    def test_reports_cannot_replace_files_or_live_in_candidates(self):
        result = self.snapshot(self.cache)
        with self.assertRaises(ValueError):
            audit.save(self.cache/'report.json', result, [str(self.cache)])
        with self.assertRaises(FileExistsError):
            audit.save(self.source, result, [str(self.cache)])
        with self.assertRaises(ValueError):
            audit.save(self.repo/'private-report.json', result, [str(self.cache)])
        self.assertEqual(self.source.read_text(), 'source remains intact\n')

    def test_unicode_candidate_and_report_are_portable_utf8(self):
        candidate = self.cache/'测试-缓存.bin'
        candidate.write_bytes(b'regenerable sample')
        result = self.snapshot(candidate)
        report = self.root/'审计.json'
        audit.save(report, result, [str(candidate)])
        self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['items'][0]['path'], str(candidate))
        candidate.write_bytes(b'changed build output')
        verification = subprocess.run([sys.executable, str(Path(audit.__file__).resolve()), 'verify', '--audit', str(report)],
                                      capture_output=True, text=True,
                                      env={**os.environ, 'PYTHONIOENCODING': 'ascii'})
        self.assertEqual(verification.returncode, 2, verification.stdout + verification.stderr)
        self.assertIn(str(candidate), json.loads(verification.stdout)['changed_or_blocked_paths'])

    def test_sibling_worktree_uncommitted_work_is_snapshotted(self):
        sibling = self.root/'other-checkout'
        self.git('worktree', 'add', '-qb', 'isolated-sibling', str(sibling))
        before = self.snapshot(self.cache)
        self.assertIn(str(sibling), before['repository_states'])
        (sibling/'source.txt').write_text('uncommitted sibling work\n')
        after = self.snapshot(self.cache)
        self.assertNotEqual(before['repository_states'][str(sibling)],
                            after['repository_states'][str(sibling)])
        self.assertEqual(self.source.read_text(), 'source remains intact\n')


if __name__ == '__main__':
    unittest.main()
