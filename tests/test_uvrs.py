"""Tests for uvrs CLI tool."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from io import StringIO

import pytest
from click.testing import CliRunner

from uvrs import cli


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
        assert "requires-python = \">=3.12\"" in content

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
        original_content = '#!/usr/bin/env python3\n# /// script\n# dependencies = []\n# ///\nprint("hello")'
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


class TestAddRemove:
    """Tests for uvrs add and remove commands."""

    def test_add_dependency(self, tmp_path):
        """Test that add command adds a dependency."""
        script_path = tmp_path / "script.py"
        script_path.write_text(
            "#!/usr/bin/env uvrs\n"
            "# /// script\n"
            "# dependencies = []\n"
            "# ///\n"
            'print("hello")'
        )

        result = run_uvrs("add", str(script_path), "rich")

        assert result.exit_code == 0
        content = script_path.read_text()
        assert "rich" in content

    def test_remove_dependency(self, tmp_path):
        """Test that remove command removes a dependency."""
        script_path = tmp_path / "script.py"
        script_path.write_text(
            "#!/usr/bin/env uvrs\n"
            "# /// script\n"
            '# dependencies = ["rich"]\n'
            "# ///\n"
            'print("hello")'
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
            "#!/usr/bin/env uvrs\n"
            "# /// script\n"
            "# dependencies = []\n"
            "# ///\n"
            'print("No recursion!")'
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
            'print("Hello from my-script.py!")',
            'import sys; print(f"Args: {sys.argv[1:]}")'
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
            "#!/usr/bin/env python3\n"
            "# /// script\n"
            "# dependencies = []\n"
            "# ///\n"
            'print("hello")'
        )

        # Use fix to update it
        result = run_uvrs("fix", str(script_path))
        assert result.exit_code == 0

        # Verify shebang was updated
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env uvrs\n")
        assert content.count("#!/") == 1  # Only one shebang
