#!/usr/bin/env python3
"""Behavior checks for worktree_report.py on isolated temporary repositories; nothing real is touched."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import worktree_report as wr

HAS_LSOF = os.name != 'nt' and shutil.which('lsof') is not None

GIT_ID = ['-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=' + os.devnull,
          '-c', 'user.name=Cleanup Validation', '-c', 'user.email=cleanup-test@example.invalid']


def args(**overrides):
    values = dict(base='origin/main', gh=None, idle_hours=24, cache_idle_hours=72, keep=[],
                  generated=[], asset=[], local_patch=[], skip_dir=[], backup_files=5, backup_limit=256 * 1024,
                  max_nodes=100000, json=None)
    values.update(overrides)
    return argparse.Namespace(**values)


class WorktreeReport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dev-cleanup-worktrees-')
        root = Path(self.temp.name).resolve()
        self.remote = root/'remote.git'
        self.main = root/'main'
        self.wt = root/'wt'
        self.wt.mkdir()
        self.run_git(root, 'init', '-q', '--bare', '-b', 'main', str(self.remote))
        self.run_git(root, 'clone', '-q', str(self.remote), str(self.main))
        (self.main/'src.gd').write_text('extends Node\n')
        (self.main/'.gitignore').write_text('.godot/\n')
        self.run_git(self.main, 'checkout', '-q', '-b', 'main')
        self.run_git(self.main, 'add', '.')
        self.commit(self.main, 'base')
        self.run_git(self.main, 'push', '-q', 'origin', 'main')

    def tearDown(self):
        self.temp.cleanup()

    def run_git(self, cwd, *a):
        return subprocess.run(['git', *GIT_ID, *a], cwd=cwd, check=True, capture_output=True)

    def commit(self, cwd, message):
        self.run_git(cwd, 'commit', '-qm', message)

    def add_worktree(self, name, branch=None):
        path = self.wt/name
        extra = ['-b', branch] if branch else ['--detach']
        self.run_git(self.main, 'worktree', 'add', '-q', *extra, str(path), 'origin/main')
        return path

    def age(self, path, hours=48):
        old = time.time() - hours * 3600
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d != '.git']
            for f in filenames:
                os.utime(os.path.join(dirpath, f), (old, old))

    def verdicts(self, **overrides):
        if HAS_LSOF:
            rep = wr.report(self.main, args(**overrides))
        else:
            # Without an open-file inventory every worktree is kept; simulate an empty one here.
            with patch.object(wr, 'open_paths', return_value=[]):
                rep = wr.report(self.main, args(**overrides))
        return {w['name']: w for w in rep['worktrees']}, {b['branch']: b for b in rep['branches']}

    def test_clean_worktree_in_base_is_removable(self):
        self.age(self.add_worktree('clean'))
        trees, _ = self.verdicts()
        self.assertEqual(trees['clean']['verdict'], 'removable', trees['clean'])
        self.assertEqual(trees['clean']['head_safety'], 'in_base')
        self.assertTrue((self.wt/'clean').exists(), 'report must not delete anything')

    def test_generated_engine_files_do_not_block(self):
        path = self.add_worktree('godot')
        (path/'src.gd.uid').write_text('uid://x\n')
        (path/'.godot').mkdir()
        (path/'.godot'/'imported.bin').write_bytes(b'cache')
        self.age(path)
        trees, _ = self.verdicts()
        self.assertEqual(trees['godot']['verdict'], 'removable', trees['godot'])

    def test_dependency_install_is_not_handmade(self):
        path = self.add_worktree('deps')
        (path/'node_modules'/'pkg').mkdir(parents=True)
        (path/'node_modules'/'pkg'/'index.js').write_text('module.exports = 1\n')
        self.age(path)
        trees, _ = self.verdicts()
        self.assertEqual(trees['deps']['verdict'], 'removable', trees['deps'])

    def test_repeatable_local_patch_is_not_work(self):
        patched = self.add_worktree('patched')
        (patched/'src.gd').write_text('extends Node3D\n')
        self.age(patched)
        mixed = self.add_worktree('mixed')
        (mixed/'src.gd').write_text('extends Node3D\n# real edit\n')
        self.age(mixed)
        subs = [wr.parse_patch('Node=Node3D')]
        trees, _ = self.verdicts(local_patch=subs)
        self.assertEqual(trees['patched']['verdict'], 'removable', trees['patched'])
        self.assertEqual(trees['patched']['local_patch_only'], 1)
        self.assertEqual(trees['mixed']['verdict'], 'keep')
        self.assertEqual(trees['mixed']['tracked_changes'], 1)
        trees, _ = self.verdicts()
        self.assertEqual(trees['patched']['verdict'], 'keep', 'without --local-patch the edit is work')

    def test_tracked_change_blocks(self):
        path = self.add_worktree('dirty')
        (path/'src.gd').write_text('extends Node2D\n')
        self.age(path)
        trees, _ = self.verdicts()
        self.assertEqual(trees['dirty']['verdict'], 'keep')
        self.assertEqual(trees['dirty']['tracked_changes'], 1)

    def test_recent_change_blocks(self):
        self.add_worktree('fresh')
        trees, _ = self.verdicts()
        self.assertEqual(trees['fresh']['verdict'], 'keep')
        self.assertTrue(any('ago' in r for r in trees['fresh']['keep_reasons']))

    def test_local_only_commit_blocks_and_branch_is_kept(self):
        path = self.add_worktree('local', branch='feature/local')
        (path/'new.gd').write_text('extends Node\n')
        self.run_git(path, 'add', 'new.gd')
        self.commit(path, 'local work')
        self.age(path)
        trees, _ = self.verdicts()
        self.assertEqual(trees['local']['head_safety'], 'local_only')
        self.assertEqual(trees['local']['verdict'], 'keep')

    def test_pushed_branch_is_removable_and_detached_branch_deletable(self):
        path = self.add_worktree('pushed', branch='feature/pushed')
        (path/'new.gd').write_text('extends Node\n')
        self.run_git(path, 'add', 'new.gd')
        self.commit(path, 'pushed work')
        self.run_git(path, 'push', '-q', 'origin', 'feature/pushed')
        self.age(path)
        self.run_git(self.main, 'branch', 'old-merged', 'origin/main')
        self.run_git(self.main, 'branch', 'unpushed', 'origin/main')
        self.run_git(self.main, 'checkout', '-q', 'unpushed')
        (self.main/'x.gd').write_text('extends Node\n')
        self.run_git(self.main, 'add', 'x.gd')
        self.commit(self.main, 'only here')
        self.run_git(self.main, 'checkout', '-q', 'main')
        trees, branches = self.verdicts()
        self.assertEqual(trees['pushed']['head_safety'], 'on_remote')
        self.assertEqual(trees['pushed']['verdict'], 'removable')
        self.assertEqual(branches['old-merged']['verdict'], 'deletable')
        self.assertEqual(branches['unpushed']['verdict'], 'keep')
        self.assertNotIn('feature/pushed', branches, 'checked-out branches are never listed')

    def test_small_untracked_script_needs_backup_large_set_blocks(self):
        small = self.add_worktree('small')
        (small/'probe.gd').write_text('# debug probe\n')
        self.age(small)
        many = self.add_worktree('many')
        for i in range(7):
            (many/f'notes{i}.md').write_text('work\n')
        self.age(many)
        trees, _ = self.verdicts()
        self.assertEqual(trees['small']['verdict'], 'removable_after_backup')
        self.assertEqual(trees['small']['backup_first'], ['probe.gd'])
        self.assertEqual(trees['many']['verdict'], 'keep')

    def test_asset_glob_and_keep_list(self):
        path = self.add_worktree('assets')
        (path/'data').mkdir()
        (path/'data'/'city.bin').write_bytes(b'downloaded')
        self.age(path)
        self.age(self.add_worktree('tooling'))
        trees, _ = self.verdicts(asset=['data'], keep=['tooling'])
        self.assertEqual(trees['assets']['verdict'], 'removable', trees['assets'])
        self.assertEqual(trees['tooling']['verdict'], 'keep')

    def test_idle_kept_worktree_lists_import_cache(self):
        path = self.add_worktree('idle')
        (path/'src.gd').write_text('changed\n')
        (path/'.godot').mkdir()
        self.age(path, hours=100)
        trees, _ = self.verdicts()
        self.assertEqual(trees['idle']['verdict'], 'keep')
        if trees['idle']['busy_pids'] == []:
            self.assertEqual(trees['idle']['cache_dirs'], [str(path/'.godot')])

    def test_unknown_open_files_block(self):
        self.age(self.add_worktree('unknown'))
        with patch.object(wr, 'open_paths', return_value=None):
            rep = wr.report(self.main, args())
        self.assertEqual(rep['worktrees'][0]['verdict'], 'keep')

    @unittest.skipUnless(HAS_LSOF, 'lsof inventory is POSIX only')
    def test_process_with_cwd_inside_blocks(self):
        path = self.add_worktree('busy')
        self.age(path)
        holder = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], cwd=path)
        try:
            time.sleep(0.5)
            trees, _ = self.verdicts()
        finally:
            holder.kill()
            holder.wait()
        self.assertEqual(trees['busy']['verdict'], 'keep')
        self.assertIn(str(holder.pid), trees['busy']['busy_pids'])

    def test_missing_directory_is_stale_record_only(self):
        path = self.add_worktree('gone')
        shutil.rmtree(path)
        trees, _ = self.verdicts()
        self.assertEqual(trees['gone']['verdict'], 'stale_record')


if __name__ == '__main__':
    unittest.main()
