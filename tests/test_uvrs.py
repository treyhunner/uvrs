"""Tests for uvrs CLI tool."""

from __future__ import annotations

import runpy
import subprocess
import sys
import textwrap
from pathlib import Path

import click
import pytest
from click.testing import CliRunner, Result
from pytest_mock import MockerFixture

import uvrs
from uvrs import cli, main, run_script


def run_uvrs(*args: str, check: bool = True) -> Result:
    """Helper to run uvrs command via Click's test runner."""
    runner = CliRunner()
    result = runner.invoke(cli, args, catch_exceptions=False)
    if check and result.exit_code != 0:
        raise RuntimeError(f"Command failed: {result.output}")
    return result


def run_uvrs_subprocess(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Helper to run uvrs command as subprocess (for integration tests)."""
    cmd = [sys.executable, "-m", "uvrs"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {result.stderr}")
    return result


class TestInit:
    """Tests for uvrs init command."""

    def test_init_creates_script(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that init creates a new script with shebang."""
        script_path = tmp_path / "test-script.py"

        def fake_run(args: list[str]) -> None:
            assert args == ["uv", "init", "--script", str(script_path)]
            script_path.write_text("print('hello')\n")

        mock_run = mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        result = run_uvrs("init", str(script_path))

        assert result.exit_code == 0
        assert script_path.exists()
        assert script_path.is_file()
        mock_run.assert_called_once()

        # Check shebang is present
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")

        # Check it's executable
        assert script_path.stat().st_mode & 0o111

    def test_init_with_python_version(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that init respects --python flag."""
        script_path = tmp_path / "test-script.py"

        def fake_run(args: list[str]) -> None:
            assert args == [
                "uv",
                "init",
                "--script",
                str(script_path),
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

        mock_run = mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        result = run_uvrs("init", str(script_path), "--python", "3.12")

        assert result.exit_code == 0
        content = script_path.read_text()
        assert 'requires-python = ">=3.12"' in content
        mock_run.assert_called_once()

    def test_init_existing_file_fails(self, tmp_path: Path) -> None:
        """Test that init fails on existing file with helpful message."""
        script_path = tmp_path / "existing.py"
        script_path.write_text("# existing file")

        result = run_uvrs("init", str(script_path), check=False)

        assert result.exit_code != 0
        assert "already exists" in result.output
        assert "uvrs fix" in result.output

    def test_init_creates_pep723_metadata(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that init creates proper PEP 723 script metadata."""
        script_path = tmp_path / "test-script.py"

        def fake_run(args: list[str]) -> None:
            assert args == ["uv", "init", "--script", str(script_path)]
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

        mock_run = mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        run_uvrs("init", str(script_path))
        mock_run.assert_called_once()

        content = script_path.read_text()
        assert "# /// script" in content
        assert "# dependencies = []" in content
        assert "# ///" in content

    def test_init_forwards_extra_uv_args(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Additional uv args should be forwarded to `uv init`."""
        script_path = tmp_path / "extra.py"

        def fake_run(args: list[str]) -> None:
            assert args == ["uv", "init", "--script", str(script_path), "--no-venv"]
            script_path.write_text(
                textwrap.dedent(
                    """
                    # /// script
                    # dependencies = []
                    # ///
                    print("hello")
                    """
                ).strip()
            )

        mock_run = mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        result = run_uvrs("init", str(script_path), "--no-venv")

        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_init_handles_uv_failure(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """uv init failure should surface an error and exit with non-zero code."""
        script_path = tmp_path / "script.py"

        def fake_run(args: list[str]) -> None:
            assert args == ["uv", "init", "--script", str(script_path)]
            raise SystemExit(1)

        mock_run = mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        result = run_uvrs("init", str(script_path), check=False)

        assert result.exit_code != 0
        mock_run.assert_called_once()

    def test_init_reports_missing_output(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """If uv init succeeds but no file created, show an error."""
        script_path = tmp_path / "script.py"

        def fake_run(args: list[str]) -> None:
            assert args == ["uv", "init", "--script", str(script_path)]

        mock_run = mocker.patch("uvrs.run_uv_command", side_effect=fake_run)

        result = run_uvrs("init", str(script_path), check=False)

        assert result.exit_code != 0
        assert "did not create" in result.output
        mock_run.assert_called_once()


class TestFix:
    """Tests for uvrs fix command."""

    def test_fix_adds_shebang(self, tmp_path: Path) -> None:
        """Test that fix adds shebang to file without one."""
        script_path = tmp_path / "no-shebang.py"
        script_path.write_text(
            textwrap.dedent(
                """
                # /// script
                # dependencies = []
                # ///
                print("hello")
                """
            ).strip()
        )

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")
        assert 'print("hello")' in content

    def test_fix_replaces_existing_shebang(self, tmp_path: Path) -> None:
        """Test that fix replaces existing shebang."""
        script_path = tmp_path / "old-shebang.py"
        script_path.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env python3
                # /// script
                # dependencies = []
                # ///
                print("hello")
                """
            ).strip()
        )

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        lines = content.split("\n")
        assert lines[0] == "#!/usr/bin/env uvrs"
        assert "#!/usr/bin/env python3" not in content

    def test_fix_replaces_uv_run_shebang(self, tmp_path: Path) -> None:
        """Test that fix replaces uv run shebang."""
        script_path = tmp_path / "uv-shebang.py"
        script_path.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env -S uv run --script
                print("hello")
                """
            ).strip()
        )

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")
        assert "uv run" not in content.split("\n")[0]

    def test_fix_makes_executable(self, tmp_path: Path) -> None:
        """Test that fix makes file executable."""
        script_path = tmp_path / "not-executable.py"
        script_path.write_text("print('hello')")
        script_path.chmod(0o644)  # Not executable

        run_uvrs("fix", str(script_path))

        assert script_path.stat().st_mode & 0o111

    def test_fix_on_nonexistent_file_fails(self, tmp_path: Path) -> None:
        """Test that fix fails on nonexistent file."""
        script_path = tmp_path / "nonexistent.py"

        result = run_uvrs("fix", str(script_path), check=False)

        assert result.exit_code != 0

    def test_fix_empty_file(self, tmp_path: Path) -> None:
        """Test that fix handles empty files."""
        script_path = tmp_path / "empty.py"
        script_path.write_text("")

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")

    def test_fix_fails_for_directory(self, tmp_path: Path) -> None:
        """fix should error when given a directory path."""
        directory_path = tmp_path / "somedir"
        directory_path.mkdir()

        result = run_uvrs("fix", str(directory_path), check=False)

        assert result.exit_code != 0
        assert "not a file" in result.output.lower()


class TestAddRemove:
    """Tests for uvrs add and remove commands."""

    def test_add_dependency(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that add command forwards dependency to uv."""
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hello')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("add", str(script_path), "rich")

        assert result.exit_code == 0
        mock_run.assert_called_once_with(["uv", "add", "--script", str(script_path), "rich"])

    def test_add_forwards_extra_args(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """uvrs add should forward additional flags to uv."""
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hello')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("add", str(script_path), "--optional", "dev", "rich")

        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            ["uv", "add", "--script", str(script_path), "--optional", "dev", "rich"]
        )

    def test_remove_dependency(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that remove command forwards dependency to uv."""
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hello')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("remove", str(script_path), "rich")

        assert result.exit_code == 0
        mock_run.assert_called_once_with(["uv", "remove", "--script", str(script_path), "rich"])

    def test_remove_forwards_extra_args(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """uvrs remove should forward additional flags to uv."""
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hello')\n")

        mock_run = mocker.patch("uvrs.run_uv_command")

        result = run_uvrs("remove", str(script_path), "--dry-run", "rich")

        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            ["uv", "remove", "--script", str(script_path), "--dry-run", "rich"]
        )

    def test_add_requires_dependency(self, tmp_path: Path) -> None:
        """uvrs add should surface a helpful error when no dependency provided."""
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hello')\n")

        result = run_uvrs("add", str(script_path), check=False)

        assert result.exit_code != 0
        assert "dependency" in result.output.lower()

    def test_remove_requires_dependency(self, tmp_path: Path) -> None:
        """uvrs remove should surface a helpful error when no dependency provided."""
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hello')\n")

        result = run_uvrs("remove", str(script_path), check=False)

        assert result.exit_code != 0
        assert "dependency" in result.output.lower()


class TestShebangMode:
    """Tests for shebang mode execution (using subprocess for realism)."""

    def test_run_script(self, tmp_path: Path) -> None:
        """Test that uvrs can run a script."""
        script_path = tmp_path / "script.py"
        script_path.write_text(
            "#!/usr/bin/env uvrs\n"
            "# /// script\n"
            "# dependencies = []\n"
            "# ///\n"
            'print("Hello from script")'
        )

        result = run_uvrs_subprocess(str(script_path))

        assert result.returncode == 0
        assert "Hello from script" in result.stdout

    def test_run_script_with_arguments(self, tmp_path: Path) -> None:
        """Test that script arguments are passed through."""
        script_path = tmp_path / "script.py"
        script_path.write_text(
            "#!/usr/bin/env uvrs\n"
            "# /// script\n"
            "# dependencies = []\n"
            "# ///\n"
            "import sys\n"
            'print(" ".join(sys.argv[1:]))'
        )

        result = run_uvrs_subprocess(str(script_path), "arg1", "arg2", "--flag")

        assert result.returncode == 0
        assert "arg1 arg2 --flag" in result.stdout

    def test_run_nonexistent_script_fails(self, tmp_path: Path) -> None:
        """Test that running nonexistent script fails."""
        script_path = tmp_path / "nonexistent.py"

        result = run_uvrs_subprocess(str(script_path), check=False)

        assert result.returncode != 0
        assert "not found" in result.stderr.lower()

    def test_no_recursive_invocation(self, tmp_path: Path) -> None:
        """Test that scripts with uvrs shebang don't cause recursion."""
        script_path = tmp_path / "script.py"
        script_path.write_text(
            '#!/usr/bin/env uvrs\n# /// script\n# dependencies = []\n# ///\nprint("No recursion!")'
        )

        # This should not hang or cause recursion error
        result = run_uvrs_subprocess(str(script_path))

        assert result.returncode == 0
        assert "No recursion!" in result.stdout
        assert "recursively invoked" not in result.stderr


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_help_flag(self):
        """Test that --help flag works."""
        result = run_uvrs("--help")

        assert result.exit_code == 0
        assert "uvrs" in result.output
        assert "Commands:" in result.output

    def test_run_uvrs_error_handling(self):
        """Test that run_uvrs raises RuntimeError when command fails with check=True."""
        with pytest.raises(RuntimeError, match="Command failed"):
            run_uvrs("nonexistent_command")

    def test_run_uvrs_subprocess_error_handling(self):
        """Test that run_uvrs_subprocess raises RuntimeError when command fails with check=True."""
        with pytest.raises(RuntimeError, match="Command failed"):
            run_uvrs_subprocess("nonexistent_command")

    def test_subcommand_help(self):
        """Test that subcommand help works."""
        result = run_uvrs("init", "--help")

        assert result.exit_code == 0
        assert "init" in result.output
        assert "PATH" in result.output

    def test_script_named_like_command(self, tmp_path: Path) -> None:
        """Test that we can run a script named like a command."""
        script_path = tmp_path / "init"
        script_path.write_text(
            "#!/usr/bin/env uvrs\n"
            "# /// script\n"
            "# dependencies = []\n"
            "# ///\n"
            'print("I am a script named init")'
        )

        # With full path, should run the script
        result = run_uvrs_subprocess(str(script_path))

        assert result.returncode == 0
        assert "I am a script named init" in result.stdout

    def test_no_args_shows_help(self):
        """Test that running uvrs with no args shows help."""
        result = run_uvrs()

        assert result.exit_code == 0
        assert "uvrs" in result.output
        assert "Commands:" in result.output

    def test_init_command_takes_precedence(self, tmp_path: Path) -> None:
        """Test that 'uvrs init' invokes command, not a file named 'init'."""
        # Even if a file named 'init' exists in current dir,
        # 'uvrs init' without args should show command help
        result = run_uvrs("init", check=False)

        # Should show init command help, not try to run a file
        assert "PATH" in result.output or "required" in result.output.lower()


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_full_workflow(self, tmp_path: Path) -> None:
        """Test complete workflow: init, add dependency, run."""
        script_path = tmp_path / "my-script.py"

        # 1. Initialize script
        init_result = run_uvrs("init", str(script_path))
        assert init_result.exit_code == 0
        assert script_path.exists()

        # 2. Modify script to import and use a package
        content = script_path.read_text()
        # Replace the main function
        new_content = content.replace(
            'print("Hello from my-script.py!")', 'import sys; print(f"Args: {sys.argv[1:]}")'
        )
        script_path.write_text(new_content)

        # 3. Run the script with arguments
        run_result = run_uvrs_subprocess(str(script_path), "test", "args")
        assert run_result.returncode == 0
        assert "Args:" in run_result.stdout

    def test_init_and_fix_workflow(self, tmp_path: Path) -> None:
        """Test that fix can update a script created elsewhere."""
        script_path = tmp_path / "script.py"

        # Create a script without uvrs (simulating manual creation)
        script_path.write_text(
            '#!/usr/bin/env python3\n# /// script\n# dependencies = []\n# ///\nprint("hello")'
        )

        # Use fix to update it
        result = run_uvrs("fix", str(script_path))
        assert result.exit_code == 0

        # Verify shebang was updated
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")
        assert content.count("#!/") == 1  # Only one shebang


class TestRunScript:
    """Direct tests for run_script helper."""

    def test_run_script_requires_args(self):
        """Calling run_script without args should raise ClickException."""
        with pytest.raises(click.ClickException) as exc:
            run_script([])

        assert "No script path provided" in str(exc.value)

    def test_run_script_missing_file(self, tmp_path: Path) -> None:
        """run_script should error if the script path does not exist."""
        missing_path = tmp_path / "missing.py"

        with pytest.raises(click.ClickException) as exc:
            run_script([str(missing_path)])

        assert "Script not found" in str(exc.value)

    def test_run_script_execvp_invocation(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """run_script should delegate to os.execvp with the correct arguments."""
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hi')\n")

        execvp_mock = mocker.patch("uvrs.os.execvp", side_effect=SystemExit(0))

        with pytest.raises(SystemExit) as exc:
            run_script([str(script_path), "arg1", "arg2"])

        assert exc.value.code == 0  # type: ignore[attr-defined]
        execvp_mock.assert_called_once_with(
            "uv",
            ["uv", "run", "--script", str(script_path), "arg1", "arg2"],
        )


class TestMain:
    """Direct tests for the top-level main dispatcher."""

    def test_main_no_args_invokes_cli(self, mocker: MockerFixture) -> None:
        """No arguments should call the Click CLI entry point."""
        mocker.patch.object(sys, "argv", ["uvrs"])
        mock_main = mocker.patch.object(uvrs.cli, "main")

        main()

        mock_main.assert_called_once_with()

    def test_main_command_invokes_cli(self, mocker: MockerFixture) -> None:
        """Known subcommands should dispatch to Click CLI."""

        mocker.patch.object(sys, "argv", ["uvrs", "init"])
        mock_main = mocker.patch.object(uvrs.cli, "main")
        mock_get_command = mocker.patch.object(uvrs.cli, "get_command", return_value=object())

        main()

        mock_main.assert_called_once_with()
        mock_get_command.assert_called()

    def test_main_flag_invokes_cli(self, mocker: MockerFixture) -> None:
        """Flags should be forwarded to Click CLI."""

        mocker.patch.object(sys, "argv", ["uvrs", "--help"])
        mock_main = mocker.patch.object(uvrs.cli, "main")

        main()

        mock_main.assert_called_once_with()

    def test_main_script_invokes_run_script(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A non-command argument should invoke run_script with remaining args."""
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hello')\n")

        mocker.patch.object(sys, "argv", ["uvrs", str(script_path), "--flag"])
        mocker.patch.object(uvrs.cli, "get_command", return_value=None)
        mock_run_script = mocker.patch("uvrs.run_script")
        mock_main = mocker.patch.object(uvrs.cli, "main")

        main()

        mock_run_script.assert_called_once_with([str(script_path), "--flag"])
        mock_main.assert_not_called()

    def test_main_handles_cli_without_commands(self, mocker: MockerFixture) -> None:
        """Fallback to empty command set when cli has no commands attribute."""
        mocker.patch.object(sys, "argv", ["uvrs", "script.py"])
        mocker.patch.object(uvrs.cli, "get_command", return_value=None)
        mock_run_script = mocker.patch("uvrs.run_script")
        mock_main = mocker.patch.object(uvrs.cli, "main")

        main()

        mock_run_script.assert_called_once_with(["script.py"])
        mock_main.assert_not_called()

    def test_main_shows_run_script_error(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Errors from run_script should be rendered cleanly and exit with code 1."""
        mocker.patch.object(sys, "argv", ["uvrs", "script.py"])
        mocker.patch.object(uvrs.cli, "get_command", return_value=None)

        mocker.patch("uvrs.run_script", side_effect=click.ClickException("boom"))

        with pytest.raises(SystemExit) as exc:
            main()

        assert exc.value.code == 1  # type: ignore[attr-defined]
        err = capsys.readouterr().err
        assert "Error: boom" in err


class TestModuleEntry:
    """Tests for running the package as ``python -m uvrs``."""

    def test_dunder_main_invokes_main(self, mocker: MockerFixture) -> None:
        """Running the module should call uvrs.main()."""
        mock_main = mocker.patch.object(uvrs, "main")

        runpy.run_module("uvrs.__main__", run_name="__main__")

        mock_main.assert_called_once_with()


class TestHelpers:
    """Unit tests for helper utilities."""

    def test_run_uv_command_success(self, mocker: MockerFixture) -> None:
        """run_uv_command should invoke subprocess.run with check enabled."""
        mock_run = mocker.patch(
            "uvrs.subprocess.run",
            return_value=subprocess.CompletedProcess(["uv"], 0),
        )

        uvrs.run_uv_command(["uv", "--version"])

        mock_run.assert_called_once_with(["uv", "--version"], check=True)

    def test_run_uv_command_failure(self, mocker: MockerFixture) -> None:
        """run_uv_command should exit with uv's return code when the command fails."""
        mocker.patch(
            "uvrs.subprocess.run",
            side_effect=subprocess.CalledProcessError(5, ["uv", "bad"]),
        )

        with pytest.raises(SystemExit) as exc:
            uvrs.run_uv_command(["uv", "bad"])

        assert exc.value.code == 5
