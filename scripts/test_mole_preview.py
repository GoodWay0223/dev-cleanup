"""Preview-only behavior checks; never run cleanup against user data."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import mole_preview as preview


class PreviewBoundaries(unittest.TestCase):
    def test_only_dry_runs_are_exposed(self):
        for platform in ('darwin', 'win32'):
            for command in ('clean', 'purge'):
                self.assertEqual(preview.preview_args(command, platform)[0], [command, '--dry-run'])
            for command in ('remove', 'update', 'uninstall', 'optimize'):
                with self.assertRaises(ValueError):
                    preview.preview_args(command, platform)
            with self.assertRaises(ValueError):
                preview.preview_args('clean', platform, Path.home())

    def test_windows_analysis_is_rejected_before_execution(self):
        with patch.object(preview.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                preview.preview_args('analyze', 'win32', Path.home())
            run.assert_not_called()

    def test_mac_json_option_precedes_path_to_avoid_interactive_tui(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve()
            args, _ = preview.preview_args('analyze', 'darwin', path)
            self.assertEqual(args, ['analyze', '--json', str(path)])

    def test_windows_cmd_is_replaced_by_ps1_without_shell(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root/'mo.cmd').write_text('Never execute this batch file')
            (root/'mole.ps1').write_text('# isolated fixture')
            with patch.object(preview.shutil, 'which', return_value='powershell.exe'):
                args = preview.launcher(root/'mo.cmd', 'win32')
            self.assertIn('-NoProfile', args)
            self.assertIn('-NonInteractive', args)
            self.assertEqual(args[-2:], ['-File', str(root/'mole.ps1')])
            with patch.object(preview.subprocess, 'run', return_value=subprocess.CompletedProcess(args, 0, 'help', '')) as run:
                preview.invoke(args + ['clean', '--dry-run'], 1)
            self.assertFalse(run.call_args.kwargs['shell'])
            self.assertEqual(run.call_args.args[0][-2:], ['clean', '--dry-run'])

    def test_private_reports_never_enter_git_or_replace_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            repo = root/'repo'
            repo.mkdir()
            subprocess.run(['git', '-C', str(repo), 'init', '-q'], check=True)
            with self.assertRaises(ValueError):
                preview.prepare_report(repo/'private-report')
            report = root/'report'
            preview.prepare_report(report)
            with self.assertRaises(FileExistsError):
                preview.prepare_report(report)
            with self.assertRaises(ValueError):
                preview.prepare_report(root/'analyzed/report', root/'analyzed')

    def test_timeout_and_permissions_never_mean_complete(self):
        result = {'exit_code': 0, 'timed_out': False, 'stdout': 'skipped incomplete root scan', 'stderr': ''}
        self.assertEqual(preview.scan_state(result), 'reported_with_limits')
        result.update(timed_out=True)
        self.assertEqual(preview.scan_state(result), 'incomplete_timeout')
        result.update(timed_out=False, exit_code=1)
        self.assertEqual(preview.scan_state(result), 'incomplete_tool_error')
        result.update(exit_code=0, stdout='Dry run finished')
        self.assertEqual(preview.scan_state(result), 'reported_success_scope_unverified')


if __name__ == '__main__':
    unittest.main()
