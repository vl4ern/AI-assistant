# Web Module

Веб-модуль находится в `apps/web/frontend`.

## Что где

- `frontend/` — основное приложение React + Vite (активная версия).
- `study/`, `images/` — вспомогательные материалы/прототипы.

## Быстрый запуск

Из корня репозитория:

```bash
make web-install
make web-dev
```

Или вручную:

```bash
cd apps/web/frontend
npm ci
npm run dev -- --host 0.0.0.0 --port 5173
```

Открыть: `http://localhost:5173`

## Линтер

```bash
make web-lint
```

## Переменные окружения

- `VITE_API_URL` — адрес backend API (по умолчанию `http://localhost:8000`).
