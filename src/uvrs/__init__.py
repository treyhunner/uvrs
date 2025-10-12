"""Create and run uv scripts with a POSIX-friendly shebang."""

from __future__ import annotations

import shlex
import subprocess
import sys
from argparse import ArgumentParser, ArgumentTypeError, Namespace, _SubParsersAction
from collections.abc import Iterable, Sequence
from os import PathLike, execvp
from pathlib import Path

from rich import print as rprint

CommandArgs = Sequence[str | PathLike[str]]


def readable_path(value: str) -> Path:
    """Argparse type that accepts only existing files."""
    path = Path(value)
    if not path.exists():
        raise ArgumentTypeError(f"{value} does not exist")
    if not path.is_file():
        raise ArgumentTypeError(f"{value} is not a file")
    return path


def args_join(args: CommandArgs) -> str:
    """Return shell-quoted command arguments for display."""
    return shlex.join(str(arg) for arg in args)


def fail(message: str, exit_code: int = 1) -> None:
    """Emit an error message and exit immediately."""
    rprint(message, file=sys.stderr)
    raise SystemExit(exit_code)


def run_uv_command(args: CommandArgs) -> None:
    """Log and execute a uv command, surfacing failures via exit codes."""
    rprint(f"[bold cyan]→ uvrs executing:[/] {args_join(args)}")
    try:
        subprocess.run([str(arg) for arg in args], check=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise SystemExit(exc.returncode) from None


def run_script(args: Sequence[str]) -> None:
    """Execute ``uv run --script`` replacing the current process."""
    execvp("uv", ["uv", "run", "--script", *args])


def handle_init(args: Namespace, extras: Sequence[str]) -> None:
    """Implement ``uvrs init``."""
    path: Path = args.path
    python_version = args.python_version

    if path.exists():
        fail(
            f"File already exists at `[cyan]{path}[/]`\n"
            f"To add or update the shebang use: [cyan]uvrs fix {path}[/]",
        )

    extra_args = list(extras)
    if python_version:
        extra_args = ["--python", python_version, *extra_args]

    run_uv_command(["uv", "init", "--script", path, *extra_args])

    content = path.read_text()
    path.write_text(f"#!/usr/bin/env uvrs\n{content}")
    path.chmod(path.stat().st_mode | 0o111)

    rprint(f"Updated shebang in `[cyan]{path}[/]`")


def handle_fix(args: Namespace, extras: Sequence[str]) -> None:
    """Implement ``uvrs fix`` by ensuring the shebang is correct."""
    path: Path = args.path

    if extras:
        fail(f"[bold red]error[/]: unrecognized arguments [yellow]{args_join(extras)}[/]")

    content = path.read_text()
    if content.startswith("#!"):
        new_content = "\n".join(["#!/usr/bin/env uvrs", *content.splitlines()[1:]])
    else:
        new_content = f"#!/usr/bin/env uvrs\n{content}"
    path.write_text(new_content)

    current_mode = path.stat().st_mode
    if not (current_mode & 0o111):
        path.chmod(current_mode | 0o111)

    rprint(f"Updated shebang in `[cyan]{path}[/]`")


def handle_add(args: Namespace, extras: Sequence[str]) -> None:
    """Implement ``uvrs add`` by delegating to ``uv add``."""
    run_uv_command(["uv", "add", "--script", args.path, *extras])


def handle_remove(args: Namespace, extras: Sequence[str]) -> None:
    """Implement ``uvrs remove`` by delegating to ``uv remove``."""
    run_uv_command(["uv", "remove", "--script", args.path, *extras])


def create_parser() -> ArgumentParser:
    """Build the top-level argparse parser."""
    parser = ArgumentParser(
        prog="uvrs",
        description="Create and run uv scripts with POSIX standardized shebang line",
    )
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser(
        "init",
        help="Create a new script via `uv init --script` and add the uvrs shebang",
        add_help=True,
    )
    init_parser.add_argument("path", type=Path)
    init_parser.add_argument("--python", dest="python_version")
    init_parser.set_defaults(handler=handle_init, parser=init_parser)

    fix_parser = subparsers.add_parser(
        "fix",
        help="Ensure a script starts with the uvrs shebang",
    )
    fix_parser.add_argument("path", type=readable_path)
    fix_parser.set_defaults(handler=handle_fix, parser=fix_parser)

    add_parser = subparsers.add_parser(
        "add",
        help="Forward to `uv add --script` with the provided arguments",
    )
    add_parser.add_argument("path", type=readable_path)
    add_parser.set_defaults(handler=handle_add, parser=add_parser)

    remove_parser = subparsers.add_parser(
        "remove",
        help="Forward to `uv remove --script` with the provided arguments",
    )
    remove_parser.add_argument("path", type=readable_path)
    remove_parser.set_defaults(handler=handle_remove, parser=remove_parser)

    return parser


def _command_names(parser: ArgumentParser) -> set[str]:
    """Extract the first-level command names from the parser."""
    return next(
        set(action.choices.keys())
        for action in parser._actions
        if isinstance(action, _SubParsersAction)
    )


def main(argv: Iterable[str] | None = None) -> None:
    """Entry point for the ``uvrs`` command."""
    args_list = list(argv if argv is not None else sys.argv[1:])

    parser = create_parser()
    if not args_list:
        print(parser.format_help())
    elif args_list[0].startswith("-") or args_list[0] in _command_names(parser):
        args, extras = parser.parse_known_args(args_list)
        args.handler(args, extras)
    else:
        run_script(args_list)
