# AI Assistant

Интеллектуальный ассистент для планирования учебной нагрузки, дедлайнов и личных задач.

Этот репозиторий приведен к рабочей модульной архитектуре под команду из 4 человек, где каждый разрабатывает свою часть параллельно и с минимальными конфликтами.

## Текущий статус

- Собран базовый монорепо-каркас: `apps/web` + `apps/api` + `docs` + `packages/contracts`.
- Реализован рабочий backend-контур с API-роутами, in-memory knowledge base, greedy-планировщиком и заглушками интеграций.
- Поднят стартовый frontend с проверкой связи с API.
- Добавлены правила работы команды: архитектура, роли, Git workflow, roadmap.

## Структура репозитория

```text
AI-assistant/
  apps/
    api/                # FastAPI backend (intelligence + knowledge + integrations)
    web/                # Frontend модуль (активное приложение: apps/web/frontend, React + Vite)
  docs/
    architecture.md
    team-workflow.md
    git-workflow.md
    roadmap.md
    api-contract.md
    product-vision.md
  packages/
    contracts/
      openapi.yaml
  legacy/
    web-prototypes/    # старые наработки, не участвуют в текущем запуске
  images/               # материалы из изначального описания проекта
  Makefile
  docker-compose.yml
  .env.example
```

## Распределение ролей (1 человек = 1 модуль)

- Интеллект ассистента: `apps/api/app/modules/intelligence`
- Веб-интерфейс: `apps/web`
- База знаний (модели/репозитории/БД): `apps/api/app/modules/knowledge`
- Интеграции: `apps/api/app/modules/integrations`

Подробно: `docs/team-workflow.md`.


## Важно по запуску исправленной версии

Подробная инструкция лежит в файле `RUN_FIXED_PROJECT.md`.

Коротко:

```bash
cp .env.example .env
docker compose up --build
```

Открыть:

- Frontend: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- Health-check: `http://localhost:8000/health`

## Быстрый запуск (локально)

1. Перейти в проект:
   ```bash
   cd AI-assistant
   ```
2. Скопировать переменные окружения:
   ```bash
   cp .env.example .env
   ```
3. Запустить backend:
   ```bash
   make api-install
   make api-dev
   ```
4. В другом терминале запустить frontend:
   ```bash
   make web-install
   make web-dev
   ```
5. Открыть:
   - Frontend: `http://localhost:5173`
   - API docs: `http://localhost:8000/docs`

## Запуск через Docker

```bash
cp .env.example .env
make compose-up
```

## Командная работа

- Архитектура и границы модулей: `docs/architecture.md`
- Git-ветки, PR, merge-процесс: `docs/git-workflow.md`
- API-контракты между модулями: `docs/api-contract.md`
- План по этапам разработки: `docs/roadmap.md`
- Детальный старт на ближайший спринт: `docs/start-plan.md`
