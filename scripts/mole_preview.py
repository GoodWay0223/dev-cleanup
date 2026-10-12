#!/usr/bin/env python3
"""Run only supported Mole previews; save private output outside Git repositories."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


def launcher(path, system):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('Mole entrypoint must be a file')
    if system == 'darwin':
        return [str(path)]
    if system != 'win32':
        raise ValueError('Only macOS and Windows are supported')
    if path.suffix.lower() in ('.cmd', '.bat'):
        # Avoid cmd.exe / shell interpolation. Official launchers have this sibling.
        path = (path.parent/'mole.ps1').resolve(strict=True)
    if path.suffix.lower() == '.ps1':
        powershell = shutil.which('powershell.exe') or shutil.which('pwsh.exe')
        if not powershell:
            raise ValueError('PowerShell is unavailable')
        return [powershell, '-NoLogo', '-NoProfile', '-NonInteractive',
                '-ExecutionPolicy', 'Bypass', '-File', str(path)]
    if path.suffix.lower() == '.exe':
        return [str(path)]
    raise ValueError('Unsupported Windows launcher; use the official mole.ps1 or mo.exe')


def find_mole(system, requested=None):
    if requested:
        return launcher(requested, system)
    if system not in ('darwin', 'win32'):
        raise ValueError('Only macOS and Windows are supported')
    found = shutil.which('mo')
    if found:
        return launcher(found, system)
    fallback = (Path.home()/'.local/bin/mo' if system == 'darwin'
                else Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))/'Programs/mole-cli/mole.ps1')
    if not fallback.is_file():
        raise ValueError('Mole is not installed; installation needs an existing user request')
    return launcher(fallback, system)


def preview_args(command, system, path=None):
    if system not in ('darwin', 'win32'):
        raise ValueError('Only macOS and Windows are supported')
    if command in ('clean', 'purge'):
        if path is not None:
            raise ValueError('No exact-path option is assumed for clean/purge')
        return [command, '--dry-run'], '--dry-run'
    if command == 'analyze' and system == 'darwin':
        if path is None or not Path(path).is_absolute() or not Path(path).is_dir():
            raise ValueError('Mac JSON analysis needs an existing absolute directory')
        # The native Go parser stops processing flags after its first positional path.
        return ['analyze', '--json', str(Path(path).resolve())], '--json'
    raise ValueError('Unsupported preview; Windows analyze is interactive, without JSON in the verified version')


def prepare_report(path, analyzed=None):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('Report directory must be an absolute path without link aliases')
    if analyzed is not None and (path == analyzed or analyzed in path.parents):
        raise ValueError('Keep reports outside the analyzed directory')
    ancestor = path
    while not ancestor.exists():
        ancestor = ancestor.parent
    result = subprocess.run(['git', '-C', str(ancestor), 'rev-parse', '--show-toplevel'],
                            capture_output=True, timeout=10,
                            env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
    if result.returncode == 0:
        raise ValueError('Do not save personal preview reports in a Git repository')
    if result.returncode != 128 or b'not a git repository' not in result.stderr.lower():
        raise ValueError('Cannot verify report location; no Mole command was run')
    path.mkdir(parents=True, exist_ok=False)
    return path


def invoke(args, timeout):
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                timeout=timeout, shell=False,
                                env={**os.environ, 'NO_COLOR': '1', 'MO_NO_OPLOG': '1'})
        return {'argv': args, 'exit_code': result.returncode, 'timed_out': False,
                'stdout': result.stdout, 'stderr': result.stderr}
    except subprocess.TimeoutExpired as exc:
        def decode(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
        return {'argv': args, 'exit_code': None, 'timed_out': True,
                'stdout': decode(exc.stdout), 'stderr': decode(exc.stderr)}


def scan_state(result):
    if result['timed_out']:
        return 'incomplete_timeout'
    if result['exit_code'] != 0:
        return 'incomplete_tool_error'
    text = (result['stdout'] + '\n' + result['stderr']).casefold()
    limitations = ('incomplete', 'skipped', 'full disk access', 'need sudo', 'needs sudo',
                   'access denied', 'permission denied', 'requires admin')
    if any(marker in text for marker in limitations):
        return 'reported_with_limits'
    return 'reported_success_scope_unverified'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('clean', 'purge', 'analyze'))
    parser.add_argument('--path', type=Path, help='Mac analyze only')
    parser.add_argument('--mole-path', type=Path, help='Existing official entrypoint')
    parser.add_argument('--report-dir', type=Path, help='New private directory outside Git')
    parser.add_argument('--timeout', type=int, default=60, help='Per-command limit, 1-60 seconds')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 60:
        parser.error('Timeout must be 1-60 seconds')
    operation, required = preview_args(args.command, sys.platform, args.path)
    entry = find_mole(sys.platform, args.mole_path)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory = args.report_dir or Path.home()/'.codex/attachments'/f'mole-preview-{stamp}-{uuid.uuid4().hex[:8]}'
    report = prepare_report(directory, args.path.resolve() if args.path else None)
    records = []
    for name, argv in (('version', entry + ['--version']),
                       ('help', entry + [args.command, '--help'])):
        result = invoke(argv, args.timeout)
        records.append({'stage': name, **result})
        if result['exit_code'] != 0:
            break
    if len(records) == 2 and records[-1]['exit_code'] == 0 and required in records[-1]['stdout']:
        result = invoke(entry + operation, args.timeout)
        records.append({'stage': 'preview', **result})
    else:
        result = {'exit_code': 2, 'timed_out': False, 'stdout': '',
                  'stderr': 'Required option is not advertised by successful local help; preview was not run'}
    value = {'schema': 1, 'platform': sys.platform, 'created_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
             'scan_state': scan_state(result), 'candidate_files_deleted': False, 'records': records,
             'notice': 'Mole can write its own preview/configuration. Output is evidence, never deletion permission.'}
    with (report/'preview.json').open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'report': str(report/'preview.json'), 'scan_state': value['scan_state'],
                      'candidate_files_deleted': False}, ensure_ascii=False))
    return 0 if result['exit_code'] == 0 else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
