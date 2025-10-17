"""Create and run uv scripts with a POSIX-friendly shebang."""

from __future__ import annotations

import importlib.metadata
import re
import shlex
import subprocess
import sys
from argparse import ArgumentParser, ArgumentTypeError, Namespace, _SubParsersAction
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from os import PathLike, execvp
from pathlib import Path

from rich import print
from tomlkit import dumps, parse, table

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CommandArgs = Sequence[str | PathLike[str]]


def readable_path(value: str) -> Path:
    """Argparse type that accepts only paths pointing to files."""
    path = Path(value)
    if not path.exists():
        raise ArgumentTypeError(f"{value} does not exist")
    if not path.is_file():
        raise ArgumentTypeError(f"{value} is not a file")
    return path


def args_join(args: CommandArgs) -> str:
    """Return a shell-quoted representation of ``args`` for logging."""
    return shlex.join(str(arg) for arg in args)


def fail(message: str, exit_code: int = 1) -> None:
    """Print ``message`` to stderr and exit the process."""
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


def run_uv_command(args: CommandArgs) -> None:
    """Log and execute a ``uv`` CLI command, preserving exit codes."""
    print(f"[bold cyan]→ uvrs executing:[/] {args_join(args)}")
    try:
        subprocess.run([str(arg) for arg in args], check=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise SystemExit(exc.returncode) from None


def run_script(args: Sequence[str]) -> None:
    """Delegate execution to ``uv run --exact --script`` replacing the current process."""
    execvp("uv", ["uv", "run", "--exact", "--script", *args])


# ---------------------------------------------------------------------------
# PEP 723 Inline Metadata Helpers
# ---------------------------------------------------------------------------

# PEP 723 regex pattern
METADATA_REGEX = re.compile(
    r"""
    ^ [#] [ ] /// [ ] script $      # "# /// script"
    \s                              # followed by newline (and any whitespace)
    (?P<content>
        (                           # One or more lines of:
            ^ [#] ( | [ ] .* ) $    # "#" (blank) or "# content"
            \s                      # followed by newline (and any whitespace)
        )+
    )
    ^ [#] [ ] /// $                 # "# ///"
    """,
    flags=re.MULTILINE | re.VERBOSE,
)


def get_current_timestamp() -> str:
    """Return current UTC timestamp in RFC 3339 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_metadata_block(content: str) -> re.Match[str] | None:
    """
    Extract the PEP 723 script metadata block from file content.

    Returns:
        Match object or None if not found
    """
    match list(METADATA_REGEX.finditer(content)):
        case [match]:
            return match
        case []:
            return None
        case _:
            raise ValueError("Multiple PEP 723 script blocks found")


def parse_metadata(match: re.Match[str]) -> str:
    """
    Extract TOML content from a PEP 723 metadata block.

    Returns the raw TOML string (without comment prefixes).
    """
    return "\n".join(
        line.removeprefix("#").removeprefix(" ")
        for line in match.group("content").splitlines()
    )


def format_metadata(toml_content: str) -> str:
    """
    Format TOML content as a PEP 723 metadata block.

    Adds comment prefixes and wraps with /// script markers.
    Does not include a trailing newline after # /// to avoid duplicating
    the newline that already exists in the content after the block.
    """
    commented_lines = [
        f"# {line}" if line else "#" for line in toml_content.splitlines()
    ]
    return "# /// script\n" + "\n".join(commented_lines) + "\n# ///"


def update_exclude_newer(script_path: Path) -> str:
    """
    Add or update exclude-newer in the script's PEP 723 metadata.

    Args:
        script_path: Path to the Python script

    Returns:
        The timestamp that was set
    """
    timestamp = get_current_timestamp()
    content = script_path.read_text()

    if match := extract_metadata_block(content):
        # Parse metadata TOML and update timestamp
        doc = parse(parse_metadata(match))
        doc.setdefault("tool", table()).setdefault("uv", table())  # type: ignore[union-attr]
        doc["tool"]["uv"]["exclude-newer"] = timestamp  # type: ignore[index]

        # Format back to PEP 723 block and replace in content
        new_block = format_metadata(dumps(doc))
        new_content = content[: match.start()] + new_block + content[match.end() :]
    else:
        # Create minimal PEP 723 metadata block
        new_block = format_metadata(
            dumps({"dependencies": [], "tool": {"uv": {"exclude-newer": timestamp}}})
        )

        # Insert after shebang if present, otherwise at start
        if content.startswith("#!"):
            lines = content.splitlines(keepends=True)
            new_content = lines[0] + new_block + "\n" + "".join(lines[1:])
        else:
            new_content = new_block + "\n" + content

    script_path.write_text(new_content)
    return timestamp


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def handle_init(args: Namespace, extras: Sequence[str]) -> None:
    """Implement ``uvrs init``."""
    path: Path = args.path
    python_version = args.python_version
    no_stamp = args.no_stamp

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

    print(f"Updated shebang in `[cyan]{path}[/]`")

    if not no_stamp:
        # Add timestamp
        timestamp = update_exclude_newer(path)
        print(f"Set [cyan]exclude-newer[/] to [yellow]{timestamp}[/]")


def handle_fix(args: Namespace, extras: Sequence[str]) -> None:
    """Ensure an existing script uses the uvrs shebang."""
    if extras:
        fail(
            f"[bold red]error[/]: unrecognized arguments [yellow]{args_join(extras)}[/]"
        )

    path: Path = args.path
    no_stamp = args.no_stamp

    content = path.read_text()
    if content.startswith("#!"):
        new_content = "\n".join(["#!/usr/bin/env uvrs", *content.splitlines()[1:]])
    else:
        new_content = f"#!/usr/bin/env uvrs\n{content}"
    path.write_text(new_content)

    current_mode = path.stat().st_mode
    if not (current_mode & 0o111):
        path.chmod(current_mode | 0o111)

    print(f"Updated shebang in `[cyan]{path}[/]`")

    if not no_stamp:
        # Add/update timestamp (create metadata if it doesn't exist)
        timestamp = update_exclude_newer(path)
        print(f"Set [cyan]exclude-newer[/] to [yellow]{timestamp}[/]")
        # Sync with upgrade to ensure environment is fresh
        run_uv_command(["uv", "sync", "--script", path, "--upgrade"])


def handle_add(args: Namespace, extras: Sequence[str]) -> None:
    """Forward to ``uv add --script`` with any additional arguments."""
    run_uv_command(["uv", "add", "--script", args.path, *extras])


def handle_remove(args: Namespace, extras: Sequence[str]) -> None:
    """Forward to ``uv remove --script`` with any additional arguments."""
    run_uv_command(["uv", "remove", "--script", args.path, *extras])


def handle_stamp(args: Namespace, extras: Sequence[str]) -> None:
    """Add or update exclude-newer timestamp in the script metadata."""
    path: Path = args.path

    if extras:
        fail(
            f"[bold red]error[/]: unrecognized arguments [yellow]{args_join(extras)}[/]"
        )

    # Update the timestamp (create metadata if it doesn't exist)
    timestamp = update_exclude_newer(path)
    print(f"Set [cyan]exclude-newer[/] to [yellow]{timestamp}[/] in `[cyan]{path}[/]`")

    # Upgrade requirements to match the new timestamp
    run_uv_command(["uv", "sync", "--script", path, "--upgrade"])


# ---------------------------------------------------------------------------
# Parser / entrypoint
# ---------------------------------------------------------------------------


def _version_string() -> str:
    return importlib.metadata.version("uvrs")


def create_parser() -> ArgumentParser:
    """Build the top-level argparse parser."""
    parser = ArgumentParser(
        prog="uvrs",
        description="Create and run uv scripts with POSIX standardized shebang line",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"uvrs {_version_string()}",
    )

    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser(
        "init",
        help="Create a new script via `uv init --script` and add the uvrs shebang",
        add_help=True,
    )
    init_parser.add_argument("path", type=Path)
    init_parser.add_argument("--python", dest="python_version")
    init_parser.add_argument(
        "--no-stamp",
        action="store_true",
        help="Skip adding exclude-newer timestamp to metadata",
    )
    init_parser.set_defaults(handler=handle_init, parser=init_parser)

    fix_parser = subparsers.add_parser(
        "fix",
        help="Ensure a script starts with the uvrs shebang",
    )
    fix_parser.add_argument("path", type=readable_path)
    fix_parser.add_argument(
        "--no-stamp",
        action="store_true",
        help="Skip adding/updating exclude-newer timestamp",
    )
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

    stamp_parser = subparsers.add_parser(
        "stamp",
        help="Add or update exclude-newer timestamp and upgrade dependencies",
    )
    stamp_parser.add_argument("path", type=readable_path)
    stamp_parser.set_defaults(handler=handle_stamp, parser=stamp_parser)

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
        parser.print_help()
        return

    if args_list[0].startswith("-") or args_list[0] in _command_names(parser):
        namespace, extras = parser.parse_known_args(args_list)
        handler = getattr(namespace, "handler", None)
        if handler is None:
            fail("No command specified")
        assert callable(handler)
        handler(namespace, extras)
    else:
        run_script(args_list)
