.DEFAULT_GOAL := all

sources = frostbound

.PHONY: .uv
.uv:
	@uv -V || echo 'Please install uv: https://docs.astral.sh/uv/getting-started/installation/'

.PHONY: install
install: .uv
	uv sync --frozen --group all --all-extras

.PHONY: format
format:
	uv run ruff check --fix --exit-zero $(sources)
	uv run ruff format $(sources)

.PHONY: lint
lint:
	uv run ruff check $(sources)
	uv run ruff format --check $(sources)

.PHONY: typecheck
typecheck:
	uv run mypy $(sources)
	uv run pyright $(sources)

.PHONY: test
test: .uv
	uv run pytest tests

.PHONY: testcov
testcov: .uv
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml tests

.PHONY: coverage
coverage: .uv
	uv run coverage run -m pytest tests
	uv run coverage report
	uv run coverage html
	uv run coverage xml

.PHONY: docs
docs:
	cd docs && make html

.PHONY: ci
ci: lint typecheck test coverage

.PHONY: rebuild-lockfiles
rebuild-lockfiles: .uv
	uv lock --upgrade

.PHONY: clean
clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]'`
	rm -rf .cache
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -f .coverage
	rm -rf coverage.xml
	rm -rf .mypy_cache
	rm .dmypy.json

.PHONY: help
help:
	@echo "Usage:"
	@echo "  make dev                Run the package with developer settings"
	@echo "  make prod               Run the pacakge with production settings"
	@echo "  make test               CI: Run tests"
	@echo "  make cov                CI: Run test and calculate coverage"
	@echo "  make check              CI: Lint the code"
	@echo "  make format             CI: Format the code"
	@echo "  make type               CI: Check typing"
	@echo "  make doc                Run local documentation server"
	@echo "  make build              Build the package wheel before publishing to Pypi"
	@echo "  make publish            Publish package to Pypi"
	@echo "  make dockerbuild        Build the docker image"
	@echo "  make dockerrun          Run the docker image"
	@echo "  make ci                 Run all CI steps (check, format, type, test coverage)"