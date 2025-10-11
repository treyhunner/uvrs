"""Tests for uvrs CLI tool."""

import runpy
import subprocess
import sys
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import uvrs
from uvrs import cli, main, run_script


def run_uvrs(*args, check=True):
    """Helper to run uvrs command via Click's test runner."""
    runner = CliRunner()
    result = runner.invoke(cli, args, catch_exceptions=False)
    if check and result.exit_code != 0:
        raise RuntimeError(f"Command failed: {result.output}")
    return result


def run_uvrs_subprocess(*args, check=True):
    """Helper to run uvrs command as subprocess (for integration tests)."""
    cmd = [sys.executable, "-m", "uvrs"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {result.stderr}")
    return result


class TestInit:
    """Tests for uvrs init command."""

    def test_init_creates_script(self, tmp_path):
        """Test that init creates a new script with shebang."""
        script_path = tmp_path / "test-script.py"

        result = run_uvrs("init", str(script_path))

        assert result.exit_code == 0
        assert script_path.exists()
        assert script_path.is_file()

        # Check shebang is present
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")

        # Check it's executable
        assert script_path.stat().st_mode & 0o111

    def test_init_with_python_version(self, tmp_path):
        """Test that init respects --python flag."""
        script_path = tmp_path / "test-script.py"

        result = run_uvrs("init", str(script_path), "--python", "3.12")

        assert result.exit_code == 0
        content = script_path.read_text()
        assert 'requires-python = ">=3.12"' in content

    def test_init_existing_file_fails(self, tmp_path):
        """Test that init fails on existing file with helpful message."""
        script_path = tmp_path / "existing.py"
        script_path.write_text("# existing file")

        result = run_uvrs("init", str(script_path), check=False)

        assert result.exit_code != 0
        assert "already exists" in result.output
        assert "uvrs fix" in result.output

    def test_init_creates_pep723_metadata(self, tmp_path):
        """Test that init creates proper PEP 723 script metadata."""
        script_path = tmp_path / "test-script.py"

        run_uvrs("init", str(script_path))

        content = script_path.read_text()
        assert "# /// script" in content
        assert "# dependencies = []" in content
        assert "# ///" in content

    def test_init_handles_uv_failure(self, tmp_path, monkeypatch):
        """uv init failure should surface an error and exit with non-zero code."""
        script_path = tmp_path / "script.py"

        monkeypatch.setattr(
            uvrs.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stderr="boom")
        )

        result = run_uvrs("init", str(script_path), check=False)

        assert result.exit_code != 0
        assert "Error running uv init" in result.output

    def test_init_reports_missing_output(self, tmp_path, monkeypatch):
        """If uv init succeeds but no file created, show an error."""
        script_path = tmp_path / "script.py"

        monkeypatch.setattr(
            uvrs.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stderr="", stdout=""),
        )

        result = run_uvrs("init", str(script_path), check=False)

        assert result.exit_code != 0
        assert "did not create" in result.output


