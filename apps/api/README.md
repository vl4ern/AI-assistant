# API service

Backend часть проекта на FastAPI.

## Запуск локально

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --app-dir . --reload --host 0.0.0.0 --port 8000
```

Документация API: `http://localhost:8000/docs`

## Тесты

```bash
PYTHONPATH=. pytest tests -q
```
