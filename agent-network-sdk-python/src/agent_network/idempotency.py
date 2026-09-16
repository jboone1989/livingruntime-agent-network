from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class IdempotencyStore:
    def __init__(self, path: Path | None = None, ttl_seconds: float = 86400.0) -> None:
        self._values: dict[str, Any] = {}
        self._senders: dict[str, Any] = {}
        self._expires: dict[str, float] = {}
        self.ttl_seconds = ttl_seconds
        self.path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS idempotency (k TEXT PRIMARY KEY, value_json TEXT NOT NULL, expires_at REAL NOT NULL)"
                )

    def _connect(self) -> sqlite3.Connection:
        assert self.path is not None
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _purge(self) -> None:
        now = time.time()
        dead = [k for k, exp in self._expires.items() if exp <= now]
        for key in dead:
            self._values.pop(key, None)
            self._senders.pop(key, None)
            self._expires.pop(key, None)
        if self.path is not None:
            with self._connect() as conn:
                conn.execute("DELETE FROM idempotency WHERE expires_at <= ?", (now,))

    def get(self, key: str) -> Any | None:
        self._purge()
        if key in self._values:
            return self._values[key]
        if self.path is None:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT value_json, expires_at FROM idempotency WHERE k=?", (key,)).fetchone()
        if row is None or row["expires_at"] <= time.time():
            return None
        value = json.loads(row["value_json"])
        self._values[key] = value
        return value

    def put(self, key: str, value: Any) -> None:
        expires = time.time() + self.ttl_seconds
        self._values[key] = value
        self._expires[key] = expires
        if self.path is not None:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO idempotency(k, value_json, expires_at) VALUES (?,?,?) ON CONFLICT(k) DO UPDATE SET value_json=excluded.value_json, expires_at=excluded.expires_at",
                    (key, json.dumps(value, ensure_ascii=False), expires),
                )

    def get_message(self, sender_agent_id: str, message_id: str) -> Any | None:
        return self.get(f"msg:{sender_agent_id}:{message_id}")

    def put_message(self, sender_agent_id: str, message_id: str, value: Any) -> None:
        self.put(f"msg:{sender_agent_id}:{message_id}", value)

    def run(self, key: str, fn: Callable[[], T]) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = fn()
        self.put(key, value)
        return value

    def seen_message(self, sender_agent_id: str, message_id: str, ttl_holder: Any = None) -> bool:
        return self.get_message(sender_agent_id, message_id) is not None