class TestFix:
    """Tests for uvrs fix command."""

    def test_fix_adds_shebang(self, tmp_path):
        """Test that fix adds shebang to file without one."""
        script_path = tmp_path / "no-shebang.py"
        original_content = '# /// script\n# dependencies = []\n# ///\nprint("hello")'
        script_path.write_text(original_content)

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")
        assert 'print("hello")' in content

    def test_fix_replaces_existing_shebang(self, tmp_path):
        """Test that fix replaces existing shebang."""
        script_path = tmp_path / "old-shebang.py"
        original_content = (
            '#!/usr/bin/env python3\n# /// script\n# dependencies = []\n# ///\nprint("hello")'
        )
        script_path.write_text(original_content)

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        lines = content.split("\n")
        assert lines[0] == "#!/usr/bin/env uvrs"
        assert "#!/usr/bin/env python3" not in content

    def test_fix_replaces_uv_run_shebang(self, tmp_path):
        """Test that fix replaces uv run shebang."""
        script_path = tmp_path / "uv-shebang.py"
        original_content = '#!/usr/bin/env -S uv run --script\nprint("hello")'
        script_path.write_text(original_content)

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")
        assert "uv run" not in content.split("\n")[0]

    def test_fix_makes_executable(self, tmp_path):
        """Test that fix makes file executable."""
        script_path = tmp_path / "not-executable.py"
        script_path.write_text("print('hello')")
        script_path.chmod(0o644)  # Not executable

        run_uvrs("fix", str(script_path))

        assert script_path.stat().st_mode & 0o111

    def test_fix_on_nonexistent_file_fails(self, tmp_path):
        """Test that fix fails on nonexistent file."""
        script_path = tmp_path / "nonexistent.py"

        result = run_uvrs("fix", str(script_path), check=False)

        assert result.exit_code != 0

    def test_fix_empty_file(self, tmp_path):
        """Test that fix handles empty files."""
        script_path = tmp_path / "empty.py"
        script_path.write_text("")

        result = run_uvrs("fix", str(script_path))

        assert result.exit_code == 0
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")

    def test_fix_fails_for_directory(self, tmp_path):
        """fix should error when given a directory path."""
        directory_path = tmp_path / "somedir"
        directory_path.mkdir()

        result = run_uvrs("fix", str(directory_path), check=False)

        assert result.exit_code != 0
        assert "not a file" in result.output.lower()


class TestAddRemove:
    """Tests for uvrs add and remove commands."""

    def test_add_dependency(self, tmp_path):
        """Test that add command adds a dependency."""
        script_path = tmp_path / "script.py"
        script_path.write_text(
            '#!/usr/bin/env uvrs\n# /// script\n# dependencies = []\n# ///\nprint("hello")'
        )

        result = run_uvrs("add", str(script_path), "rich")

        assert result.exit_code == 0
        content = script_path.read_text()
        assert "rich" in content

    def test_remove_dependency(self, tmp_path):
        """Test that remove command removes a dependency."""
        script_path = tmp_path / "script.py"
        script_path.write_text(
            '#!/usr/bin/env uvrs\n# /// script\n# dependencies = ["rich"]\n# ///\nprint("hello")'
        )

        result = run_uvrs("remove", str(script_path), "rich")

        assert result.exit_code == 0
        content = script_path.read_text()
        assert "dependencies = []" in content or '"rich"' not in content


class TestShebangMode:
    """Tests for shebang mode execution (using subprocess for realism)."""

    def test_run_script(self, tmp_path):
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

    def test_run_script_with_arguments(self, tmp_path):
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

    def test_run_nonexistent_script_fails(self, tmp_path):
        """Test that running nonexistent script fails."""
        script_path = tmp_path / "nonexistent.py"

        result = run_uvrs_subprocess(str(script_path), check=False)

        assert result.returncode != 0
        assert "not found" in result.stderr.lower()

    def test_no_recursive_invocation(self, tmp_path):
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

    def test_subcommand_help(self):
        """Test that subcommand help works."""
        result = run_uvrs("init", "--help")

        assert result.exit_code == 0
        assert "init" in result.output
        assert "PATH" in result.output

    def test_script_named_like_command(self, tmp_path):
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

    def test_init_command_takes_precedence(self, tmp_path):
        """Test that 'uvrs init' invokes command, not a file named 'init'."""
        # Even if a file named 'init' exists in current dir,
        # 'uvrs init' without args should show command help
        result = run_uvrs("init", check=False)

        # Should show init command help, not try to run a file
        assert "PATH" in result.output or "required" in result.output.lower()


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_full_workflow(self, tmp_path):
        """Test complete workflow: init, add dependency, run."""
        script_path = tmp_path / "my-script.py"

        # 1. Initialize script
        result = run_uvrs("init", str(script_path))
        assert result.exit_code == 0
        assert script_path.exists()

        # 2. Modify script to import and use a package
        content = script_path.read_text()
        # Replace the main function
        new_content = content.replace(
            'print("Hello from my-script.py!")', 'import sys; print(f"Args: {sys.argv[1:]}")'
        )
        script_path.write_text(new_content)

        # 3. Run the script with arguments
        result = run_uvrs_subprocess(str(script_path), "test", "args")
        assert result.returncode == 0
        assert "Args:" in result.stdout

    def test_init_and_fix_workflow(self, tmp_path):
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

    def test_run_script_requires_args(self, capfd):
        """Calling run_script without args should exit with an error."""
        with pytest.raises(SystemExit) as exc:
            run_script([])

        assert exc.value.code == 1
        assert "No script path provided" in capfd.readouterr().err

    def test_run_script_missing_file(self, tmp_path, capfd):
        """run_script should error if the script path does not exist."""
        missing_path = tmp_path / "missing.py"

        with pytest.raises(SystemExit) as exc:
            run_script([str(missing_path)])

        assert exc.value.code == 1
        assert "Script not found" in capfd.readouterr().err

    def test_run_script_execvp_invocation(self, tmp_path, monkeypatch):
        """run_script should delegate to os.execvp with the correct arguments."""
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hi')\n")

        captured: dict[str, list[str] | str] = {}

        def fake_execvp(cmd: str, args: list[str]) -> None:
            captured["cmd"] = cmd
            captured["args"] = args
            raise SystemExit(0)

        monkeypatch.setattr(uvrs.os, "execvp", fake_execvp)

        with pytest.raises(SystemExit) as exc:
            run_script([str(script_path), "arg1", "arg2"])

        assert exc.value.code == 0
        assert captured["cmd"] == "uv"
        assert captured["args"] == ["uv", "run", "--script", str(script_path), "arg1", "arg2"]


