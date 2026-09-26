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

### TaskCreate (входные поля)

- `title: string` (обязательное)
- `description: string | null`
- `estimated_minutes: int` (15..1440, по умолчанию `60`)
- `priority: int` (1..4, по умолчанию `3`)
- `deadline: datetime | null`
- `workspace_id: string` (по умолчанию `study`)
- `project_id: string | null`
- `auto_reschedule: bool` (по умолчанию `true`)
- `depends_on: string[]` (ID блокирующих задач, по умолчанию `[]`)
- `allow_split: bool` (по умолчанию `false`)
- `min_chunk_minutes: int | null` (15..1440)

### TaskStatus

- `todo`
- `in_progress`
- `completed`
- `cancelled`
- `blocked`

## Schedule

- `POST /v1/schedule/rebuild` — пересчитать расписание.
- `GET /v1/schedule/today` — получить задачи на сегодня + prime-task.
- `POST /v1/schedule/reorder-feedback` — записать ручной reorder задачи для дообучения модели.

### Reorder feedback payload

- `moved_task_id: string` (обязательное)
- `left_task_id: string | null` (ID задачи слева после ручной перестановки)
- `right_task_id: string | null` (ID задачи справа после ручной перестановки)
- `moved_at: datetime | null` (если не передан, backend берет текущее время)

## Integrations

- `GET /v1/integrations` — список адаптеров со статусом синхронизации.
- `GET /v1/integrations/lessons` — занятия расписания из кэша синхронизации (с учебными неделями).
- `GET /v1/integrations/week` — текущая учебная неделя (1–4) и дата начала семестра.
- `POST /v1/integrations/import` — импорт расписания из JSON-файла портала БГУИР.
- `POST /v1/integrations/sync` — синхронизировать все адаптеры.
- `POST /v1/integrations/{provider_name}/sync` — синхронизировать один адаптер.
- `POST /v1/auth/register` — регистрация (`username`, `password`) → токен.
- `POST /v1/auth/login` — вход → токен.
- `GET /v1/auth/me` — текущий пользователь (заголовок `Authorization: Bearer <token>`).

Задачи, события и планирование (`/v1/tasks`, `/v1/events`, `/v1/schedule/*`)
требуют заголовок `Authorization: Bearer <token>` и возвращают только личные
данные пользователя плюс общие (импортированное расписание).

## Правила совместимости

- Любое breaking-change изменение API:
  - сначала обсуждается в issue
  - затем обновляются `docs/api-contract.md` и `packages/contracts/openapi.yaml`
  - только после этого вносятся изменения в backend/frontend
