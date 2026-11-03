SHELL := /bin/bash

-include .env
export

API_PORT ?= 8000

.PHONY: api-install api-dev api-test models llm-dev web-install web-dev web-lint up logs compose-up compose-down

api-install:
	python3 -m venv .venv && ./.venv/bin/pip install -r apps/api/requirements-dev.txt

api-dev:
	./.venv/bin/uvicorn app.main:app --app-dir apps/api --reload --host 0.0.0.0 --port $(API_PORT)

api-test:
	PYTHONPATH=apps/api ./.venv/bin/pytest apps/api/tests -q

models:
	./scripts/download-models.sh

llm-dev: models
	./scripts/run-llama-server.sh

web-install:
	cd apps/web/frontend && npm ci

web-dev:
	cd apps/web/frontend && npm run dev -- --host 0.0.0.0 --port 5173

web-lint:
	cd apps/web/frontend && npm run lint

up: models
	docker compose up -d --build

logs:
	docker compose logs -f api llm

compose-up: models
	docker compose up --build

compose-down:
	docker compose down
