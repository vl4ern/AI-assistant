import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from integration.sync_scheduler import SyncScheduler
from urllib.parse import urlparse, parse_qs
from models.task import TaskStatus, SourceType
from datetime import datetime, timedelta


class SyncAPIHandler(BaseHTTPRequestHandler):
    """Простой HTTP-обработчик для управления синхронизацией"""

    scheduler: SyncScheduler = None  # Будет установлен извне

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/status":
            self._handle_status()
        elif parsed.path == "/sync/now":
            self._handle_force_sync()
        elif parsed.path == "/tasks":
            self._handle_get_tasks(params)
        elif parsed.path.startswith("/tasks/"):
            task_id = parsed.path.split("/")[-1]
            self._handle_get_task(task_id)
        elif parsed.path == "/tasks/upcoming":
            self._handle_upcoming_tasks(params)
        else:
            self._send_response(404, {"error": "Not found"})

    def _handle_status(self):
        """Возвращает статус синхронизации"""
        status = {"adapters": {}, "running": self.scheduler._running}

        for name in self.scheduler.adapters:
            last_sync = self.scheduler.last_sync_time.get(name)
            status["adapters"][name] = {
                "last_sync": last_sync.isoformat() if last_sync else None,
                "interval": self.scheduler.intervals.get(name, 0),
            }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(status, ensure_ascii=False, indent=2).encode())

    def _handle_get_tasks(self, params):
        source_filter = params.get("source", [None])[0]
        tasks = (
            self.scheduler.cache.get_all_tasks()
        )  # нужно добавить метод в ICacheStorage

        if source_filter:
            tasks = [t for t in tasks if t.source_type.value == source_filter]

        self._send_response(
            200, {"count": len(tasks), "tasks": [self._task_to_dict(t) for t in tasks]}
        )

    def _handle_get_task(self, task_id):
        task = self.scheduler.cache.get_task(task_id)
        if task:
            self._send_response(200, self._task_to_dict(task))
        else:
            self._send_response(404, {"error": "Task not found"})

    def _handle_upcoming_tasks(self, params):
        days = int(params.get("days", [3])[0])
        now = datetime.now()
        upcoming_date = now + timedelta(days=days)

        tasks = self.scheduler.cache.get_all_tasks()
        upcoming = [
            t
            for t in tasks
            if t.due_date
            and now <= t.due_date <= upcoming_date
            and t.status != TaskStatus.ARCHIVED
        ]
        upcoming.sort(key=lambda x: x.due_date)

        self._send_response(
            200,
            {
                "count": len(upcoming),
                "tasks": [self._task_to_dict(t) for t in upcoming],
            },
        )

    def do_POST(self):
        if self.path == "/tasks":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode()
            data = json.loads(body)
            task = self._create_manual_task(data)
            self.scheduler.cache.save_task(task)
            self._send_response(201, self._task_to_dict(task))

    def _handle_force_sync(self):
        """Принудительный запуск синхронизации"""
        result = self.scheduler.sync_all()
        response = {
            "success": result.success,
            "tasks_synced": result.tasks_synced,
            "errors": result.errors,
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response, ensure_ascii=False, indent=2).encode())

    def _task_to_dict(self, task):
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
        }

    def _send_response(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode())

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/tasks/"):
            task_id = parsed.path.split("/")[-1]
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode()
            data = json.loads(body)
            existing = self.scheduler.cache.get_task(task_id)
            if existing:
                updated = self._update_task(existing, data)
                self.scheduler.cache.save_task(updated)
                self._send_response(200, self._task_to_dict(updated))
            else:
                self._send_response(404, {"error": "Task not found"})

    def log_message(self, format, *args):
        # Подавляем стандартные логи HTTP
        pass


def start_api_server(scheduler: SyncScheduler, port: int = 8090):
    """Запуск HTTP-сервера для внешнего управления"""
    SyncAPIHandler.scheduler = scheduler
    server = HTTPServer(("localhost", port), SyncAPIHandler)
    print(f"[API] HTTP-сервер запущен на порту {port}")
    print(f"[API] Статус: http://localhost:{port}/status")
    print(f"[API] Принудительная синхронизация: http://localhost:{port}/sync/now")
    server.serve_forever()
