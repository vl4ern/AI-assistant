import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from integration.sync_scheduler import SyncScheduler


class SyncAPIHandler(BaseHTTPRequestHandler):
    """Простой HTTP-обработчик для управления синхронизацией"""

    scheduler: SyncScheduler = None  # Будет установлен извне

    def do_GET(self):
        if self.path == "/status":
            self._handle_status()
        elif self.path == "/sync/now":
            self._handle_force_sync()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

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
