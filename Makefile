# Everything here runs offline and costs nothing. `make check` is exactly what CI runs.
UV ?= uv

.PHONY: help install lint fmt typecheck test check demo site sample

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

test:            ## pytest: generates the data, runs the SQL, compares with the reference
	$(UV) run pytest

check: lint typecheck test  ## everything CI runs

demo:            ## generate the data, run the SQL, print the KPI table and planted-and-found
	$(UV) run process-metrics-lab demo

site:            ## build site/index.html (run `make demo` first, or it has no data)
	$(UV) run process-metrics-lab site

sample:          ## refresh data/sample_events.csv (the first 200 rows of the event log)
	mkdir -p data && head -n 201 build/events.csv > data/sample_events.csv
