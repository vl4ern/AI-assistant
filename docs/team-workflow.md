# Работа команды из 4 человек

## Роли и зоны владения

1. Интеллект ассистента
- Папка: `apps/api/app/modules/intelligence`
- Ответственность: scoring, planner, пересчет расписания, prime-task.
- Основные API: `/v1/schedule/*`.

2. Frontend
- Папка: `apps/web`
- Ответственность: экраны Today/Calendar/Projects/Analytics, auth flow, UX.
- Основные API: `/v1/tasks`, `/v1/schedule/today`, `/v1/integrations/*`.

3. База знаний
- Папка: `apps/api/app/modules/knowledge`
- Ответственность: модели данных, repository layer, PostgreSQL схема, миграции, индексы.
- Основные API: `/v1/tasks`, `/v1/events`.

4. Интеграции
- Папка: `apps/api/app/modules/integrations`
- Ответственность: OAuth, импорт/экспорт, синхронизация Google/GitHub/LMS.
- Основные API: `/v1/integrations/*`.

## Как не мешать друг другу

- Не редактировать чужой модуль без отдельного согласования.
- Любое изменение общего API сначала фиксируется в `docs/api-contract.md` и `packages/contracts/openapi.yaml`.
- Для cross-module правок делать отдельный PR с пометкой `contract-change`.

## Обязательные weekly-артефакты

- Короткий demo-запуск своего модуля.
- PR в `develop` с описанием, что поменялось.
- Обновленные тесты для своей зоны.
