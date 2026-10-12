#!/usr/bin/env python3
"""Read-only filesystem/Git/open-file audit. Never deletes candidate files."""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


PROTECTED_PARTS = {
    '.git', 'node_modules', '.venv', 'venv', 'vendor', 'packages', 'Pods', 'SourcePackages',
    'checkouts', 'repositories', 'references', 'reference', '.media', '.bench',
    '.runs', 'resources', 'Resources', 'assets', 'Assets.xcassets', 'fixtures',
    'test-fixtures', 'DeviceSupport', 'Archives', 'Logs', 'publish', '.vs',
}
PROTECTED_SUFFIXES = {
    '.xcresult', '.xcarchive', '.photoslibrary', '.app', '.ipa', '.dSYM',
    '.framework', '.bundle', '.sqlite', '.sqlite3', '.db', '.pem', '.key',
    '.p12', '.mobileprovision', '.exe', '.dll', '.pdb', '.msix', '.msi',
}
SOURCE_SUFFIXES = {'.swift', '.ts', '.tsx', '.js', '.jsx', '.py', '.rs', '.go',
                   '.c', '.h', '.m', '.mm', '.kt', '.java', '.toml', '.yaml', '.yml'}
PROTECTED_NAMES = {'info.plist', 'package.json', 'package-lock.json', 'pnpm-lock.yaml',
                   'yarn.lock', 'Cargo.lock', 'Package.resolved', 'manifest.json',
                   'AGENTS.md', 'SKILL.md'}


def contained(path, root):
    return path == root or root in path.parents


def protection(path, is_file=False):
    home = Path.home().resolve()
    broad = [Path('/'), home, home/'Documents', home/'Desktop', home/'Downloads',
             home/'Movies', home/'Library', home/'.codex', home/'.codex/worktrees',
             home/'Library/Developer/Xcode/DerivedData',
             home/'Library/Developer/CoreSimulator/Devices',
             home/'Library/Caches']
    if path in broad:
        return 'broad_root'
    if os.name == 'nt':
        if path == Path(path.anchor) or str(path).startswith('\\\\'):
            return 'drive_root_or_network_path'
        for variable in ('WINDIR', 'PROGRAMFILES', 'PROGRAMFILES(X86)'):
            root = os.environ.get(variable)
            if root and contained(path, Path(root).resolve()):
                return 'windows_system_or_installed_program'
        if any(part.lower() in {'$recycle.bin', 'system volume information'} for part in path.parts):
            return 'windows_system_data'
    for rel in ('sessions', 'memories', 'skills', 'plugins', 'attachments'):
        if contained(path, home/'.codex'/rel):
            return 'codex_persistent_data'
    if any(part.casefold() in {p.casefold() for p in PROTECTED_PARTS}
           or Path(part).suffix.casefold() in {s.casefold() for s in PROTECTED_SUFFIXES}
           for part in path.parts):
        return 'protected_content'
    if path.name.casefold() in {n.casefold() for n in PROTECTED_NAMES} or path.name == '.env' or path.name.startswith('.env.'):
        return 'source_metadata_or_configuration'
    if is_file and path.suffix.casefold() in SOURCE_SUFFIXES:
        return 'source_or_configuration_file'
    if any(ord(c) < 32 for c in str(path)):
        return 'unsupported_control_character_in_path'
    return None


