from fastapi.testclient import TestClient

from order_api.main import app


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "logisupply-order-api",
    }


def test_query_order_by_path_is_case_insensitive() -> None:
    response = client.get("/orders/jd2026001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is True
    assert payload["order"]["order_id"] == "JD2026001"
    assert payload["order"]["status"] == "运输中"


def test_query_order_by_query_parameter() -> None:
    response = client.get("/orders", params={"order_id": "JD2026002"})

    assert response.status_code == 200
    assert response.json()["order"]["current_node"] == "华北干线运输节点"


def test_query_order_by_post() -> None:
    response = client.post("/orders/query", json={"order_id": "JD2026003"})

    assert response.status_code == 200
    assert response.json()["order"]["exception_type"] == "温度异常报警"


def test_missing_order_returns_structured_404() -> None:
    response = client.post("/orders/query", json={"order_id": "JD9999999"})

    assert response.status_code == 404
    assert response.json()["detail"]["found"] is False
    assert "JD9999999" in response.json()["detail"]["message"]


def test_normal_order_has_low_risk() -> None:
    response = client.post(
        "/orders/analyze",
        json={"order_id": "JD2026001", "user_problem": "订单是否正常？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "低"
    assert payload["user_problem"] == "订单是否正常？"


def test_delayed_order_has_medium_risk() -> None:
    response = client.post(
        "/orders/analyze",
        json={"order_id": "JD2026002", "user_problem": "延迟了怎么处理？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "中"
    assert "主动通知客户" in payload["suggestion"]


def test_temperature_alarm_has_high_risk() -> None:
    response = client.post(
        "/orders/analyze",
        json={"order_id": "JD2026003", "user_problem": "温度报警怎么办？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "高"
    assert "温控记录" in payload["suggestion"]


def test_damaged_order_has_high_risk() -> None:
    response = client.post(
        "/orders/analyze",
        json={"order_id": "JD2026004", "user_problem": "包装破损怎么办？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "高"
    assert "破损照片" in payload["suggestion"]


def test_analyze_missing_order_returns_404() -> None:
    response = client.post(
        "/orders/analyze",
        json={"order_id": "JD9999999", "user_problem": "怎么处理？"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["found"] is False
