# uvrs

This program is meant to be used in a shebang line, like this:

```python
#!/usr/bin/env uvrs
```

Unlike the shebang line [recommended by uv's documentation][uv shebang], the above shebang does not rely on the non-standard `-S` option (see [uv issue 11876][11876]).


## Installation

This should be installed as a globally available tool (so the above shebang line works):

```console
uv tool install uvrs
```


## Primary Usage

The primary purpose of the `uvrs` command is to accept a filename to be run as a uv script.

The `uvrs` command is not designed to run a script on its own.
If you need to run a script, use `uv run` for that.

The `uvrs` command can *also* be used to:

1. Create new uv scripts with a `uvrs` shebang line
2. Update existing uv scripts to use a `uvrs` shebang line


## Creating new uv scripts

To initialize a new uv script with a `uvrs` shebang line use the `init` command:

```console
uvrs init ~/bin/my-script --python 3.12
```

This will create the file `~/bin/my-script` using `uv init --script ~/bin/my-script --python 3.12` and then add an appropriate shebang line to the beginning of the script:

```python
#!/usr/bin/env uvrs
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///


def main() -> None:
    print("Hello from my-script!")


if __name__ == "__main__":
    main()
```


## Updating existing uv scripts

To update an existing uv script to use the `uvrs` shebang, use the `fix` command:

```console
uvrs fix ~/bin/my-script
```

If the file does not yet have a shebang line, this shebang line will be added:

```python
#!/usr/bin/env uvrs
```

If the file being fixed already has a shebang line which uses `uv run`, the shebang will be updated to use `uvrs` instead.


## Managing dependencies

To update the dependencies within inline script metadata, use `uvrs add` and `uvrs remove`.

To add a new dependency:

```console
uvrs add ~/bin/my-script 'rich'
```

This is simply a shortcut for running `uv add --script ~/bin/my-script` 'rich'`.

To remove a new dependency:

```console
uvrs remove ~/bin/my-script 'rich'
```

This is simply a shortcut for running `uv remove --script ~/bin/my-script` 'rich'`.


## The goal

Eventually, I would like to see a similar tool [integrated into uv][16241].

Until that time, I plan to maintain this uvrs tool.


[uv shebang]: https://docs.astral.sh/uv/guides/scripts/#using-a-shebang-to-create-an-executable-file
[11876]: https://github.com/astral-sh/uv/issues/11876
[16241]: https://github.com/astral-sh/uv/issues/16241
