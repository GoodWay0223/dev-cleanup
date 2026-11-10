#!/usr/bin/env python3
"""Read-only report on Git worktrees and local branches left behind by AI coding agents.

It never deletes, moves, fetches or rewrites anything. Each worktree gets a verdict:
"removable" only when every check passes, otherwise "keep" with the reasons.
The verdict is evidence for review, not deletion permission.
"""

import argparse
import datetime as dt
import fnmatch
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

DEFAULT_GENERATED = ['*.import', '*.uid', '.godot', '.godot/*', '*/.godot', '*/.godot/*',
                     '.DS_Store', '*/.DS_Store',
                     # Dependency installs and bytecode are rebuilt from lock files / sources.
                     'node_modules', '*/node_modules', '__pycache__', '*/__pycache__']
# Large regenerable trees that are skipped when looking for the newest hand-made change.
DEFAULT_SKIP_DIRS = {'.git', '.godot', 'node_modules', 'Library', 'Temp', '.gradle',
                     '.venv', 'venv', 'DerivedData', '__pycache__', '.next', '.turbo'}
# Engine / tool import caches that can be dropped from an idle worktree while keeping its code.
CACHE_DIR_CANDIDATES = ['.godot', 'game/.godot', 'Library', 'Temp', 'obj', '.gradle', 'DerivedData']


