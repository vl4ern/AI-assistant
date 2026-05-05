# AI Assistant

MVP базы знаний интеллектуального ассистента планирования учебной нагрузки, дедлайнов и личных задач.

Проект разрабатывается в рамках курсового проектирования. Для 4 семестра основной акцент сделан на модуле базы знаний: хранении фактов о задачах, событиях, зависимостях, дедлайнах, приоритетах и статусах.

## Текущий статус

В текущей версии реализованы:

- backend на FastAPI;
- frontend на React + Vite;
- PostgreSQL как долговременное хранилище базы знаний;
- запуск через Docker Compose;
- сохранение задач после обновления страницы и перезапуска Docker;
- модуль базы знаний с моделями, репозиторием, сервисным слоем и правилами;
- базовые API для задач, событий, расписания и интеграций;
- автоматические тесты правил базы знаний.

## Назначение проекта

Система предназначена для помощи пользователю в структурировании учебных и личных задач.

В рамках 4 семестра проект рассматривается не как завершённый интеллектуальный ассистент, а как основа для него — база знаний, которая хранит и структурирует сведения, необходимые для последующего планирования.

База знаний содержит:

- задачи пользователя;
- события и занятые временные интервалы;
- зависимости между задачами;
- дедлайны;
- приоритеты;
- статусы выполнения;
- источники событий.

## Почему это база знаний

Проект хранит не только отдельные записи, но и структурированные знания предметной области.

Основные сущности:

| Сущность | Назначение |
|---|---|
| `Task` | задача пользователя |
| `Event` | событие или занятый временной интервал |
| `TaskDependency` | отношение зависимости между задачами |

Основные отношения:

| Отношение | Смысл |
|---|---|
| `Task has Deadline` | задача имеет срок выполнения |
| `Task has Priority` | задача имеет приоритет |
| `Task has Status` | задача имеет состояние выполнения |
| `Task depends_on Task` | одна задача зависит от другой |
| `Event occupies TimeInterval` | событие занимает временной интервал |
| `Event has Source` | событие имеет источник происхождения |

Правила базы знаний проверяют корректность фактов. Например, событие не может заканчиваться раньше, чем начинается, а задача не может зависеть сама от себя.

## Структура репозитория

```text
AI-assistant/
  apps/
    api/
      app/
        api/                    # API-маршруты FastAPI
        core/                   # настройки приложения
        modules/
          knowledge/            # база знаний
          intelligence/         # планировщик и scoring
          integrations/         # заготовка интеграционного слоя
      tests/                    # тесты backend
    web/
      frontend/                 # React + Vite frontend
  docs/
    knowledge_base.md           # описание базы знаний
    database_schema.md          # схема хранения знаний в PostgreSQL
    testing.md                  # проверка и тестирование проекта
    architecture.md
    team-workflow.md
    git-workflow.md
    roadmap.md
    api-contract.md
    product-vision.md
  packages/
    contracts/
      openapi.yaml
  Makefile
  docker-compose.yml
  .env.example
```

## Модуль базы знаний

Основной модуль для 4 семестра находится здесь:

```text
apps/api/app/modules/knowledge
```

Состав модуля:

| Файл | Назначение |
|---|---|
| `models.py` | Pydantic-модели задач и событий |
| `schema.sql` | PostgreSQL-схема базы знаний |
| `repository.py` | общий интерфейс репозитория |
| `postgres_repository.py` | реализация хранения в PostgreSQL |
| `in_memory_repository.py` | резервное in-memory хранилище |
| `rules.py` | правила базы знаний |
| `service.py` | сервисный слой базы знаний |

Логика обращения:

```text
API → KnowledgeService → Rules → Repository → PostgreSQL
```

## Запуск через Docker

Перейти в корень проекта:

```bash
cd AI-assistant
```

Создать `.env`:

```bash
cp .env.example .env
```

Запустить проект:

```bash
docker compose up -d --build
```

Проверить контейнеры:

```bash
docker compose ps
```

Ожидаемый результат:

