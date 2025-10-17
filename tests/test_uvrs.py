"""Tests for the argparse-based uvrs CLI."""

from __future__ import annotations

import io
import runpy
import subprocess
import sys
import textwrap
from argparse import Namespace
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
            stdout
            if target in (None, sys.stdout)
            else stderr
            if target is sys.stderr
            else stdout
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

    return CommandResult(
        exit_code=exit_code,
        stdout=stdout.getvalue(),
        stderr=stderr.getvalue(),
    )


class TestInit:
    def test_init_creates_script(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "test-script.py"

        def fake_run(args: Sequence[Any]) -> None:
            assert list(args) == ["uv", "init", "--script", script_path]
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

        result = run_uvrs("init", str(script_path))

        assert result.exit_code == 0
        assert script_path.exists()
        assert script_path.stat().st_mode & 0o111
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")
        assert "[tool.uv]" in content
        assert "exclude-newer" in content

    def test_init_with_python_version(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
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

    def test_init_forwards_extra_uv_args(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "extra.py"

        def fake_run(args: Sequence[Any]) -> None:
            assert list(args) == ["uv", "init", "--script", script_path, "--no-venv"]
            script_path.write_text(
                textwrap.dedent(
                    """
                    # /// script
                    # dependencies = []
                    # ///
                    print('hi')
                    """
                ).strip()
            )

        mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        run_uvrs("init", str(script_path), "--no-venv")

    def test_init_handles_uv_failure(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "script.py"

        def fake_run(args: Sequence[Any]) -> None:
            raise SystemExit(42)

        mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        result = run_uvrs("init", str(script_path), check=False)

        assert result.exit_code == 42

    def test_init_no_stamp_skips_timestamp(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
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

        result = run_uvrs("init", str(script_path), "--no-stamp")

        assert result.exit_code == 0
        content = script_path.read_text()
        assert "exclude-newer" not in content
        assert "[tool.uv]" not in content


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

    def test_fix_adds_timestamp_to_pep723_script(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env python
                # /// script
                # dependencies = []
                # ///
                print('hello')
                """
            ).strip()
        )

        mock_run = mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")
        assert "[tool.uv]" in content
        assert "exclude-newer" in content
        # Should call uv sync --script <path> --upgrade
        mock_run.assert_called_once_with(
            ["uv", "sync", "--script", script_path, "--upgrade"]
        )

    def test_fix_no_stamp_skips_timestamp(self, tmp_path: Path) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env python
                # /// script
                # dependencies = []
                # ///
                print('hello')
                """
            ).strip()
        )

        result = run_uvrs("fix", str(script_path), "--no-stamp")

        assert result.exit_code == 0
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")
        assert "exclude-newer" not in content

    def test_fix_creates_metadata_for_plain_script(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "plain-script.py"
        script_path.write_text("#!/usr/bin/env python\nprint('hello')\n")

        mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        # Should update shebang
        assert content.startswith("#!/usr/bin/env uvrs\n")
        # Should create metadata
        assert "# /// script" in content
        assert "dependencies = []" in content
        assert "[tool.uv]" in content
        assert "exclude-newer" in content


class TestStamp:
    def test_stamp_adds_timestamp(self, tmp_path: Path, mocker: MockerFixture) -> None:
        script_path = tmp_path / "script.py"
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

        mock_run = mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("stamp", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        assert "[tool.uv]" in content
        assert "exclude-newer" in content
        # Should call uv sync --script <path> --upgrade
        mock_run.assert_called_once_with(
            ["uv", "sync", "--script", script_path, "--upgrade"]
        )

    def test_stamp_updates_existing_timestamp(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text(
            textwrap.dedent(
                """
                # /// script
                # dependencies = []
                #
                # [tool.uv]
                # exclude-newer = "2024-01-01T00:00:00Z"
                # ///
                print('hello')
                """
            ).strip()
        )

        mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("stamp", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        assert "exclude-newer" in content
        # Should have a new timestamp (not the old one)
        assert "2024-01-01T00:00:00Z" not in content

    def test_stamp_creates_metadata_with_shebang(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text("#!/usr/bin/env python\nprint('hello')\n")

        mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("stamp", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        # Should preserve shebang and insert metadata after it
        assert content.startswith("#!/usr/bin/env python\n")
        assert "# /// script" in content
        assert "dependencies = []" in content
        assert "[tool.uv]" in content
        assert "exclude-newer" in content

    def test_stamp_rejects_extra_args(self, tmp_path: Path) -> None:
        script_path = tmp_path / "script.py"
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

        result = run_uvrs("stamp", str(script_path), "extra", check=False)

        assert result.exit_code == 1
        assert "unrecognized arguments" in result.stderr

    def test_stamp_creates_metadata_if_missing(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hello')\n")

        mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("stamp", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        assert "# /// script" in content
        assert "dependencies = []" in content
        assert "[tool.uv]" in content
        assert "exclude-newer" in content


class TestAddRemove:
    def test_add_forwards_arguments(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hi')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        run_uvrs("add", str(script_path), "requests", "--dev")

        mock_run.assert_called_once_with(
            ["uv", "add", "--script", script_path, "requests", "--dev"]
        )

    def test_add_allows_no_dependencies(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hi')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("add", str(script_path))

        assert result.exit_code == 0
        mock_run.assert_called_once_with(["uv", "add", "--script", script_path])

    def test_remove_forwards_arguments(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hi')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        run_uvrs("remove", str(script_path), "requests")

        mock_run.assert_called_once_with(
            ["uv", "remove", "--script", script_path, "requests"]
        )

    def test_remove_allows_no_dependencies(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hi')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("remove", str(script_path))

        assert result.exit_code == 0
        mock_run.assert_called_once_with(["uv", "remove", "--script", script_path])

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

    def test_main_no_handler_specified(self, mocker: MockerFixture) -> None:
        # Create a namespace without a handler attribute
        namespace = Namespace()
        mocker.patch.object(
            uvrs.ArgumentParser, "parse_known_args", return_value=(namespace, [])
        )

        result = run_uvrs("init", check=False)

        assert result.exit_code == 1
        assert "No command specified" in result.stderr

    def test_main_command_paths_to_handler(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        script_path = tmp_path / "script.py"

        def fake_run(args: Sequence[Any]) -> None:
            script_path.write_text(
                textwrap.dedent(
                    """
                    # /// script
                    # dependencies = []
                    # ///
                    print('hi')
                    """
                ).strip()
            )

        mocker.patch("uvrs.run_uv_command", side_effect=fake_run)
        run_uvrs("init", str(script_path))
        assert script_path.exists()


class TestModuleEntry:
    def test_dunder_main_invokes_main(self, mocker: MockerFixture) -> None:
        mock_main = mocker.patch("uvrs.main")
        runpy.run_module("uvrs.__main__", run_name="__main__")
        mock_main.assert_called_once_with()


class TestPEP723Helpers:
    def test_extract_metadata_block_multiple_blocks_raises(self) -> None:
        content = textwrap.dedent(
            """
            # /// script
            # dependencies = []
            # ///
            print('first')
            # /// script
            # dependencies = []
            # ///
            print('second')
            """
        )

        with pytest.raises(ValueError, match="Multiple PEP 723 script blocks found"):
            uvrs.extract_metadata_block(content)

    def test_parse_metadata_handles_empty_comment_lines(self) -> None:
        # Edge case: lines that are just # (blank lines in TOML)
        content = textwrap.dedent(
            """
            # /// script
            # dependencies = []
            #
            # [tool.uv]
            # exclude-newer = "2025-01-01T00:00:00Z"
            # ///
            """
        ).strip()

        match = uvrs.extract_metadata_block(content)
        assert match is not None
        result = uvrs.parse_metadata(match)
        # Should parse blank lines correctly
        assert "dependencies = []" in result
        assert "[tool.uv]" in result
        assert "\n\n" in result  # The blank line should create an empty line in TOML


class TestIntegration:
    """Integration tests that actually run uv commands (no mocking)."""

    def test_init_with_real_uv(self, tmp_path: Path) -> None:
        """Test uvrs init creates a working script with real uv."""
        script_path = tmp_path / "test-script.py"

        result = run_uvrs("init", str(script_path))

        assert result.exit_code == 0
        assert script_path.exists()
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")
        assert "# /// script" in content
        assert "[tool.uv]" in content
        assert "exclude-newer" in content

    def test_stamp_with_real_uv(self, tmp_path: Path) -> None:
        """Test uvrs stamp actually runs uv sync --script --upgrade."""
        script_path = tmp_path / "stamp-test.py"

        # First create a script
        run_uvrs("init", str(script_path))

        # Read the initial timestamp
        content_before = script_path.read_text()

        # Add a dependency
        run_uvrs("add", str(script_path), "rich")

        # Now stamp it (should update timestamp and sync)
        result = run_uvrs("stamp", str(script_path))

        assert result.exit_code == 0
        assert "exclude-newer" in result.stdout

        # Verify timestamp was updated
        content_after = script_path.read_text()
        assert "exclude-newer" in content_after
        # Timestamp should be different (later)
        assert content_after != content_before

    def test_fix_with_real_uv(self, tmp_path: Path) -> None:
        """Test uvrs fix with real uv on a script with dependencies."""
        script_path = tmp_path / "fix-test.py"

        # Create a script with uv directly
        script_path.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env python
                # /// script
                # dependencies = ["rich"]
                # ///
                print('hello')
                """
            ).strip()
        )

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")
        assert "[tool.uv]" in content
        assert "exclude-newer" in content

    def test_add_and_remove_with_real_uv(self, tmp_path: Path) -> None:
        """Test uvrs add and remove actually modify dependencies."""
        script_path = tmp_path / "deps-test.py"

        # Create script
        run_uvrs("init", str(script_path))

        # Add a dependency
        result = run_uvrs("add", str(script_path), "requests")
        assert result.exit_code == 0

        content = script_path.read_text()
        assert "requests" in content

        # Remove the dependency
        result = run_uvrs("remove", str(script_path), "requests")
        assert result.exit_code == 0

        content = script_path.read_text()
        assert "requests" not in content

    def test_init_no_stamp_with_real_uv(self, tmp_path: Path) -> None:
        """Test uvrs init --no-stamp doesn't add timestamp."""
        script_path = tmp_path / "no-stamp-test.py"

        result = run_uvrs("init", str(script_path), "--no-stamp")

        assert result.exit_code == 0
        content = script_path.read_text()
        assert "exclude-newer" not in content
        assert "[tool.uv]" not in content

    def test_stamp_does_not_add_extra_newlines(self, tmp_path: Path) -> None:
        """Test that running stamp multiple times doesn't add extra newlines."""
        script_path = tmp_path / "newline-test.py"

        # Create a script
        run_uvrs("init", str(script_path))

        # Count newlines after first stamp
        content_1 = script_path.read_text()
        newlines_1 = content_1.count("\n")

        # Stamp again
        run_uvrs("stamp", str(script_path))
        content_2 = script_path.read_text()
        newlines_2 = content_2.count("\n")

        # Stamp a third time
        run_uvrs("stamp", str(script_path))
        content_3 = script_path.read_text()
        newlines_3 = content_3.count("\n")

        # The number of newlines should stay the same
        assert newlines_1 == newlines_2 == newlines_3, (
            f"Newlines increased: {newlines_1} -> {newlines_2} -> {newlines_3}\n"
            f"First:\n{content_1}\n"
            f"Second:\n{content_2}\n"
            f"Third:\n{content_3}"
        )

    def test_stamp_creates_metadata_for_plain_script(self, tmp_path: Path) -> None:
        """Test that stamp can add metadata to a plain Python script."""
        script_path = tmp_path / "plain-script.py"
        script_path.write_text("#!/usr/bin/env python\nprint('hello world')\n")

        result = run_uvrs("stamp", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        # Should have shebang preserved
        assert content.startswith("#!/usr/bin/env python\n")
        # Should have created metadata
        assert "# /// script" in content
        assert "dependencies = []" in content
        assert "[tool.uv]" in content
        assert "exclude-newer" in content
        # Original code should be preserved
        assert "print('hello world')" in content

    def test_fix_creates_metadata_for_plain_script_integration(
        self,
        tmp_path: Path,
    ) -> None:
        """Test that fix can add metadata to a plain Python script with real uv."""
        script_path = tmp_path / "plain-script.py"
        script_path.write_text("#!/usr/bin/env python\nprint('hello world')\n")

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        # Should have updated shebang
        assert content.startswith("#!/usr/bin/env uvrs\n")
        # Should have created metadata
        assert "# /// script" in content
        assert "dependencies = []" in content
        assert "[tool.uv]" in content
        assert "exclude-newer" in content
        # Original code should be preserved
        assert "print('hello world')" in content


class TestHelpers:
    def test_run_script_invokes_execvp(self, mocker: MockerFixture) -> None:
        mock_execvp = mocker.patch("uvrs.execvp")

        uvrs.run_script(["script.py", "--flag"])

        mock_execvp.assert_called_once_with(
            "uv", ["uv", "run", "--exact", "--script", "script.py", "--flag"]
        )

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