def run(args, cwd=None, valid=(0,)):
    result = subprocess.run(args, cwd=cwd, capture_output=True, timeout=120,
                            env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0'})
    if result.returncode not in valid:
        raise RuntimeError(f"{' '.join(args[:3])} failed (exit {result.returncode}): "
                           f"{result.stderr.decode(errors='replace').strip()[:200]}")
    return result


def git(repo, *args, valid=(0,)):
    return run(['git', '-C', str(repo), *args], valid=valid)


def matches(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def list_worktrees(repo):
    out = git(repo, 'worktree', 'list', '--porcelain', '-z').stdout.decode()
    trees, current = [], {}
    for field in out.split('\0'):
        if not field:
            if current:
                trees.append(current)
                current = {}
            continue
        key, _, value = field.partition(' ')
        current[key] = value or True
    if current:
        trees.append(current)
    return trees


def open_paths():
    """(pid, path) for open files and process cwds; None when the inventory is unavailable."""
    if os.name == 'nt' or not shutil.which('lsof'):
        return None
    result = subprocess.run(['lsof', '-nP', '-Fpn'], capture_output=True, timeout=120)
    if not result.stdout:
        return None
    me = {str(os.getpid()), str(os.getppid())}
    records, pid = [], None
    for line in result.stdout.decode(errors='replace').splitlines():
        if line.startswith('p'):
            pid = line[1:]
        elif line.startswith('n/') and pid not in me:
            records.append((pid, line[1:]))
    return records


def busy_pids(path, opened):
    if opened is None:
        return None
    root = str(path).rstrip('/') + '/'
    return sorted({pid for pid, p in opened if p == str(path) or p.startswith(root)})


def newest_change(path, skip_dirs, max_nodes):
    """Newest mtime (epoch seconds) of a hand-made file, skipping regenerable trees."""
    newest, nodes, pending = 0.0, 0, [str(path)]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                nodes += 1
                if nodes > max_nodes:
                    return None
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir():
                        if entry.name not in skip_dirs:
                            pending.append(entry.path)
                    elif entry.name != '.git':
                        newest = max(newest, entry.stat(follow_symlinks=False).st_mtime)
                except OSError:
                    return None
    return newest


def status_entries(tree, untracked):
    flag = '--untracked-files=normal' if untracked else '--untracked-files=no'
    out = git(tree, 'status', '--porcelain=v1', '-z', flag).stdout.decode(errors='replace')
    entries, parts, i = [], out.split('\0'), 0
    while i < len(parts):
        item = parts[i]
        i += 1
        if len(item) < 4:
            continue
        code, path = item[:2], item[3:]
        if code[0] in 'RC':
            i += 1  # skip the rename source
        entries.append((code, path))
    return entries


def parse_patch(spec):
    old, sep, new = spec.partition('=')
    if not sep or not old:
        raise argparse.ArgumentTypeError('expected OLD=NEW')
    return old.encode(), new.encode()


def only_local_patch(tree, rel, subs):
    """True when the working file is exactly HEAD's version with the given substitutions applied."""
    target = tree/rel
    if target.is_symlink() or not target.is_file():
        return False
    result = git(tree, 'show', f'HEAD:{rel}', valid=(0, 128))
    if result.returncode != 0:
        return False
    expected = result.stdout
    for old, new in subs:
        expected = expected.replace(old, new)
    try:
        return target.read_bytes() == expected and expected != result.stdout
    except OSError:
        return False


def head_safety(tree, head, base, gh_repo, branch):
    if git(tree, 'merge-base', '--is-ancestor', head, base, valid=(0, 1)).returncode == 0:
        return 'in_base'
    if git(tree, 'branch', '-r', '--contains', head).stdout.strip():
        return 'on_remote'
    cherry = git(tree, 'cherry', base, head).stdout.decode()
    if cherry and not any(line.startswith('+') for line in cherry.splitlines()):
        return 'patch_in_base'
    if gh_repo and branch and pr_state(gh_repo, branch) == 'MERGED':
        return 'pr_merged'
    return 'local_only'


_pr_cache = {}


def pr_state(gh_repo, branch):
    key = (gh_repo, branch)
    if key not in _pr_cache:
        state = None
        if shutil.which('gh'):
            result = subprocess.run(['gh', 'pr', 'list', '-R', gh_repo, '--head', branch, '--state', 'all',
                                     '--json', 'state', '-q', '.[0].state'], capture_output=True, timeout=60)
            state = result.stdout.decode().strip() or None if result.returncode == 0 else None
        _pr_cache[key] = state
    return _pr_cache[key]


def inspect_worktree(record, base, args, opened, now):
    path = Path(record['worktree'])
    branch = record.get('branch', '')
    branch = branch[len('refs/heads/'):] if isinstance(branch, str) and branch.startswith('refs/heads/') else ''
    info = {'path': str(path), 'name': path.name, 'branch': branch or None,
            'head': record.get('HEAD'), 'keep_reasons': [], 'backup_first': [], 'cache_dirs': []}
    if record.get('prunable') or not path.is_dir():
        info['verdict'] = 'stale_record'
        info['keep_reasons'].append('missing directory: only `git worktree prune` applies')
        return info
    reasons = info['keep_reasons']
    if path.name in args.keep or str(path) in args.keep:
        reasons.append('named as always-keep')
    if record.get('locked'):
        reasons.append('worktree is locked')
    pids = busy_pids(path, opened)
    info['busy_pids'] = pids
    if pids is None:
        reasons.append('open-file inventory unavailable')
    elif pids:
        reasons.append(f'in use by pid {", ".join(pids[:5])}')
    newest = newest_change(path, set(args.skip_dir) | DEFAULT_SKIP_DIRS, args.max_nodes)
    info['idle_hours'] = None if newest is None else round((now - newest) / 3600, 1)
    if newest is None:
        reasons.append('could not determine last change')
    elif info['idle_hours'] < args.idle_hours:
        reasons.append(f'changed {info["idle_hours"]}h ago (< {args.idle_hours}h)')
    generated = DEFAULT_GENERATED + args.generated
    tracked = [p for code, p in status_entries(path, False) if not matches(p, generated)]
    if args.local_patch:
        patched = [p for p in tracked if only_local_patch(path, p, args.local_patch)]
        info['local_patch_only'] = len(patched)
        tracked = [p for p in tracked if p not in patched]
    info['tracked_changes'] = len(tracked)
    work = []  # unsaved work: blocks removal unless the worktree is stale and gets a full backup
    if tracked:
        work.append(f'{len(tracked)} uncommitted tracked change(s), e.g. {tracked[0]}')
    untracked = [p for code, p in status_entries(path, True)
                 if code == '??' and not matches(p.rstrip('/'), generated)
                 and not matches(p, generated) and not matches(p.rstrip('/'), args.asset)]
    info['untracked_handmade'] = untracked
    if untracked:
        small = all((path/p).is_file() and (path/p).stat().st_size <= args.backup_limit for p in untracked)
        if small and len(untracked) <= args.backup_files:
            info['backup_first'] = untracked
        else:
            work.append(f'{len(untracked)} untracked hand-made path(s), e.g. {untracked[0]}')
    safety = head_safety(path, info['head'], base, args.gh, branch) if info['head'] else 'unknown'
    info['head_safety'] = safety
    if safety == 'unknown':
        reasons.append('HEAD commit could not be checked')
    elif safety == 'local_only':
        work.append('HEAD commit exists only on this machine')
    idle = info['idle_hours']
    stale = args.stale_hours is not None and idle is not None and idle >= args.stale_hours
    if work and stale and not reasons:
        # The user allowed removing long-idle worktrees once their work is saved outside them.
        info['backup_work'] = True
        info['backup_reasons'] = work
    else:
        reasons.extend(work)
    if reasons:
        info['verdict'] = 'keep'
        idle = info['idle_hours']
        if (pids == [] and idle is not None and idle >= args.cache_idle_hours
                and path.name not in args.keep):
            info['cache_dirs'] = [str(path/c) for c in CACHE_DIR_CANDIDATES if (path/c).is_dir()]
    else:
        backup = info['backup_first'] or info.get('backup_work')
        info['verdict'] = 'removable_after_backup' if backup else 'removable'
    return info


def inspect_branches(repo, base, checked_out, gh_repo):
    rows = []
    refs = git(repo, 'for-each-ref', '--format=%(refname:short)', 'refs/heads').stdout.decode().split()
    base_name = base.split('/', 1)[-1]
    for b in refs:
        if b in checked_out or b == base_name:
            continue
        cherry = git(repo, 'cherry', base, b).stdout.decode()
        if not any(line.startswith('+') for line in cherry.splitlines()):
            why = 'all commits in base'
        elif git(repo, 'branch', '-r', '--contains', b).stdout.strip():
            why = 'tip is on a remote branch'
        elif gh_repo and pr_state(gh_repo, b) == 'MERGED':
            why = 'PR merged'
        else:
            rows.append({'branch': b, 'verdict': 'keep', 'reason': 'unpushed commits'})
            continue
        rows.append({'branch': b, 'verdict': 'deletable', 'reason': why})
    return rows


def report(repo, args):
    repo = Path(repo).resolve()
    base = args.base
    git(repo, 'rev-parse', '--verify', base + '^{commit}')
    opened = open_paths()
    now = time.time()
    trees = list_worktrees(repo)
    checked_out = {t['branch'][len('refs/heads/'):] for t in trees
                   if isinstance(t.get('branch'), str)}
    items = [inspect_worktree(t, base, args, opened, now) for t in trees[1:]]  # trees[0] = main checkout
    return {'repository': str(repo), 'base': base, 'worktrees': items,
            'branches': inspect_branches(repo, base, checked_out, args.gh)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('repo', nargs='+', help='Main checkout(s) whose worktrees to inspect')
    parser.add_argument('--base', default='origin/main', help='Integration ref (default origin/main)')
    parser.add_argument('--gh', help='owner/repo: also treat a MERGED PR for the branch as safe (needs gh)')
    parser.add_argument('--idle-hours', type=float, default=24, help='Keep worktrees changed more recently')
    parser.add_argument('--stale-hours', type=float,
                        help='Only when the user allowed it: a worktree idle this long may be removed even with '
                             'unsaved work, after backup_worktree.py saves that work (verdict removable_after_backup)')
    parser.add_argument('--cache-idle-hours', type=float, default=72,
                        help='For kept but idle worktrees, list import caches that could be dropped')
    parser.add_argument('--keep', action='append', default=[], help='Worktree name or path to always keep')
    parser.add_argument('--generated', action='append', default=[], help='Extra glob of generated files')
    parser.add_argument('--asset', action='append', default=[],
                        help='Glob of untracked downloaded assets that do not count as hand-made work')
    parser.add_argument('--local-patch', action='append', default=[], type=parse_patch, metavar='OLD=NEW',
                        help='Text substitution of a repeatable local patch that is never committed; a tracked '
                             'file equal to HEAD with these substitutions applied is not counted as work')
    parser.add_argument('--skip-dir', action='append', default=[], help='Extra directory name to skip for idle time')
    parser.add_argument('--backup-files', type=int, default=5,
                        help='At most this many small untracked files may be backed up instead of blocking')
    parser.add_argument('--backup-limit', type=int, default=256 * 1024, help='Max bytes per backed-up file')
    parser.add_argument('--max-nodes', type=int, default=400000)
    parser.add_argument('--json', type=Path, help='Write the full report here (outside any repository)')
    args = parser.parse_intermixed_args()  # repos may follow options
    reports = [report(r, args) for r in args.repo]
    if args.json:
        with args.json.open('x', encoding='utf-8') as stream:
            json.dump({'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                       'notice': 'Read-only report; a verdict is not deletion permission.',
                       'reports': reports}, stream, ensure_ascii=False, indent=2)
    for rep in reports:
        print(f"# {rep['repository']} (base {rep['base']})")
        for w in rep['worktrees']:
            extra = '; '.join(w['keep_reasons']) or ', '.join(filter(None, [w.get('head_safety')]))
            print(f"{w['verdict']:<23} {w['name']:<24} idle={w.get('idle_hours')}h  {extra}")
            if w['backup_first']:
                print(f"{'':<23}   back up first: {', '.join(w['backup_first'])}")
            if w.get('backup_work'):
                print(f"{'':<23}   stale, back up with backup_worktree.py first: {'; '.join(w['backup_reasons'])}")
            if w['cache_dirs']:
                print(f"{'':<23}   idle import caches: {', '.join(w['cache_dirs'])}")
        for b in rep['branches']:
            print(f"branch {b['verdict']:<16} {b['branch']}  ({b['reason']})")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        sys.exit(2)
