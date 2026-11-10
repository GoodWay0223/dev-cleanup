#!/usr/bin/env python3
"""Save a worktree's unsaved work to a new directory before the worktree is removed.

Writes only into DEST (which must not exist yet and must lie outside the worktree); never
touches the worktree, its branch or any remote. What it saves:
  tracked.diff  - uncommitted changes to tracked files (generated files and --local-patch edits left out)
  untracked/    - hand-made untracked files (generated files and --asset globs left out)
  commits.bundle - commits not in --base, when HEAD exists only on this machine
  README.txt    - HEAD, branch and how to restore
Exit status is non-zero if anything could not be saved; do not remove the worktree then.
"""

import argparse
import os
from pathlib import Path
import shutil
import sys

import worktree_report as wr


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('worktree', type=Path)
    parser.add_argument('dest', type=Path, help='New directory for the backup (outside every repository)')
    parser.add_argument('--base', default='origin/main')
    parser.add_argument('--generated', action='append', default=[])
    parser.add_argument('--asset', action='append', default=[])
    parser.add_argument('--local-patch', action='append', default=[], type=wr.parse_patch, metavar='OLD=NEW')
    args = parser.parse_args()

    tree, dest = args.worktree.resolve(), args.dest.resolve()
    if dest == tree or tree in dest.parents:
        sys.exit('dest must be outside the worktree')
    dest.mkdir(parents=True)  # refuses to reuse an existing backup

    generated = wr.DEFAULT_GENERATED + args.generated
    tracked = [p for _, p in wr.status_entries(tree, False) if not wr.matches(p, generated)]
    tracked = [p for p in tracked if not (args.local_patch and wr.only_local_patch(tree, p, args.local_patch))]
    if tracked:
        diff = wr.git(tree, 'diff', '--binary', 'HEAD', '--', *tracked).stdout
        (dest/'tracked.diff').write_bytes(diff)
        wr.git(tree, 'apply', '--reverse', '--check', str(dest/'tracked.diff'))  # the diff must round-trip

    others = wr.git(tree, 'ls-files', '--others', '--exclude-standard', '-z').stdout.decode().split('\0')
    copied = []
    for rel in filter(None, others):
        if wr.matches(rel, generated) or wr.matches(rel, args.asset) or \
                any(wr.matches(str(parent), generated + args.asset) for parent in Path(rel).parents):
            continue
        src, target = tree/rel, dest/'untracked'/rel
        if src.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(os.readlink(src), target)
        elif src.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            if target.stat().st_size != src.stat().st_size:
                sys.exit(f'copy mismatch: {rel}')
        copied.append(rel)

    head = wr.git(tree, 'rev-parse', 'HEAD').stdout.decode().strip()
    branch = wr.git(tree, 'branch', '--show-current').stdout.decode().strip()
    bundled = False
    if wr.git(tree, 'merge-base', '--is-ancestor', head, args.base, valid=(0, 1)).returncode == 1 and \
            not wr.git(tree, 'branch', '-r', '--contains', head).stdout.strip():
        wr.git(tree, 'bundle', 'create', str(dest/'commits.bundle'), 'HEAD', '--not', args.base)
        wr.git(tree, 'bundle', 'verify', str(dest/'commits.bundle'))
        bundled = True

    (dest/'README.txt').write_text(
        f'worktree: {tree}\nHEAD: {head}\nbranch: {branch or "(detached)"}\n'
        f'tracked changes: {len(tracked)}\nuntracked files: {len(copied)}\ncommits bundle: {bundled}\n\n'
        'restore:\n'
        f'  git worktree add <path> {head}   (fetch commits.bundle first if present)\n'
        '  git -C <path> apply tracked.diff\n'
        '  cp -R untracked/. <path>/\n', encoding='utf-8')
    print(f'{tree.name}: {len(tracked)} tracked, {len(copied)} untracked, bundle={bundled} -> {dest}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
