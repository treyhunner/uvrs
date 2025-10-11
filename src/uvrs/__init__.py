"""uvrs - Create and run uv scripts with POSIX standardized shebang line."""

import os
import shlex
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


def run_uv_command(args: list[str]) -> None:
    """Run a uv CLI command, echoing it first and exiting on failure."""
    click.echo(f"Running: {' '.join(shlex.quote(arg) for arg in args)}")
    try:
        subprocess.run(args, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from None


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


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("path", type=click.Path(path_type=Path))
@click.argument("uv_args", nargs=-1, type=click.UNPROCESSED)
@click.option("--python", "python_version", help="Python version constraint (e.g., 3.12)")
def init(path: Path, uv_args: tuple[str, ...], python_version: str | None) -> None:
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
    extra_args = list(uv_args)
    if python_version:
        extra_args = ["--python", python_version, *extra_args]

    cmd = ["uv", "init", "--script", str(path), *extra_args]

    run_uv_command(cmd)

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


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("path", type=click.Path(exists=True))
@click.argument("uv_args", nargs=-1, type=click.UNPROCESSED)
def add(path: str, uv_args: tuple[str, ...]) -> None:
    """Add a dependency to a script's inline metadata.

    This is a shortcut for 'uv add --script PATH DEPENDENCY'.
    """
    if not uv_args:
        raise click.ClickException("Please specify at least one dependency to add.")

    run_uv_command(["uv", "add", "--script", path, *uv_args])


@cli.command(context_settings={"ignore_unknown_options": True})
@click.argument("path", type=click.Path(exists=True))
@click.argument("uv_args", nargs=-1, type=click.UNPROCESSED)
def remove(path: str, uv_args: tuple[str, ...]) -> None:
    """Remove a dependency from a script's inline metadata.

    This is a shortcut for 'uv remove --script PATH DEPENDENCY'.
    """
    if not uv_args:
        raise click.ClickException("Please specify at least one dependency to remove.")

    run_uv_command(["uv", "remove", "--script", path, *uv_args])


def is_click_command(argument: str) -> bool:
    """Return True if the given argument represents a click command."""
    ctx = click.Context(cli)
    return cli.get_command(ctx, argument) is not None


def main() -> None:
    """Main entry point for uvrs CLI."""
    # Check if we're in shebang mode (first arg is not a known subcommand)
    args = sys.argv[1:]
    if not args or args[0].startswith("-") or is_click_command(args[0]):
        # No arguments, first argument is a known command, or it's a flag (--help)
        cli()
    else:
        # Shebang mode: first argument is the script path
        try:
            run_script(args)
        except click.ClickException as exc:
            exc.show()
            sys.exit(getattr(exc, "exit_code", 1))
