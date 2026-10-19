"""SQLite persistence for the demo order service and ticket lifecycle."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing, contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._ready = False
        self._lock = threading.Lock()

    def initialize(self) -> None:
        with self._lock:
            if self._ready:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=15)) as conn, conn:
                conn.execute("PRAGMA journal_mode=WAL")
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version > 1:
                    raise RuntimeError("Database schema is newer than this application")
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS tracking (
                        order_id TEXT NOT NULL REFERENCES orders(order_id),
                        occurred_at TEXT NOT NULL, node TEXT NOT NULL,
                        description TEXT NOT NULL,
                        PRIMARY KEY(order_id, occurred_at));
                    CREATE TABLE IF NOT EXISTS proposals (
                        proposal_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                        order_id TEXT NOT NULL REFERENCES orders(order_id),
                        summary TEXT NOT NULL, created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS tickets (
                        ticket_id TEXT PRIMARY KEY,
                        proposal_id TEXT NOT NULL UNIQUE REFERENCES proposals(proposal_id),
                        user_id TEXT NOT NULL,
                        order_id TEXT NOT NULL REFERENCES orders(order_id),
                        summary TEXT NOT NULL, status TEXT NOT NULL
                          CHECK(status IN ('open','processing','resolved','closed')),
                        resolution TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                    CREATE UNIQUE INDEX IF NOT EXISTS one_active_ticket
                        ON tickets(user_id, order_id) WHERE status != 'closed';
                    CREATE TABLE IF NOT EXISTS ticket_events (
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id),
                        from_status TEXT, to_status TEXT NOT NULL,
                        note TEXT NOT NULL, actor TEXT NOT NULL, occurred_at TEXT NOT NULL);
                    PRAGMA user_version=1;
                """)
                root = Path(__file__).parent
                orders = json.loads((root / "orders.json").read_text(encoding="utf-8"))
                for order in orders:
                    conn.execute("INSERT OR IGNORE INTO orders VALUES (?,?)",
                                 (order["order_id"], json.dumps(order, ensure_ascii=False)))
                    # Seed only the known archived snapshot; do not invent carrier events.
                    conn.execute("INSERT OR IGNORE INTO tracking VALUES (?,?,?,?)",
                                 (order["order_id"], order["last_update"],
                                  order["current_node"],
                                  f"演示快照：{order['status']}；{order['exception_type']}"))
            self._ready = True

    @contextmanager
    def connect(self, *, write: bool = False):
        self.initialize()
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def find_order(self, order_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT payload FROM orders WHERE order_id=?",
                               (order_id.strip().upper(),)).fetchone()
        return json.loads(row["payload"]) if row else None

    def load_orders(self) -> list[dict]:
        with self.connect() as conn:
            return [json.loads(row["payload"]) for row in
                    conn.execute("SELECT payload FROM orders ORDER BY order_id")]
