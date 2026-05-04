# API service

Backend часть проекта на FastAPI.

## Запуск локально

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_assistant"
uvicorn app.main:app --app-dir . --reload --host 0.0.0.0 --port 8000
```

Документация API: `http://localhost:8000/docs`

## PostgreSQL

- Хранилище `knowledge` работает через PostgreSQL (`psycopg`).
- При старте `PostgresKnowledgeRepository` автоматически применяет `app/modules/knowledge/schema.sql`.
- Автоинициализацию можно отключить: `POSTGRES_AUTO_INIT_SCHEMA=false`.
- Для ручного применения схемы используйте:

```bash
psql "$DATABASE_URL" -f app/modules/knowledge/migrations/0001_init_knowledge.sql
```

## Тесты

```bash
PYTHONPATH=. pytest tests -q
```
