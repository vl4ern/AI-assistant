# Как запустить исправленный проект

Проект состоит из двух частей:

- `apps/api` — backend на FastAPI;
- `apps/web/frontend` — frontend на React + Vite.

## Вариант 1. Рекомендуемый запуск через Docker

```bash
cd AI-assistant-dev_true
cp .env.example .env
docker compose up --build
```

Открыть в браузере:

- frontend: http://localhost:5173
- API-документация: http://localhost:8000/docs
- health-check API: http://localhost:8000/health

Остановить проект:

```bash
docker compose down
```

Если нужно полностью удалить данные PostgreSQL:

```bash
docker compose down -v
```

## Вариант 2. Локальный запуск без Docker

Требования:

- Python 3.10+
- Node.js 22.x
- npm

Проверить версии:

```bash
python3 --version
node -v
npm -v
```

Если Node.js старый, например `v12`, frontend не запустится. Нужно поставить Node 22 через `nvm`.

### 1. Запуск backend

В первом терминале:

```bash
cd AI-assistant-dev_true
make api-install
make api-dev
```

API будет доступен здесь:

```text
http://localhost:8000/docs
```

### 2. Запуск frontend

Во втором терминале:

```bash
cd AI-assistant-dev_true
make web-install
make web-dev
```

Frontend будет доступен здесь:

```text
http://localhost:5173
```

## Что было исправлено

1. Исправлена ошибка сборки frontend: `initialTasks` был объявлен, но не использовался.
2. Frontend теперь берет адрес API из `VITE_API_URL`, а по умолчанию использует `http://localhost:8000`.
3. В `docker-compose.yml` API теперь получает корректный `DATABASE_URL` для контейнера PostgreSQL.
4. В `docker-compose.yml` frontend использует `http://localhost:8000`, потому что запросы выполняются из браузера пользователя, а не из контейнера.
5. Backend теперь не падает полностью, если PostgreSQL недоступен: используется in-memory хранилище для локальной проверки.
6. Backend получил fallback для скоринга, если `scikit-learn` не установлен. При нормальной установке зависимостей будет использоваться `SGDRegressor`.

## Быстрая проверка

После запуска backend открой:

```text
http://localhost:8000/health
```

Нормальный ответ:

```json
{
  "status": "ok",
  "service": "AI Assistant API",
  "version": "0.1.0"
}
```

После запуска frontend открой:

```text
http://localhost:5173
```

Если страница открылась и задачи отображаются, frontend работает.
