import pytest

from order_api import main
from order_api.database import Database


@pytest.fixture(autouse=True)
def isolate_legacy_database(tmp_path, monkeypatch):
    """Legacy API and offline-baseline tests must never modify the user's DB."""
    monkeypatch.setattr(main, "default_db", Database(tmp_path / "legacy.db"))
