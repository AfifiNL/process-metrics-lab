# Everything here runs offline and costs nothing. `make check` is exactly what CI runs.
UV ?= uv

.PHONY: help install lint fmt typecheck test check

help:            ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install:         ## create .venv with dev tools (locked)
	$(UV) sync

lint:            ## ruff lint + format check
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests

fmt:             ## apply ruff formatting and safe fixes
	$(UV) run ruff format src tests
	$(UV) run ruff check --fix src tests

typecheck:       ## mypy (strict)
	$(UV) run mypy

test:            ## pytest
	$(UV) run pytest

check: lint typecheck test  ## everything CI runs
