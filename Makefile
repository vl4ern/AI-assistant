SHELL := /bin/bash

.PHONY: api-install api-dev api-test web-install web-dev web-lint compose-up compose-down

api-install:
	python3 -m venv .venv && ./.venv/bin/pip install -r apps/api/requirements-dev.txt

api-dev:
	./.venv/bin/uvicorn app.main:app --app-dir apps/api --reload --host 0.0.0.0 --port 8000

api-test:
	PYTHONPATH=apps/api ./.venv/bin/pytest apps/api/tests -q

web-install:
	cd apps/web && npm ci

web-dev:
	cd apps/web && npm run dev

web-lint:
	cd apps/web && npm run lint

compose-up:
	docker compose up --build

compose-down:
	docker compose down
