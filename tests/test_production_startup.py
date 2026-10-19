import pytest
from fastapi.testclient import TestClient

from order_api.serve import build_application, load_settings


@pytest.fixture
def environment(monkeypatch, tmp_path):
    for name in ("LOGISUPPLY_DB_PATH", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_VOLUME_MOUNT_PATH", "PORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOGISUPPLY_TOOL_API_KEY", "tool-" + "x" * 32)
    monkeypatch.setenv("LOGISUPPLY_ADMIN_API_KEY", "operator-" + "y" * 32)
    monkeypatch.setenv("LOGISUPPLY_DB_PATH", str(tmp_path / "data" / "service.db"))
    return monkeypatch, tmp_path


def test_production_startup_initializes_database_and_uses_port(environment):
    monkeypatch, _ = environment
    monkeypatch.setenv("PORT", "9123")
    settings = load_settings()
    assert settings.port == 9123
    app = build_application(settings)
    assert settings.database.is_file()
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.post("/tools/query_order", json={"order_id": "JD2026002"},
                       headers={"X-API-Key": settings.tool_key}).status_code == 200
    assert client.get("/orders/JD2026002").status_code == 404


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_bad_port_prevents_startup(environment, port):
    monkeypatch, _ = environment
    monkeypatch.setenv("PORT", port)
    with pytest.raises(ValueError, match="PORT"):
        load_settings()


def test_missing_or_default_key_prevents_startup(environment):
    monkeypatch, _ = environment
    for key in ("", "short", "replace-with-random-tool-key"):
        monkeypatch.setenv("LOGISUPPLY_TOOL_API_KEY", key)
        with pytest.raises(ValueError, match="keys"):
            load_settings()


def test_railway_requires_real_volume_and_contained_database(environment):
    monkeypatch, tmp_path = environment
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "deployment-test")
    with pytest.raises(ValueError, match="volume"):
        load_settings()
    mount = tmp_path / "volume"
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(mount))
    with pytest.raises(ValueError, match="inside"):
        load_settings()
    monkeypatch.delenv("LOGISUPPLY_DB_PATH")
    assert load_settings().database == mount / "logisupply.db"
