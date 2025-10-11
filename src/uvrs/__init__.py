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
        raise click.ClickException("No script path provided")

    [script_path, *script_args] = args

    # Check if script exists
    if not Path(script_path).exists():
        raise click.ClickException(f"Script not found: {script_path}")

    # Execute with uv run --script to avoid recursive shebang invocation
    os.execvp("uv", ["uv", "run", "--script", script_path, *script_args])


@cli.command()
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--python", help="Python version constraint (e.g., 3.12)")
def init(path: Path, python: str | None) -> None:
    """Create a new uv script with uvrs shebang.

    Creates a new script at PATH using 'uv init --script' and adds
    the #!/usr/bin/env uvrs shebang line.
    """

    # Check if file already exists
    if path.exists():
        raise click.ClickException(
            f"File already exists at {path}\nUse 'uvrs fix {path}' to add or update the shebang line"
        )

    # Build uv init command
    cmd = ["uv", "init", "--script", str(path)]
    if python:
        cmd.extend(["--python", python])

    # Run uv init
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise click.ClickException(f"Error running uv init: {result.stderr}")

    # Read the created file
    if not path.exists():
        raise click.ClickException(f"uv init did not create file at {path}")

    # Add shebang at the beginning
    content = path.read_text()
    path.write_text(f"{SHEBANG_LINE}\n{content}")

    # Make executable
    path.chmod(path.stat().st_mode | 0o111)

    click.echo(f"Initialized script at {path} with uvrs shebang")


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def fix(path: Path) -> None:
    """Add or update shebang line to use uvrs.

    If PATH has no shebang, adds #!/usr/bin/env uvrs.
    If PATH has a uv run shebang, updates it to use uvrs.
    """

    # Check if it's a file
    if not path.is_file():
        raise click.ClickException(f"{path} is not a file")

    content = path.read_text()
    if content.startswith("#!"):
        # Has a shebang, replace it
        new_content = "\n".join([SHEBANG_LINE, *content.split("\n")[1:]])
    else:
        # No shebang, add it
        new_content = f"{SHEBANG_LINE}\n{content}"

    path.write_text(new_content)

    # Make executable if not already
    current_mode = path.stat().st_mode
    if not (current_mode & 0o111):
        path.chmod(current_mode | 0o111)

    click.echo(f"Updated shebang in {path}")


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.argument("dependency")
def add(path: str, dependency: str) -> None:
    """Add a dependency to a script's inline metadata.

    This is a shortcut for 'uv add --script PATH DEPENDENCY'.
    """
    result = subprocess.run(["uv", "add", "--script", path, dependency])
    sys.exit(result.returncode)


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.argument("dependency")
def remove(path: str, dependency: str) -> None:
    """Remove a dependency from a script's inline metadata.

    This is a shortcut for 'uv remove --script PATH DEPENDENCY'.
    """
    result = subprocess.run(["uv", "remove", "--script", path, dependency])
    sys.exit(result.returncode)


def is_click_command(argument: str) -> bool:
    """Return True if the given argument represents a click command."""
    ctx = click.Context(cli)
    return cli.get_command(ctx, argument) is not None


def main() -> None:
    """Main entry point for uvrs CLI."""
    # Check if we're in shebang mode (first arg is not a known subcommand)
    if len(sys.argv) == 1 or sys.argv[1].startswith("-") or is_click_command(sys.argv[1]):
        # No arguments, first argument is a known command, or it's a flag (--help)
        cli()
    else:
        # Shebang mode: first argument is the script path
        run_script(sys.argv[1:])
