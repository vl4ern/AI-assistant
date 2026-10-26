import json
import os
import threading
from pathlib import Path


class ConfigStore:
    """Простое JSON-хранилище настроек с потокобезопасной записью."""

    def __init__(self, path: str = "config.json"):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Config] Не удалось прочитать {self.path}: {e}. Начинаю с пустого.")
            return {}

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value
            self._save_locked()

    def _save_locked(self):
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, self.path)
