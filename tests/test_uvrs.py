"""Tests for the argparse-based uvrs CLI."""

from __future__ import annotations

import io
import runpy
import subprocess
import sys
import textwrap
from collections.abc import Callable, Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture

import uvrs


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


def rich_stub(stdout: io.StringIO, stderr: io.StringIO) -> Callable[..., None]:
    def _print(*objects: object, **kwargs: Any) -> None:
        target = kwargs.pop("file", None)
        stream = (
            stdout if target in (None, sys.stdout) else stderr if target is sys.stderr else stdout
        )
        kwargs.pop("markup", None)
        kwargs.pop("highlight", None)
        print(*objects, file=stream, **kwargs)

    return _print


def run_uvrs(*args: str, check: bool = True) -> CommandResult:
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = 0

    with (
        patch("uvrs.print", side_effect=rich_stub(stdout, stderr)),
        redirect_stdout(stdout),
        redirect_stderr(stderr),
    ):
        try:
            uvrs.main(list(args))
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
        except Exception as exc:  # pragma: no cover - unexpected exception surface
            exit_code = 1
            stderr.write(f"{exc}\n")
        else:
            exit_code = 0

    return CommandResult(exit_code=exit_code, stdout=stdout.getvalue(), stderr=stderr.getvalue())


class TestInit:
    def test_init_creates_script(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "test-script.py"

        def fake_run(args: Sequence[Any]) -> None:
            assert list(args) == ["uv", "init", "--script", script_path]
            script_path.write_text("print('hello')\n")

        mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        result = run_uvrs("init", str(script_path))

        assert result.exit_code == 0
        assert script_path.exists()
        assert script_path.stat().st_mode & 0o111
        assert script_path.read_text().startswith("#!/usr/bin/env uvrs\n")

    def test_init_with_python_version(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "test-script.py"

        def fake_run(args: Sequence[Any]) -> None:
            assert list(args) == [
                "uv",
                "init",
                "--script",
                script_path,
                "--python",
                "3.12",
            ]
            script_path.write_text(
                textwrap.dedent(
                    """
                    # /// script
                    # dependencies = []
                    # requires-python = ">=3.12"
                    # ///
                    print('hello')
                    """
                ).strip()
            )

        mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        run_uvrs("init", str(script_path), "--python", "3.12")

        content = script_path.read_text()
        assert 'requires-python = ">=3.12"' in content

    def test_init_existing_file_fails(self, tmp_path: Path) -> None:
        script_path = tmp_path / "existing.py"
        script_path.write_text("print('hi')\n")

        result = run_uvrs("init", str(script_path), check=False)

        assert result.exit_code == 1
        assert "already exists" in result.stderr

    def test_init_creates_pep723_metadata(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "test-script.py"

        def fake_run(args: Sequence[Any]) -> None:
            script_path.write_text(
                textwrap.dedent(
                    """
                    # /// script
                    # dependencies = []
                    # ///
                    print('hello')
                    """
                ).strip()
            )

        mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        run_uvrs("init", str(script_path))

        content = script_path.read_text()
        assert "# /// script" in content
        assert "# dependencies = []" in content

    def test_init_forwards_extra_uv_args(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "extra.py"

        def fake_run(args: Sequence[Any]) -> None:
            assert list(args) == ["uv", "init", "--script", script_path, "--no-venv"]
            script_path.write_text("print('hi')\n")

        mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        run_uvrs("init", str(script_path), "--no-venv")

    def test_init_handles_uv_failure(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "script.py"

        def fake_run(args: Sequence[Any]) -> None:
            raise SystemExit(42)

        mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        result = run_uvrs("init", str(script_path), check=False)

        assert result.exit_code == 42


class TestFix:
    def test_fix_adds_shebang(self, tmp_path: Path) -> None:
        script_path = tmp_path / "no-shebang.py"
        script_path.write_text("print('hello')\n")

        run_uvrs("fix", str(script_path))

        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")

    def test_fix_updates_existing_shebang(self, tmp_path: Path) -> None:
        script_path = tmp_path / "with-shebang.py"
        script_path.write_text("#!/usr/bin/env python\nprint('hi')\n")

        run_uvrs("fix", str(script_path))

        assert script_path.read_text().startswith("#!/usr/bin/env uvrs\n")

    def test_fix_requires_file(self, tmp_path: Path) -> None:
        directory = tmp_path / "not-a-file"
        directory.mkdir()

        result = run_uvrs("fix", str(directory), check=False)

        assert result.exit_code == 2
        assert "is not a file" in result.stderr

    def test_fix_rejects_extra_args(self, tmp_path: Path) -> None:
        script_path = tmp_path / "test.py"
        script_path.write_text("print('hi')\n")

        result = run_uvrs("fix", str(script_path), "extra", check=False)

        assert result.exit_code == 1
        assert "unrecognized arguments" in result.stderr


class TestAddRemove:
    def test_add_forwards_arguments(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hi')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        run_uvrs("add", str(script_path), "requests", "--dev")

        assert mock_run.call_count == 2
        mock_run.assert_any_call(["uv", "add", "--script", script_path, "requests", "--dev"])
        mock_run.assert_any_call(["uv", "sync", "--script", script_path])

    def test_add_allows_no_dependencies(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hi')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("add", str(script_path))

        assert result.exit_code == 0
        assert mock_run.call_count == 2
        mock_run.assert_any_call(["uv", "add", "--script", script_path])
        mock_run.assert_any_call(["uv", "sync", "--script", script_path])

    def test_remove_forwards_arguments(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hi')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        run_uvrs("remove", str(script_path), "requests")

        assert mock_run.call_count == 2
        mock_run.assert_any_call(["uv", "remove", "--script", script_path, "requests"])
        mock_run.assert_any_call(["uv", "sync", "--script", script_path])

    def test_remove_allows_no_dependencies(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hi')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("remove", str(script_path))

        assert result.exit_code == 0
        assert mock_run.call_count == 2
        mock_run.assert_any_call(["uv", "remove", "--script", script_path])
        mock_run.assert_any_call(["uv", "sync", "--script", script_path])

    def test_add_missing_script_errors(self, tmp_path: Path) -> None:
        script_path = tmp_path / "missing.py"

        result = run_uvrs("add", str(script_path), "requests", check=False)

        assert result.exit_code == 2
        assert "does not exist" in result.stderr

    def test_remove_missing_script_errors(self, tmp_path: Path) -> None:
        script_path = tmp_path / "missing.py"

        result = run_uvrs("remove", str(script_path), "requests", check=False)

        assert result.exit_code == 2
        assert "does not exist" in result.stderr


class TestMainBehaviour:
    def test_main_no_args_prints_help(self) -> None:
        result = run_uvrs(check=False)
        assert "usage:" in result.stdout

    def test_main_script_invokes_run_script(self, mocker: MockerFixture) -> None:
        mock_run_script = mocker.patch("uvrs.run_script")
        uvrs.main(["script.py", "--flag"])
        mock_run_script.assert_called_once_with(["script.py", "--flag"])

    def test_main_run_script_error(self, mocker: MockerFixture) -> None:
        mocker.patch("uvrs.run_script", side_effect=lambda args: uvrs.fail("boom"))
        result = run_uvrs("script.py", check=False)
        assert result.exit_code == 1
        assert "boom" in result.stderr

    def test_main_version_flag(self) -> None:
        result = run_uvrs("--version", check=False)
        assert result.exit_code == 0
        assert result.stdout.strip().startswith("uvrs ")

    def test_main_command_paths_to_handler(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "script.py"

        def fake_run(args: Sequence[Any]) -> None:
            script_path.write_text("print('hi')\n")

        mocker.patch("uvrs.run_uv_command", side_effect=fake_run)
        run_uvrs("init", str(script_path))
        assert script_path.exists()


class TestModuleEntry:
    def test_dunder_main_invokes_main(self, mocker: MockerFixture) -> None:
        mock_main = mocker.patch("uvrs.main")
        runpy.run_module("uvrs.__main__", run_name="__main__")
        mock_main.assert_called_once_with()


class TestHelpers:
    def test_run_script_invokes_execvp(self, mocker: MockerFixture) -> None:
        mock_execvp = mocker.patch("uvrs.execvp")

        uvrs.run_script(["script.py", "--flag"])

        mock_execvp.assert_called_once_with("uv", ["uv", "run", "--script", "script.py", "--flag"])

    def test_run_uv_command_success(self, mocker: MockerFixture) -> None:
        mock_print = mocker.patch("uvrs.print")
        mock_run = mocker.patch("uvrs.subprocess.run")
        mock_run.return_value.returncode = 0

        uvrs.run_uv_command(["uv", "--version"])

        mock_run.assert_called_once_with(["uv", "--version"], check=True)
        mock_print.assert_any_call("[bold cyan]→ uvrs executing:[/] uv --version")

    def test_run_uv_command_failure(self, mocker: MockerFixture) -> None:
        mocker.patch("uvrs.print")
        mocker.patch(
            "uvrs.subprocess.run",
            side_effect=subprocess.CalledProcessError(5, ["uv", "bad"]),
        )

        with pytest.raises(SystemExit) as exc:
            uvrs.run_uv_command(["uv", "bad"])

        assert getattr(exc.value, "code", None) == 5
