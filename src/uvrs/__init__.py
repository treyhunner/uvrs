"""uvrs - Create and run uv scripts with POSIX standardized shebang line."""

import os
import subprocess
import sys
from pathlib import Path

import click

SHEBANG_LINE = "#!/usr/bin/env uvrs"


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """uvrs - Create and run uv scripts with POSIX standardized shebang line.

    When invoked as a shebang (#!/usr/bin/env uvrs), runs the script with uv.
    Otherwise, provides commands for managing uv scripts.
    """
    # If no subcommand was invoked, show help
    # Note: shebang mode is handled in main(), not here
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        sys.exit(0)


def run_script(args: list[str]) -> None:
    """Execute a script using uv run.

    Args:
        args: List of arguments where first is the script path and rest are script arguments
    """
    if not args:
        click.echo("Error: No script path provided", err=True)
        sys.exit(1)

    script_path = args[0]
    script_args = args[1:]

    # Check if script exists
    if not Path(script_path).exists():
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    # Execute with uv run --script to avoid recursive shebang invocation
    uv_cmd = ["uv", "run", "--script", script_path] + script_args
    os.execvp("uv", uv_cmd)


@cli.command()
@click.argument("path", type=click.Path())
@click.option("--python", help="Python version constraint (e.g., 3.12)")
def init(path: str, python: str | None) -> None:
    """Create a new uv script with uvrs shebang.

    Creates a new script at PATH using 'uv init --script' and adds
    the #!/usr/bin/env uvrs shebang line.
    """
    path_obj = Path(path)

    # Check if file already exists
    if path_obj.exists():
        click.echo(f"Error: File already exists at {path}", err=True)
        click.echo(f"Use 'uvrs fix {path}' to add or update the shebang line", err=True)
        sys.exit(1)

    # Build uv init command
    cmd = ["uv", "init", "--script", str(path)]
    if python:
        cmd.extend(["--python", python])

    # Run uv init
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"Error running uv init: {result.stderr}", err=True)
        sys.exit(result.returncode)

    # Read the created file
    if not path_obj.exists():
        click.echo(f"Error: uv init did not create file at {path}", err=True)
        sys.exit(1)

    content = path_obj.read_text()

    # Add shebang at the beginning
    new_content = f"{SHEBANG_LINE}\n{content}"
    path_obj.write_text(new_content)

    # Make executable
    path_obj.chmod(path_obj.stat().st_mode | 0o111)

    click.echo(f"Initialized script at {path} with uvrs shebang")


@cli.command()
@click.argument("path", type=click.Path(exists=True))
def fix(path: str) -> None:
    """Add or update shebang line to use uvrs.

    If PATH has no shebang, adds #!/usr/bin/env uvrs.
    If PATH has a uv run shebang, updates it to use uvrs.
    """
    path_obj = Path(path)

    # Check if it's a file
    if not path_obj.is_file():
        click.echo(f"Error: {path} is not a file", err=True)
        sys.exit(1)

    content = path_obj.read_text()
    lines = content.split("\n")

    if not lines:
        # Empty file
        new_content = SHEBANG_LINE + "\n"
    elif lines[0].startswith("#!"):
        # Has a shebang, replace it
        lines[0] = SHEBANG_LINE
        new_content = "\n".join(lines)
    else:
        # No shebang, add it
        new_content = f"{SHEBANG_LINE}\n{content}"

    path_obj.write_text(new_content)

    # Make executable if not already
    current_mode = path_obj.stat().st_mode
    if not (current_mode & 0o111):
        path_obj.chmod(current_mode | 0o111)

    click.echo(f"Updated shebang in {path}")


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.argument("dependency")
def add(path: str, dependency: str) -> None:
    """Add a dependency to a script's inline metadata.

    This is a shortcut for 'uv add --script PATH DEPENDENCY'.
    """
    cmd = ["uv", "add", "--script", path, dependency]
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.argument("dependency")
def remove(path: str, dependency: str) -> None:
    """Remove a dependency from a script's inline metadata.

    This is a shortcut for 'uv remove --script PATH DEPENDENCY'.
    """
    cmd = ["uv", "remove", "--script", path, dependency]
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


def main() -> None:
    """Main entry point for uvrs CLI."""
    # Check if we're in shebang mode (first arg is not a known subcommand)
    known_commands = {"init", "fix", "add", "remove"}

    if len(sys.argv) > 1:
        first_arg = sys.argv[1]

        # If it's a flag (starts with -) or a known command, use Click
        if first_arg.startswith("-") or first_arg in known_commands:
            cli()
        else:
            # Shebang mode: first argument is the script path
            run_script(sys.argv[1:])
    else:
        # No arguments, show help
        cli()
