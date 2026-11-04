# API contract (v1)

## Health

- `GET /health`
- Назначение: проверить доступность backend.

## Tasks / Events

- `GET /v1/tasks` — список задач.
- `POST /v1/tasks` — создать задачу.
- `POST /v1/tasks/extract` — распознать черновики задач из текста и файлов (multipart, до 3 файлов).
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

### TaskDraft / TaskDrafts (черновик(и) распознавания)

`POST /v1/tasks/extract` принимает `multipart/form-data`:

- `text: string` (необязательное, по умолчанию пустое)
- `file: array of binary` (необязательное; TXT, MD, CSV, JSON, PDF, JPG, PNG, WebP, GIF, BMP).
  Можно передать сразу несколько файлов (лимит — до 3, см. `LOCAL_LLM_MAX_FILES`).

Нужен хотя бы один из параметров `text` или `file`. Размер задаётся
`LOCAL_LLM_MAX_TEXT_KB` и `LOCAL_LLM_MAX_IMAGE_MB`.

Ответ — набор черновиков `TaskDrafts` с полем `tasks` (массив):

```json
{
  "tasks": [
    {
      "title": "короткое название задачи",
      "description": "детали или null",
      "estimated_minutes": 60,
      "priority": 3,
      "deadline": "YYYY-MM-DDTHH:MM:SS или null",
      "workspace_id": "study",
      "project_id": "oop или null",
      "input_kind": "text",
      "warnings": []
    }
  ]
}
```

Массив `tasks` содержит одну задачу или несколько независимых задач
(например, несколько лабораторных из одного текста/файла). Модель сама
определяет, что из материала следует одна задача, а что — несколько; она
не дробит одну задачу на подзадачи, а возвращает самостоятельные задачи.

Чтобы создать задачу, пользователь отправляет её (после проверки/правки)
обычным `POST /v1/tasks`.

- `tasks: TaskDraft[]` — распознанные черновики (от одного до нескольких).
  Каждый черновик содержит те же поля, что и раньше: `title`, `description`,
  `estimated_minutes`, `priority`, `deadline`, `workspace_id`, `project_id`,
  `input_kind`, `warnings`.
- `TaskDraft` — отдельный черновик (элемент массива `tasks`).

Ошибки: `400` — пустой/неподдерживаемый ввод, превышен лимит файлов,
`413` — файл больше лимита, `502` — модель вернула некорректный ответ,
`503` — `llama-server` недоступен или распознавание отключено (`LOCAL_LLM_ENABLED=false`).

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