class TestMain:
    """Direct tests for the top-level main dispatcher."""

    def test_main_no_args_invokes_cli(self, monkeypatch):
        """No arguments should call the Click CLI entry point."""
        calls: list[str] = []

        monkeypatch.setattr(sys, "argv", ["uvrs"])

        def fake_cli() -> None:
            calls.append("cli")

        monkeypatch.setattr(uvrs, "cli", fake_cli)

        main()

        assert calls == ["cli"]

    def test_main_command_invokes_cli(self, monkeypatch):
        """Known subcommands should dispatch to Click CLI."""
        calls: list[str] = []

        monkeypatch.setattr(sys, "argv", ["uvrs", "init"])

        def fake_cli() -> None:
            calls.append("cli")

        monkeypatch.setattr(uvrs, "cli", fake_cli)

        main()

        assert calls == ["cli"]

    def test_main_flag_invokes_cli(self, monkeypatch):
        """Flags should be forwarded to Click CLI."""
        calls: list[str] = []

        monkeypatch.setattr(sys, "argv", ["uvrs", "--help"])

        def fake_cli() -> None:
            calls.append("cli")

        monkeypatch.setattr(uvrs, "cli", fake_cli)

        main()

        assert calls == ["cli"]

    def test_main_script_invokes_run_script(self, tmp_path, monkeypatch):
        """A non-command argument should invoke run_script with remaining args."""
        script_path = tmp_path / "script.py"
        script_path.write_text("print('hello')\n")

        monkeypatch.setattr(sys, "argv", ["uvrs", str(script_path), "--flag"])

        captured: list[list[str]] = []

        def fake_run_script(args: list[str]) -> None:
            captured.append(args)

        monkeypatch.setattr(uvrs, "run_script", fake_run_script)
        monkeypatch.setattr(uvrs, "cli", lambda: None)

        main()

        assert captured == [[str(script_path), "--flag"]]


class TestModuleEntry:
    """Tests for running the package as ``python -m uvrs``."""

    def test_dunder_main_invokes_main(self, monkeypatch):
        """Running the module should call uvrs.main()."""
        calls: list[str] = []

        def fake_main() -> None:
            calls.append("main")

        monkeypatch.setattr(uvrs, "main", fake_main)

        runpy.run_module("uvrs.__main__", run_name="__main__")

        assert calls == ["main"]
