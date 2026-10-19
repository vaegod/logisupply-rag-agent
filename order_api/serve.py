"""Production entry point: validate secrets, initialize durable storage, honor PORT."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from .database import Database
from .main import create_app


@dataclass(frozen=True)
class Settings:
    port: int
    database: Path
    tool_key: str
    admin_key: str


def load_settings() -> Settings:
    try:
        port = int(os.getenv("PORT", "8018"))
    except ValueError as exc:
        raise ValueError("PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    keys = [os.getenv(name, "") for name in ("LOGISUPPLY_TOOL_API_KEY", "LOGISUPPLY_ADMIN_API_KEY")]
    if any(len(key) < 24 or not key.isascii() or key.startswith("replace-") for key in keys):
        raise ValueError("Set distinct random tool/operator keys of at least 24 ASCII characters")
    if keys[0] == keys[1]:
        raise ValueError("Tool and operator keys must be different")
    mount = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if os.getenv("RAILWAY_ENVIRONMENT_ID") and not mount:
        raise ValueError("Attach a persistent volume before starting the Railway service")
    path = os.getenv("LOGISUPPLY_DB_PATH")
    if not path:
        if not mount:
            raise ValueError("LOGISUPPLY_DB_PATH must point to durable storage")
        path = str(Path(mount) / "logisupply.db")
    database = Path(path)
    if not database.is_absolute():
        raise ValueError("LOGISUPPLY_DB_PATH must be absolute")
    if mount and not database.resolve().is_relative_to(Path(mount).resolve()):
        raise ValueError("SQLite database must be inside the mounted persistent volume")
    return Settings(port, database, *keys)


def build_application(settings: Settings):
    # A deployment must not pass its healthcheck before the database is writable.
    Database(settings.database).initialize()
    return create_app(settings.database, tool_key=settings.tool_key, admin_key=settings.admin_key)


def main():
    settings = load_settings()
    uvicorn.run(build_application(settings), host="0.0.0.0", port=settings.port, workers=1)


if __name__ == "__main__":
    main()