```text
api        Up
web        Up
postgres   Up
```

Открыть приложение:

- Frontend: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- Health-check: `http://localhost:8000/health`

Остановить проект:

```bash
docker compose down
```

Не использовать без необходимости:

```bash
docker compose down -v
```

Ключ `-v` удаляет volume PostgreSQL и вместе с ним сохранённые данные.

## Проверка PostgreSQL

Проверить доступность PostgreSQL:

```bash
docker compose exec postgres pg_isready -U assistant -d assistant_db
```

Проверить, что backend использует PostgreSQL:

```bash
docker compose exec api python -c "from app.container import container; print(type(container.knowledge_repository).__name__)"
```

Ожидаемый результат:

```text
PostgresKnowledgeRepository
```

Проверить, что сервис базы знаний подключён:

```bash
docker compose exec api python -c "from app.container import container; print(type(container.knowledge_service).__name__)"
```

Ожидаемый результат:

```text
KnowledgeService
```

## Проверка таблиц базы знаний

Войти в PostgreSQL:

```bash
docker compose exec postgres psql -U assistant -d assistant_db
```

Показать таблицы:

```sql
\dt
```

Ожидаемые таблицы:

```text
events
task_dependencies
tasks
```

Проверить задачи:

```sql
SELECT id, title FROM tasks;
```

Выйти:

```sql
\q
```

## Проверка сохранения данных

1. Открыть сайт: `http://localhost:5173`.
2. Создать задачу.
3. Обновить страницу клавишей F5.
4. Убедиться, что задача осталась.
5. Выполнить:

```bash
docker compose down
docker compose up -d --build
```

6. Снова открыть сайт.
7. Убедиться, что задача сохранилась.

Если задача осталась после перезапуска Docker, значит она хранится в PostgreSQL.

## Проверка правила базы знаний через API

Пример некорректного события:

```bash
curl -X POST http://localhost:8000/v1/events \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Некорректное событие",
    "start_at": "2026-05-05T12:00:00Z",
    "end_at": "2026-05-05T10:00:00Z",
    "source": "manual"
  }'
```

Ожидаемый ответ:

```json
{
  "detail": "Event end_at must be later than start_at."
}
```

Это показывает, что система отклоняет факт, нарушающий правила базы знаний.

## Тестирование

Автоматические тесты правил базы знаний находятся здесь:

```text
apps/api/tests/knowledge/test_rules.py
```

Если `pytest` не установлен внутри контейнера, временно установить его можно так:

```bash
docker compose exec api pip install pytest
```

Запуск тестов:

```bash
docker compose exec api python -m pytest tests/knowledge/test_rules.py -v
```

Ожидаемый результат:

```text
9 passed
```

## Документация

Основные документы:

| Документ | Назначение |
|---|---|
| `docs/knowledge_base.md` | описание базы знаний, сущностей, отношений и правил |
| `docs/database_schema.md` | описание PostgreSQL-схемы |
| `docs/testing.md` | инструкция по проверке и тестированию |
| `docs/architecture.md` | архитектура проекта |
| `docs/team-workflow.md` | распределение ролей |
| `docs/git-workflow.md` | правила работы с Git |
| `docs/roadmap.md` | план развития |
| `docs/api-contract.md` | API-контракты |

## Командная работа

Роли в проекте:

- база знаний: `apps/api/app/modules/knowledge`;
- интеллект ассистента: `apps/api/app/modules/intelligence`;
- интеграции: `apps/api/app/modules/integrations`;
- веб-интерфейс: `apps/web/frontend`.

Работа ведётся через ветки Git. Основная рабочая ветка для доработок:

```text
dev_true
```

После проверки изменения могут быть перенесены в:

```text
release
```

## Текущее ограничение

Текущая версия проекта является MVP базы знаний. Она не заявляется как полноценный интеллектуальный решатель задач.

Сложное автоматическое планирование, интеграции с реальными внешними сервисами и расширенный пользовательский интерфейс относятся к следующим этапам развития проекта.
....