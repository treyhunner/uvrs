# uvrs

A tool for managing uv scripts more easily.

Unlike `uv`, `uvrs` adds a shebang line, sets an executable bit, runs scripts with exact dependency syncing, and timestamp-pins requirements by default.


## Why this exists

While `uv` has excellent support for [inline script metadata (PEP 723)][PEP 723], there are several rough edges when managing scripts:

1. **Non-portable shebang**: The [recommended shebang][uv shebang] uses `#!/usr/bin/env -S uv run --script`, which relies on the non-standard `-S` flag that doesn't work on some systems ([uv issue #11876][11876])

2. **No executable bit**: `uv init --script` creates files that aren't executable by default, requiring a manual `chmod +x`

3. **Inconsistent syncing**: `uv run --script` is deliberately inexact by default. It *may* implicitly sync some changes, but doesn't guarantee that the installed dependencies match the virtual environment consistently.

4. **No reproducibility by default**: Scripts don't include `exclude-newer` timestamps, so running the same script weeks later may use different package versions, breaking reproducibility

`uvrs` addresses all of these issues:

- **Portable shebang** that works everywhere: `#!/usr/bin/env uvrs`
- **Executable by default** for new and fixed scripts
- **Consistent syncing** via `uv run --exact --script` which ensures the environment always matches metadata
- **Reproducible by default** with automatic `exclude-newer` timestamps


## Installation

This should be installed as a globally available tool (so the above shebang line works):

```console
uv tool install -p 3.14 uvrs
```

That will install `uvrs` using Python 3.14 (for nicely colorized help text).


## What each command does

Here's what `uvrs` does under the hood, compared to the equivalent `uv` workflow:

### `uvrs init <path>`

This is equivalent to:

```bash
uv init --script <path>
# Add #!/usr/bin/env uvrs shebang
# Add exclude-newer timestamp to metadata
chmod +x <path>
```

### `uvrs fix <path>`

This is equivalent to:

```bash
# Update shebang to #!/usr/bin/env uvrs
# Add exclude-newer timestamp if missing
uv sync --script <path> --upgrade
chmod +x <path>
```

### `uvrs add <path> <package>`

This is equivalent to:

```bash
uv add --script <path> <package>
```

### `uvrs remove <path> <package>`

This is equivalent to:

```bash
uv remove --script <path> <package>
```

### `uvrs stamp <path>`

This is equivalent to:

```bash
# Update exclude-newer timestamp to current time
uv sync --script <path> --upgrade
```

### `uvrs <path>`

This is equivalent to:

```bash
uv run --exact --script <path>
```

Using `--exact` guarantees the managed virtual environment always matches the script's inline metadata before execution.
This means any dependency changes, including those introduced by `uvrs add` or `uvrs remove`, are respected the next time you run the script.


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

To remove a dependency:

```console
uvrs remove ~/bin/my-script 'rich'
```

The environment will sync automatically the next time you run the script (uvrs uses `uv run --exact` which ensures the environment matches the metadata exactly).


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
