UV_VERSION := 0.11.33
PYTHON_VERSION ?= 3.14.7
COMPOSE_PROJECT_NAME := amra-phase1

.PHONY: bootstrap services migrate verify demo sbom clean

bootstrap:
	@test "$$(uv --version | awk '{print $$2}')" = "$(UV_VERSION)"
	uv python install $(PYTHON_VERSION)
	uv sync --locked --python $(PYTHON_VERSION)
	./scripts/build_toolchain.sh
	uv run --python $(PYTHON_VERSION) python scripts/generate_sbom.py

services:
	docker compose -p $(COMPOSE_PROJECT_NAME) up -d postgres temporal minio

migrate:
	uv run --python $(PYTHON_VERSION) amra db migrate

verify:
	uv sync --locked --python $(PYTHON_VERSION)
	uv run --python $(PYTHON_VERSION) ruff format --check src tests scripts
	uv run --python $(PYTHON_VERSION) ruff check src tests scripts
	uv run --python $(PYTHON_VERSION) pyright src
	uv run --python $(PYTHON_VERSION) python scripts/validate_contracts.py
	uv run --python $(PYTHON_VERSION) python scripts/secret_scan.py
	uv run --python $(PYTHON_VERSION) python scripts/generate_sbom.py
	git diff --exit-code -- uv.lock sbom
	uv export --python $(PYTHON_VERSION) --locked --no-dev --no-emit-project -o build/runtime-requirements.txt
	uv run --python $(PYTHON_VERSION) pip-audit --strict --progress-spinner=off -r build/runtime-requirements.txt
	uv run --python $(PYTHON_VERSION) pytest
	uv run --python $(PYTHON_VERSION) coverage json -o build/coverage.json
	uv run --python $(PYTHON_VERSION) python scripts/check_critical_coverage.py

demo:
	uv run --python $(PYTHON_VERSION) amra demo trust-loop tests/fixtures/unsat.cnf

sbom:
	uv run --python $(PYTHON_VERSION) python scripts/generate_sbom.py

clean:
	-docker compose -p $(COMPOSE_PROJECT_NAME) down --volumes --remove-orphans
	rm -rf -- .amra/artifacts .amra/workspaces build/toolchain
