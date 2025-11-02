# Show available commands
_default:
    @printf 'Automation tasks:\n'
    @just --list --unsorted --list-heading '' --list-prefix '  - '

# Install prek git hooks
setup:
    uv sync --all-groups
    uv run prek install

# Run all checks (format, lint, test)
check: format lint test

# Format code with ruff and markdown with rumdl
format: _format-code _format-docs

_format-code *files='':
    uv run ruff check --fix {{ files }}
    uv run ruff format {{ files }}

_format-docs *files='':
    uv run rumdl fmt --fix {{ files }}

# Lint source code and docs
lint: _lint-code _lint-docs _typecheck

_lint-code *files='':
    uv run ruff check {{ files }}
    uv run ruff format --check {{ files }}

# Type check with ty
_typecheck *files='':
    uv run ty check {{ files }}

_lint-docs *files='':
    uv run rumdl check {{ files }}

# Run tests
test *args:
    uv run pytest -v {{ args }}

# Run tests with coverage
test-cov:
    uv run pytest --cov=uvrs --cov=tests --cov-report=term-missing --cov-report=html

# Run prek on all files (accepts optional flags/args)
prek *args:
    uv run prek run --all-files {{ args }}

# Bump version (usage: just bump-version patch|minor|major)
bump value:
    uv version --bump {{ value }}

# Build the package
build:
    uv sync  # Force uv version error if applicable
    uv build --clear

# Publish to PyPI
publish:
    uv publish
