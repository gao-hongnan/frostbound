.DEFAULT_GOAL := help

PACKAGE_NAME := frostbound
TEST_DIR := tests
SOURCES := $(PACKAGE_NAME) $(TEST_DIR)

.PHONY: .uv
.uv:
	@uv -V || echo 'Please install uv: https://docs.astral.sh/uv/getting-started/installation/'

.PHONY: install
install: .uv
	uv sync --frozen --group all --all-extras

.PHONY: format
format: .uv
	uv run ruff check --fix --exit-zero $(SOURCES)
	uv run ruff format $(SOURCES)

.PHONY: lint
lint: .uv
	uv run ruff check $(SOURCES)
	uv run ruff format --check $(SOURCES)

.PHONY: typecheck
typecheck: .uv
	uv run mypy $(SOURCES)
	uv run pyright $(SOURCES)
	# @echo "Running ty (experimental)..."
	# uv run ty check $(SOURCES) || echo "ty check failed (expected for pre-release)"

.PHONY: test
test: .uv
	uv run pytest $(TEST_DIR)

.PHONY: coverage
coverage: .uv
	uv run coverage run -m pytest $(TEST_DIR)
	uv run coverage report
	uv run coverage html
	uv run coverage xml

.PHONY: docs
docs:
	cd docs && make html

.PHONY: ci
ci: format lint typecheck test coverage

.PHONY: lock
lock: .uv
	uv lock --upgrade

.PHONY: clean
clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]'`
	rm -rf .cache .pytest_cache .ruff_cache .mypy_cache
	rm -rf htmlcov coverage.xml
	rm -f .coverage .dmypy.json

.PHONY: help
help:
	@echo "Development Commands:"
	@echo "  install             Install dependencies"
	@echo "  format              Format code with ruff"
	@echo "  lint                Lint code with ruff"
	@echo "  typecheck           Run type checking with mypy, pyright, and ty"
	@echo "  test                Run tests with pytest"
	@echo "  coverage            Run tests with coverage reporting"
	@echo "  docs                Build documentation"
	@echo "  ci                  Run full CI pipeline (lint, typecheck, test, coverage)"
	@echo ""
	@echo "Utility Commands:"
	@echo "  lock                Update lock files"
	@echo "  clean               Clean build artifacts and cache files"
	@echo "  help                Show this help message"