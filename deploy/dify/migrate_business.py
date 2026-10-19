"""One-time SQLite backup from a stopped legacy bind mount to a Docker volume.

Run inside a temporary application container: mount the legacy directory at
/legacy and the new business volume at /data. Refuses to overwrite any database.
Never open a live Linux-container WAL database with a Windows SQLite process.
"""
import sqlite3
from pathlib import Path

source = Path("/legacy/local-logisupply.db")
target = Path("/data/local-logisupply.db")
if not source.is_file() or target.exists():
    raise RuntimeError("Expected an existing legacy database and an empty target")
with sqlite3.connect(source) as old, sqlite3.connect(target) as new:
    old.backup(new)
    assert new.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    for table in ("tickets", "ticket_events", "proposals", "web_sessions", "web_conversations", "web_messages"):
        assert old.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == new.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    counts = [new.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("tickets", "ticket_events")]
print(f"Preserved {counts[0]} synthetic tickets and {counts[1]} events in the local Docker volume.")
