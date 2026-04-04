# API contract (v1)

## Health

- `GET /health`
- Назначение: проверить доступность backend.

## Tasks / Events

- `GET /v1/tasks` — список задач.
- `POST /v1/tasks` — создать задачу.
- `PATCH /v1/tasks/{task_id}/status` — изменить статус.
- `GET /v1/events` — список занятых событий.
- `POST /v1/events` — создать событие.

## Schedule

- `POST /v1/schedule/rebuild` — пересчитать расписание.
- `GET /v1/schedule/today` — получить задачи на сегодня + prime-task.

## Integrations

- `GET /v1/integrations` — список доступных провайдеров.
- `POST /v1/integrations/{provider_name}/sync` — синхронизировать провайдер.

## Правила совместимости

- Любое breaking-change изменение API:
  - сначала обсуждается в issue
  - затем обновляются `docs/api-contract.md` и `packages/contracts/openapi.yaml`
  - только после этого вносятся изменения в backend/frontend
