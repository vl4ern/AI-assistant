import json
import uuid
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional

from integration.sync_scheduler import SyncScheduler
from models.task import Task, TaskStatus, SourceType, utc_now


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Парсит ISO-дату, приводит к aware UTC. Бросает ValueError при ошибке."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Некорректная дата: {value!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class SyncAPIHandler(BaseHTTPRequestHandler):
    """HTTP-обработчик для управления синхронизацией и задачами."""

    scheduler: SyncScheduler = None  # устанавливается в start_api_server

    # ------------------------------------------------------------------ CORS

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization"
        )

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ------------------------------------------------------------------ helpers

    def _json(self, code: int, payload):
        body = json.dumps(
            payload, ensure_ascii=False, indent=2, default=str
        ).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            raise ValueError("Пустое тело запроса")
        raw = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Некорректный JSON: {e}")
        if not isinstance(data, dict):
            raise ValueError("Тело запроса должно быть JSON-объектом")
        return data

    def _task_to_dict(self, task: Task) -> dict:
        return {
            "id": task.id,
            "external_id": task.external_id,
            "source_type": task.source_type.value,
            "title": task.title,
            "description": task.description,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "duration_minutes": task.duration_minutes,
            "priority": task.priority,
            "status": task.status.value,
            "project_id": task.project_id,
            "labels": task.labels,
            "version": task.version,
            "last_modified": task.last_modified.isoformat(),
        }

    # ------------------------------------------------------------------ GET

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)

        try:
            if path == "/status":
                return self._get_status()
            if path == "/sync/now":
                return self._force_sync()
            if path == "/config":
                return self._get_config()
            if path == "/tasks":
                return self._get_tasks(params)
            if path == "/tasks/upcoming":  # ВАЖНО: до startswith("/tasks/")
                return self._get_upcoming(params)
            if path.startswith("/tasks/"):
                return self._get_task(path[len("/tasks/"):])
            return self._json(404, {"error": "Not found", "path": path})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def _get_status(self):
        adapters = {}
        for name in self.scheduler.adapters:
            last = self.scheduler.last_sync_time.get(name)
            adapters[name] = {
                "last_sync": last.isoformat() if last else None,
                "interval": self.scheduler.intervals.get(name, 0),
            }
        self._json(200, {
            "running": self.scheduler._running,
            "adapters": adapters,
        })
    
    def _get_config(self):
        iis = self.scheduler.adapters.get(SourceType.IIS.value)
        self._json(200, {
            "iis_group": iis.group_number if iis else None,
            "adapters": list(self.scheduler.adapters.keys()),
            "intervals": dict(self.scheduler.intervals),
        })

    def _force_sync(self):
        result = self.scheduler.sync_all()
        self._json(200, {
            "success": result.success,
            "tasks_synced": result.tasks_synced,
            "conflicts_detected": result.conflicts_detected,
            "errors": result.errors,
        })

    def _get_tasks(self, params):
        source = params.get("source", [None])[0]
        status = params.get("status", [None])[0]
        tasks = self.scheduler.cache.get_all_tasks()
        if source:
            tasks = [t for t in tasks if t.source_type.value == source]
        if status:
            tasks = [t for t in tasks if t.status.value == status]
        tasks.sort(key=lambda t: (t.due_date is None, t.due_date or utc_now()))
        self._json(200, {
            "count": len(tasks),
            "tasks": [self._task_to_dict(t) for t in tasks],
        })

    def _get_task(self, task_id: str):
        task = self.scheduler.cache.get_task(task_id)
        if not task:
            return self._json(404, {"error": "Task not found"})
        self._json(200, self._task_to_dict(task))

    def _get_upcoming(self, params):
        try:
            days = int(params.get("days", [3])[0])
        except (ValueError, TypeError):
            return self._json(400, {"error": "Параметр days должен быть числом"})
        now = utc_now()
        horizon = now + timedelta(days=days)
        tasks = [
            t for t in self.scheduler.cache.get_all_tasks()
            if t.due_date and now <= t.due_date <= horizon
            and t.status != TaskStatus.ARCHIVED
        ]
        tasks.sort(key=lambda t: t.due_date)
        self._json(200, {
            "count": len(tasks),
            "tasks": [self._task_to_dict(t) for t in tasks],
        })

    # ------------------------------------------------------------------ POST

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/config/iis_group":
                return self._set_iis_group()
            if path == "/tasks":
                return self._create_task()
            return self._json(404, {"error": "Not found", "path": path})
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:
            return self._json(500, {"error": str(e)})
        
    def _set_iis_group(self):
        try:
            data = self._read_json()
        except ValueError as e:
            return self._json(400, {"error": str(e)})

        group = data.get("group")
        if not group:
            return self._json(400, {"error": "Поле 'group' обязательно"})

        adapter = self.scheduler.adapters.get(SourceType.IIS.value)
        if adapter is None:
            return self._json(503, {"error": "Адаптер IIS не зарегистрирован"})

        try:
            changed = adapter.set_group_number(str(group))
        except ValueError as e:
            return self._json(400, {"error": str(e)})

        if not changed:
            return self._json(200, {"changed": False, "group": group})

        self.scheduler.last_sync_time[SourceType.IIS.value] = None
        import threading
        threading.Thread(
            target=self.scheduler.sync_adapter_now,
            args=(SourceType.IIS.value,),
            daemon=True,
        ).start()

        self._json(200, {"changed": True, "group": group, "sync_started": True})

    def _create_task(self):
        data = self._read_json()
        task = self._task_from_payload(data, task_id=None)
        if not self.scheduler.cache.save_task(task):
            return self._json(500, {"error": "Не удалось сохранить задачу"})

        # Отправка во внешний сервис, если он есть для этого source_type.
        # Адаптер может обновить task.external_id — тогда пересохраняем.
        if self._push_to_adapter(task):
            self.scheduler.cache.save_task(task)

        self._json(201, self._task_to_dict(task))

    def _task_from_payload(self, data: dict, task_id: Optional[str]) -> Task:
        if not data.get("title"):
            raise ValueError("Поле 'title' обязательно")

        source_raw = data.get("source_type", "manual")
        try:
            source = SourceType(source_raw)
        except ValueError:
            raise ValueError(f"Недопустимый source_type: {source_raw!r}")

        status_raw = data.get("status", "pending")
        try:
            status = TaskStatus(status_raw)
        except ValueError:
            raise ValueError(f"Недопустимый status: {status_raw!r}")

        try:
            due_date = _parse_iso_datetime(data.get("due_date"))
        except ValueError as e:
            raise ValueError(str(e))

        return Task(
            id=task_id or data.get("id") or str(uuid.uuid4()),
            external_id=data.get("external_id", ""),
            source_type=source,
            title=data["title"],
            description=data.get("description", ""),
            due_date=due_date,
            duration_minutes=int(data.get("duration_minutes", 30)),
            priority=int(data.get("priority", 3)),
            status=status,
            project_id=data.get("project_id", ""),
            labels=list(data.get("labels") or []),
            last_modified=utc_now(),
            version=int(data.get("version", 1)),
        )

    # ------------------------------------------------------------------ PUT

    def do_PUT(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path.startswith("/tasks/"):
                task_id = path[len("/tasks/"):]
                return self._update_task(task_id)
            return self._json(404, {"error": "Not found", "path": path})
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def _update_task(self, task_id: str):
        existing = self.scheduler.cache.get_task(task_id)
        if not existing:
            return self._json(404, {"error": "Task not found"})

        data = self._read_json()

        # Патч: изменяем только те поля, что пришли в body.
        if "title" in data:
            existing.title = data["title"]
        if "description" in data:
            existing.description = data["description"]
        if "due_date" in data:
            existing.due_date = _parse_iso_datetime(data["due_date"])
        if "duration_minutes" in data:
            existing.duration_minutes = int(data["duration_minutes"])
        if "priority" in data:
            existing.priority = int(data["priority"])
        if "status" in data:
            existing.status = TaskStatus(data["status"])
        if "project_id" in data:
            existing.project_id = data["project_id"]
        if "labels" in data:
            existing.labels = list(data["labels"] or [])

        existing.last_modified = utc_now()
        existing.version += 1

        if not self.scheduler.cache.save_task(existing):
            return self._json(500, {"error": "Не удалось сохранить задачу"})

        if self._push_to_adapter(existing):
            self.scheduler.cache.save_task(existing)

        self._json(200, self._task_to_dict(existing))

    # ------------------------------------------------------------------ DELETE

    def do_DELETE(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path.startswith("/tasks/"):
                task_id = path[len("/tasks/"):]
                return self._delete_task(task_id)
            return self._json(404, {"error": "Not found", "path": path})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def _delete_task(self, task_id: str):
        task = self.scheduler.cache.get_task(task_id)
        if not task:
            return self._json(404, {"error": "Task not found"})

        # Пробуем удалить во внешнем сервисе, если он это поддерживает.
        adapter = self.scheduler.adapters.get(task.source_type.value)
        if adapter and task.external_id:
            try:
                adapter.delete_task(task.external_id)
            except NotImplementedError:
                pass  # например, IIS — только чтение
            except Exception as e:
                print(f"[API] Ошибка удаления во внешнем сервисе: {e}")

        self.scheduler.cache.delete_task(task_id)
        self._json(200, {"deleted": task_id})

    # ------------------------------------------------------------------ push

    def _push_to_adapter(self, task: Task) -> bool:
        """
        Отправляет задачу во внешний сервис.
        MANUAL-задачи никуда не отправляются.
        Возвращает True, если был реальный push (и, возможно, изменился external_id).
        """
        if task.source_type == SourceType.MANUAL:
            return False
        adapter = self.scheduler.adapters.get(task.source_type.value)
        if not adapter:
            return False
        try:
            return bool(adapter.push_update(task))
        except NotImplementedError:
            return False
        except Exception as e:
            print(f"[API] Ошибка push в {task.source_type.value}: {e}")
            return False

    # ------------------------------------------------------------------ logging

    def log_message(self, format, *args):
        print(f"[API] {self.address_string()} - {format % args}")


def start_api_server(scheduler: SyncScheduler, port: int = 8090):
    """Запуск HTTP-сервера для внешнего управления."""
    SyncAPIHandler.scheduler = scheduler
    server = ThreadingHTTPServer(("localhost", port), SyncAPIHandler)
    print(f"[API] HTTP-сервер запущен на порту {port}")
    print(f"[API] Статус: http://localhost:{port}/status")
    print(f"[API] Принудительная синхронизация: http://localhost:{port}/sync/now")
    print(f"[API] Список задач: http://localhost:{port}/tasks")
    print(f"[API] Ближайшие: http://localhost:{port}/tasks/upcoming?days=7")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()