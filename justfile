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
format:
    uv run ruff check --fix
    uv run ruff format
    uv run rumdl fmt --fix

# Lint source code and docs
lint: _lint-code _lint-docs _typecheck

_lint-code:
    uv run ruff check
    uv run ruff format --check

# Type check with mypy
_typecheck:
    uv run mypy .

_lint-docs:
    uv run rumdl check

# Run tests
test *args:
    uv run pytest -v {{ args }}

# Run tests with coverage
test-cov:
    uv run pytest --cov=uvrs --cov-report=term-missing --cov-report=html

# Run prek on all files (accepts optional flags/args)
prek *args:
    uv run prek run --all-files {{ args }}

# Bump version (usage: just bump-version patch|minor|major)
bump value:
    uv version --bump {{ value }}

# Build the package
build:
    uv build

# Publish to PyPI
publish:
    uv publish
