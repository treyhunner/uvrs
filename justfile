# Default recipe - show available commands
default:
    @just --list

# Install prek git hooks
setup:
    uv sync --all-groups
    uv run prek install

# Run all checks (format, lint, typecheck, test)
check: format lint typecheck test lint-readme

# Format code with ruff
format:
    uv run ruff check --fix
    uv run ruff format

# Lint code with ruff
lint:
    uv run ruff check

# Type check with mypy
typecheck:
    uv run mypy src/

# Run tests
test:
    uv run pytest -v

# Run tests with coverage
test-cov:
    uv run pytest tests/ --cov=uvrs --cov-report=term-missing --cov-report=html

# Run prek on all files
prek:
    uv run prek run --all-files

# Lint README with markdown linter (placeholder - specify which tool you want)
lint-readme:
    @echo "README linting not yet configured. Did you mean a specific tool?"
    @echo "Options: mdl, markdownlint-cli, mdformat, etc."

# Clean up generated files
clean:
    rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Bump version (usage: just bump-version patch|minor|major)
bump value:
    uv version --bump {{ value }}

# Build the package
build:
    uv build

# Publish to PyPI
publish:
    uv publish