def run(args, valid=(0,), input_bytes=None):
    result = subprocess.run(args, input=input_bytes, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=60,
                            env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
    if result.returncode not in valid:
        raise RuntimeError(f'{args[0]} failed (exit {result.returncode})')
    return result


def git(repo, *args, valid=(0,), input_bytes=None):
    return run(['git', '-C', str(repo), *args], valid, input_bytes).stdout


def repo_for(path):
    parent = path if path.is_dir() else path.parent
    result = run(['git', '-C', str(parent), 'rev-parse', '--show-toplevel'], (0, 128))
    if result.returncode == 128:
        # Distinguish a non-repository from a damaged/inaccessible repository.
        if b'not a git repository' in result.stderr.lower():
            return None
        raise RuntimeError('Cannot determine Git repository')
    return Path(os.fsdecode(result.stdout).strip()).resolve()


def repo_state(repo):
    commands = {
        'head': ('rev-parse', 'HEAD'),
        'status': ('status', '--porcelain=v1', '--untracked-files=all', '-z'),
        'working_diff': ('diff', '--no-ext-diff', '--no-textconv', '--binary'),
        'staged_diff': ('diff', '--cached', '--no-ext-diff', '--no-textconv', '--binary'),
        'refs': ('show-ref',),
        'worktrees': ('worktree', 'list', '--porcelain'),
    }
    result = {key: hashlib.sha256(git(repo, *args, valid=(0, 1) if key == 'refs' else (0,))).hexdigest()
              for key, args in commands.items()}
    digest = hashlib.sha256()
    for relative in sorted(git(repo, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0')):
        if not relative:
            continue
        path = repo/os.fsdecode(relative)
        digest.update(relative + b'\0')
        if path.is_symlink():
            digest.update(os.fsencode(os.readlink(path)))
        elif path.is_file():
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
        else:
            raise RuntimeError('Cannot fingerprint untracked work; keep candidates')
    result['untracked_content'] = digest.hexdigest()
    return result


def open_files():
    if os.name == 'nt':
        # Windows checks each candidate file with an exclusive read-only probe below.
        return []
    result = run(['lsof', '-nP', '-Fpn'], (0, 1))
    if result.stderr or not result.stdout:
        raise RuntimeError('Open-file inventory incomplete; keep candidates')
    records = []
    pid = None
    for line in os.fsdecode(result.stdout).splitlines():
        if line.startswith('p'):
            pid = line[1:]
        elif line.startswith('n/'):
            records.append((pid, Path(line[1:])))
    if not records:
        raise RuntimeError('No readable open-file records')
    return records


def windows_busy_files(paths):
    """Exclusive Windows read-only opens: sharing/access errors always block."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    invalid = ctypes.c_void_p(-1).value
    blocked = []
    for path in paths:
        # FILE_READ_ATTRIBUTES, zero sharing, OPEN_EXISTING; supports directories too.
        handle = create('\\\\?\\' + str(path), 0x80, 0, None, 3, 0x02000000, None)
        if handle == invalid or handle is None:
            blocked.append({'pid': None, 'path': str(path),
                            'reason': 'locked_or_access_unknown', 'windows_error': ctypes.get_last_error()})
        elif not close(handle):
            raise RuntimeError('Cannot close Windows read-only probe handle')
    return blocked


def tree(path, max_nodes):
    digest = hashlib.sha256()
    protected, links, files, errors = [], [], [], []
    pending = [path]
    nodes, allocated = 0, 0
    root_metadata = None
    while pending:
        item = pending.pop()
        try:
            s = item.lstat()
            is_file = stat.S_ISREG(s.st_mode)
            is_dir = stat.S_ISDIR(s.st_mode)
            measured = hasattr(s, 'st_blocks')
            occupied = s.st_blocks * 512 if measured else s.st_size if is_file else 0
            record = {'path': str(item), 'device': s.st_dev, 'inode': s.st_ino,
                      'mode': s.st_mode, 'size_bytes': s.st_size,
                      'mtime_ns': s.st_mtime_ns, 'ctime_ns': s.st_ctime_ns,
                      'birthtime': getattr(s, 'st_birthtime', None),
                      'allocated_bytes': occupied, 'allocation_measured': measured}
            if item == path:
                root_metadata = record
            digest.update(json.dumps(record, ensure_ascii=True).encode() + b'\n')
            nodes += 1
            if nodes > max_nodes:
                raise RuntimeError('Tree exceeds audit node limit; select a smaller subtree')
            allocated += occupied
            reason = protection(item, is_file=is_file and item == path)
            if reason:
                protected.append({'path': str(item), 'reason': reason})
            if stat.S_ISLNK(s.st_mode) or (os.name == 'nt' and getattr(s, 'st_file_attributes', 0) & 0x400):
                links.append(str(item))
            elif is_file:
                files.append(item)
            elif is_dir:
                # No symlink following, and no enumeration into protected content.
                if not reason:
                    pending.extend(sorted(item.iterdir(), reverse=True))
            else:
                errors.append({'path': str(item), 'error': 'non_regular_file'})
        except (OSError, RuntimeError) as exc:
            errors.append({'path': str(item), 'error': str(exc)})
            if isinstance(exc, RuntimeError):
                break
    return {'tree_fingerprint': digest.hexdigest(), 'root_metadata': root_metadata,
            'nodes': nodes, 'file_count': len(files), 'allocated_bytes': allocated,
            'protected': protected, 'symlinks': links, 'errors': errors}, files


def audit(paths, max_nodes):
    global_errors = []
    try:
        opened = open_files()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        opened = []
        global_errors.append(str(exc))
    items, repos = [], set()
    for raw in paths:
        path = Path(raw)
        entry = {'path': raw, 'errors': [], 'review_ready': False}
        try:
            if not path.is_absolute() or path.resolve(strict=True) != path:
                raise RuntimeError('Require an existing canonical absolute path, without symlink aliases')
            details, files = tree(path, max_nodes)
            entry.update(details)
            if os.name == 'nt':
                entry['open_files'] = windows_busy_files(files + ([path] if path.is_dir() else []))
                entry['open_file_check'] = 'windows_exclusive_read_only_probe'
            else:
                entry['open_files'] = [{'pid': pid, 'path': str(p)} for pid, p in opened if contained(p, path)]
                entry['open_file_check'] = 'lsof_inventory'
            repo = repo_for(path)
            entry['repository'] = str(repo) if repo else None
            entry['tracked_count'] = 0
            entry['all_files_git_ignored'] = None
            if repo:
                repos.add(repo)
                rel = str(path.relative_to(repo))
                tracked = git(repo, 'ls-files', '-z', '--', rel).split(b'\0')
                entry['tracked_count'] = len([p for p in tracked if p])
                relative_files = {os.fsencode(p.relative_to(repo).as_posix()) for p in files}
                if not relative_files:
                    relative_files = {os.fsencode(path.relative_to(repo).as_posix())}
                ignored = set(git(repo, 'check-ignore', '--no-index', '-z', '--stdin',
                                  valid=(0, 1), input_bytes=b'\0'.join(sorted(relative_files)) + b'\0').split(b'\0'))
                entry['all_files_git_ignored'] = relative_files.issubset(ignored)
            entry['review_ready'] = not (global_errors or entry['errors'] or entry['protected']
                or entry['symlinks'] or entry['open_files'] or entry['tracked_count']
                or (path.is_dir() and repo and not entry['all_files_git_ignored']))
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            entry['errors'].append(str(exc))
        items.append(entry)
    # Include sibling checkouts sharing the same Git object database.
    for repo in sorted(repos):
        try:
            for record in git(repo, 'worktree', 'list', '--porcelain', '-z').split(b'\0'):
                if record.startswith(b'worktree '):
                    sibling = Path(os.fsdecode(record[len(b'worktree '):])).resolve()
                    if sibling.is_dir():
                        repos.add(sibling)
                    else:
                        raise RuntimeError('Missing registered checkout; reconcile before cleanup')
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            global_errors.append(f'Cannot inventory associated checkouts: {repo}: {exc}')
    states = {}
    for repo in sorted(repos):
        try:
            states[str(repo)] = repo_state(repo)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            global_errors.append(f'Repository snapshot unavailable: {repo}: {exc}')
    if global_errors:
        for entry in items:
            entry['review_ready'] = False
    return {'schema': 1, 'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'platform': sys.platform, 'allocation_measured': os.name != 'nt',
            'max_nodes': max_nodes, 'items': items, 'repository_states': states,
            'errors': global_errors, 'notice': 'Read-only audit; review_ready is not deletion authorization or proof of uselessness.'}


def save(path, value, candidates):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Report output must be absolute')
    canonical = path.resolve()
    if any(contained(canonical, Path(p).resolve()) for p in candidates):
        raise ValueError('Do not put the audit report inside a candidate')
    if path.exists():
        raise FileExistsError('Report already exists; never overwrite it')
    ancestor = path.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if repo_for(ancestor):
        raise ValueError('Do not put private audit reports in a Git repository')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite existing user files or a prior audit.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='mode', required=True)
    snap = subs.add_parser('snapshot')
    snap.add_argument('--paths-json', type=Path, required=True)
    snap.add_argument('--output', type=Path, required=True)
    snap.add_argument('--max-nodes', type=int, default=500000)
    verify = subs.add_parser('verify')
    verify.add_argument('--audit', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'snapshot':
        paths = json.loads(args.paths_json.read_text(encoding='utf-8-sig'))
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
            raise ValueError('Expected a nonempty JSON array of absolute path strings')
        result = audit(paths, args.max_nodes)
        save(args.output, result, paths)
        print(json.dumps({'items': len(result['items']),
                          'review_ready': sum(p['review_ready'] for p in result['items']),
                          'errors': result['errors'], 'report': str(args.output)}, ensure_ascii=False))
    else:
        before = json.loads(args.audit.read_text(encoding='utf-8-sig'))
        if before.get('schema') != 1:
            raise ValueError('Unsupported audit schema')
        current = audit([item['path'] for item in before['items']], before['max_nodes'])
        changed = [old['path'] for old, new in zip(before['items'], current['items'])
                   if not old['review_ready'] or not new['review_ready']
                   or old.get('tree_fingerprint') != new.get('tree_fingerprint')]
        git_changed = before['repository_states'] != current['repository_states']
        ok = not changed and not git_changed and not before['errors'] and not current['errors']
        print(json.dumps({'unchanged_and_review_ready': ok, 'changed_or_blocked_paths': changed,
                          'repository_state_changed': git_changed, 'errors': current['errors']}, ensure_ascii=False))
        return 0 if ok else 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
