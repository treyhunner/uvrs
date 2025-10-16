# uvrs

A tool for managing uv scripts more easily.

This is `uv run --script`, `uv add --script`, and `uv remove --script` rolled into one, with calls to `uv sync --script` automatically made to minimize unhappy surprises with the automatically-managed virtual environment.

Unlike `uv`, `uvrs` adds a shebang line, sets an executable bit, and uses timestamp-pins requirements by default.


## Why this exists

While `uv` has excellent support for [inline script metadata (PEP 723)][PEP 723], there are several rough edges when managing scripts:

1. **Non-portable shebang**: The [recommended shebang][uv shebang] uses `#!/usr/bin/env -S uv run --script`, which relies on the non-standard `-S` flag that doesn't work on some systems ([uv issue #11876][11876])

2. **No executable bit**: `uv init --script` creates files that aren't executable by default, requiring a manual `chmod +x`

3. **Inconsistent syncing**: After `uv add --script` or `uv remove --script`, the virtual environment isn't synced - running the script *may* implicitly sync new packages, but removed packages always stay installed until you manually run `uv sync --script`

4. **No reproducibility by default**: Scripts don't include `exclude-newer` timestamps, so running the same script weeks later may use different package versions, breaking reproducibility

`uvrs` addresses all of these issues:

- **Portable shebang** that works everywhere: `#!/usr/bin/env uvrs`
- **Executable by default** for new and fixed scripts
- **Automatic syncing** after add/remove operations
- **Reproducible by default** with automatic `exclude-newer` timestamps


## Installation

This should be installed as a globally available tool (so the above shebang line works):

```console
uv tool install -p 3.14 uvrs
```

That will install `uvrs` using Python 3.14 (for nicely colorized help text).


## Primary Usage

The primary purpose of the `uvrs` command is to accept a filename to be run as a uv script.

The `uvrs` command is not designed to run a script on its own.
If you need to run a script, use `uv run` for that.

The `uvrs` command can *also* be used to:

1. Create new uv scripts with a `uvrs` shebang line and `exclude-newer` timestamp
2. Update existing uv scripts to use a `uvrs` shebang line and `exclude-newer` timestamp

This is the shebang line `uvrs` uses:

```python
#!/usr/bin/env uvrs
```

Unlike the shebang line [recommended by uv's documentation][uv shebang], the above shebang does not rely on the non-standard `-S` option (see [uv issue 11876][11876]).


## Creating new uv scripts

To initialize a new uv script with a `uvrs` shebang line use the `init` command:

```console
uvrs init ~/bin/my-script --python 3.12
```

This will create the file `~/bin/my-script` using `uv init --script ~/bin/my-script --python 3.12` and then add an appropriate shebang line to the beginning of the script.

By default, `uvrs init` also adds an `exclude-newer` timestamp to improve reproducibility:

```python
#!/usr/bin/env uvrs
# /// script
# requires-python = ">=3.12"
# dependencies = []
#
# [tool.uv]
# exclude-newer = "2025-10-15T20:30:45Z"
# ///


def main() -> None:
    print("Hello from my-script!")


if __name__ == "__main__":
    main()
```

To skip adding the timestamp, use `--no-stamp`:

```console
uvrs init ~/bin/my-script --no-stamp
```


## Updating existing scripts

To update an existing Python script to use the `uvrs` shebang, use the `fix` command:

```console
uvrs fix ~/bin/my-script
```

This command:

1. Updates the shebang to `#!/usr/bin/env uvrs`
2. Adds PEP 723 metadata with an `exclude-newer` timestamp (if not present)
3. Runs `uv sync --script --upgrade` to ensure the environment is up to date

For example, a plain Python script like:

```python
#!/usr/bin/env python
print("Hello!")
```

Will be transformed to:

```python
#!/usr/bin/env uvrs
# /// script
# dependencies = []
#
# [tool.uv]
# exclude-newer = "2025-10-16T00:25:00Z"
# ///

print("Hello!")
```

To skip adding the timestamp and metadata, use `--no-stamp`:

```console
uvrs fix ~/bin/my-script --no-stamp
```


## Managing dependencies

To update the dependencies within inline script metadata, use `uvrs add` and `uvrs remove`.

To add a new dependency:

```console
uvrs add ~/bin/my-script 'rich'
```

This runs `uv add --script ~/bin/my-script 'rich'` followed by
`uv sync --script ~/bin/my-script`, so the dependency is installed immediately.

To remove a new dependency:

```console
uvrs remove ~/bin/my-script 'rich'
```

This runs `uv remove --script ~/bin/my-script 'rich'` and then
`uv sync --script ~/bin/my-script` to keep the resolved environment up to date.


## Updating timestamps and upgrading dependencies

To update the `exclude-newer` timestamp and upgrade all dependencies to the latest versions allowed by your constraints, use the `stamp` command:

```console
uvrs stamp ~/bin/my-script
```

This command:

1. Updates the `exclude-newer` field in the script's `[tool.uv]` section to the current UTC timestamp
2. Runs `uv sync --script --upgrade` to upgrade dependencies and rebuild the environment

The `exclude-newer` field limits package versions to those published before the specified timestamp, which [improves reproducibility](https://docs.astral.sh/uv/guides/scripts/#improving-reproducibility) by preventing unexpected updates.


## The goal

Eventually, I would like to see a similar tool [integrated into uv][16241].

Until that time, I plan to maintain this uvrs tool.


[PEP 723]: https://peps.python.org/pep-0723/
[uv shebang]: https://docs.astral.sh/uv/guides/scripts/#using-a-shebang-to-create-an-executable-file
[11876]: https://github.com/astral-sh/uv/issues/11876
[16241]: https://github.com/astral-sh/uv/issues/16241
