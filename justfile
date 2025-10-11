# Default recipe - show available commands
default:
    @just --list

# Run all checks (format, lint, typecheck, test)
check: format lint typecheck test lint-readme

# Format code with ruff
format:
    uv run ruff format src/ tests/

# Check code formatting without making changes
format-check:
    uv run ruff format --check src/ tests/

# Lint code with ruff
lint:
    uv run ruff check src/ tests/

# Lint and auto-fix issues
lint-fix:
    uv run ruff check --fix src/ tests/

# Type check with mypy
typecheck:
    uv run mypy src/

# Run tests
test:
    uv run pytest tests/ -v

# Run tests with coverage
test-cov:
    uv run pytest tests/ --cov=uvrs --cov-report=term-missing --cov-report=html

# Run tests quickly (no output)
test-quick:
    uv run pytest tests/ -q

# Watch tests (requires pytest-watch)
test-watch:
    uv run ptw tests/ -- -v

# Install prek hooks
prek-install:
    uv run prek install

# Run prek on all files
prek-all:
    uv run prek run --all-files

# Lint README with markdown linter (placeholder - specify which tool you want)
lint-readme:
    @echo "README linting not yet configured. Did you mean a specific tool?"
    @echo "Options: mdl, markdownlint-cli, mdformat, etc."

# Clean up generated files
clean:
    rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Build the package
build:
    uv build

# Install package locally for testing
install:
    uv tool install .

# Reinstall package locally
reinstall:
    uv tool uninstall uvrs || true
    uv tool install .

# Bump version (usage: just bump-version patch|minor|major)
bump-version VERSION:
    # This would use a tool like bump2version or similar
    @echo "Version bumping not yet configured. Current version in pyproject.toml"
    @grep "^version = " pyproject.toml
