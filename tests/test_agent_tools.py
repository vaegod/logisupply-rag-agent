from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from order_api.database import Database
from order_api.main import create_app

CONTEXT = {"user_id": "demo-user", "conversation_id": "conversation-1"}
HEADERS = {"X-API-Key": "test-tool"}
ADMIN = {"X-Admin-Key": "test-admin"}


@pytest.fixture
def service(tmp_path):
    path = tmp_path / "service.db"
    return TestClient(create_app(path, tool_key="test-tool", admin_key="test-admin")), path


def post(client, name, body):
    return client.post("/tools/" + name, json=body, headers=HEADERS)


def prepare(client, **updates):
    body = {**CONTEXT, "order_id": "jd2026002", "summary": "干线延迟，请运营核实节点并联系客户", **updates}
    response = post(client, "prepare_ticket", body)
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, draft, **updates):
    return post(client, "create_ticket", {**CONTEXT, "proposal_id": draft["proposal_id"],
                "user_message": draft["confirmation_phrase"], **updates})


def test_tools_require_service_key_and_default_fail_closed(tmp_path):
    client = TestClient(create_app(tmp_path / "disabled.db"))
    assert client.post("/tools/query_order", json={"order_id": "JD2026001"}).status_code == 503
    client = TestClient(create_app(tmp_path / "key.db", tool_key="secret"))
    assert client.post("/tools/query_order", json={"order_id": "JD2026001"}).status_code == 401
    with pytest.raises(ValueError):
        create_app(tmp_path / "same.db", tool_key="same", admin_key="same")


def test_sqlite_order_and_tracking_are_archived_snapshots(service):
    client, path = service
    order = post(client, "query_order", {"order_id": "jd2026002"}).json()
    assert order["order"]["exception_type"] == "干线运输延迟"
    tracking = post(client, "query_tracking", {"order_id": "JD2026002"}).json()
    assert tracking["data_source"] == "demo_snapshot"
    assert tracking["events"][0]["node"] == order["order"]["current_node"]
    with Database(path).connect(write=True) as conn:
        conn.execute("UPDATE orders SET payload=json_set(payload,'$.status','数据库已更新') WHERE order_id='JD2026002'")
    assert post(client, "query_order", {"order_id": "JD2026002"}).json()["order"]["status"] == "数据库已更新"
    assert post(client, "query_tracking", {"order_id": "JD9999999"}).status_code == 404


def test_sop_returns_citable_evidence_and_empty_unknown(service):
    client, _ = service
    result = post(client, "search_sop", {"query": "冷链温度报警怎么办"}).json()
    assert result["retrieval_method"] == "chunk_bm25"
    assert result["results"][0]["source"] == "03_冷链运输规范.md"
    assert "content" in result["results"][0]
    assert post(client, "search_sop", {"query": "zzzxxyy"}).json()["results"] == []
    assert post(client, "search_sop", {"query": "冷链", "top_k": 99}).status_code == 422


def test_confirmation_cannot_be_replaced_by_boolean_or_other_user(service):
    client, path = service
    draft = prepare(client)
    assert confirm(client, draft, user_message="需要的话帮我建工单").status_code == 409
    assert confirm(client, draft, user_message="确认创建工单 P-wrong").status_code == 409
    assert confirm(client, draft, user_id="other-user").status_code == 404
    assert confirm(client, draft, conversation_id="other-chat").status_code == 404
    assert confirm(client, draft, confirmed=True).status_code == 422
    with Database(path).connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0


def test_ticket_full_lifecycle_is_persistent_and_operator_only(service):
    client, path = service
    draft = prepare(client)
    created = confirm(client, draft).json()
    assert created["created"] is True
    ticket_id = created["ticket"]["ticket_id"]
    assert confirm(client, draft).json()["created"] is False
    route = f"/admin/tickets/{ticket_id}/status"
    body = {"expected_status": "open", "status": "processing", "note": "运营人员开始核实延迟节点"}
    assert client.patch(route, json=body, headers=HEADERS).status_code == 401
    assert client.patch(route, json={**body, "status": "closed"}, headers=ADMIN).status_code == 409
    assert client.patch(route, json=body, headers=ADMIN).status_code == 200
    assert client.patch(route, json=body, headers=ADMIN).status_code == 409
    for previous, status, note in [("processing", "resolved", "已核实并通知客户更新送达时间"),
                                   ("resolved", "closed", "客户确认已收到处理结果，关闭工单")]:
        assert client.patch(route, json={"expected_status": previous, "status": status, "note": note}, headers=ADMIN).status_code == 200
    restarted = TestClient(create_app(path, tool_key="test-tool", admin_key="test-admin"))
    ticket = post(restarted, "query_ticket", {"user_id": CONTEXT["user_id"], "ticket_id": ticket_id}).json()["tickets"][0]
    assert ticket["status"] == "closed"
    assert "已核实" in ticket["resolution"]
    assert [event["to_status"] for event in ticket["events"]] == ["open", "processing", "resolved", "closed"]
    assert post(client, "query_ticket", {"user_id": "other-user", "ticket_id": ticket_id}).status_code == 404
    assert post(client, "query_ticket", {"user_id": CONTEXT["user_id"]}).status_code == 422
    new_draft = prepare(restarted)
    assert new_draft["proposal_id"] != draft["proposal_id"]
    assert confirm(restarted, new_draft).json()["created"] is True


def test_service_factory_uses_environment_keys(service, monkeypatch):
    _, path = service
    monkeypatch.setenv("LOGISUPPLY_TOOL_API_KEY", "factory-tool")
    monkeypatch.setenv("LOGISUPPLY_ADMIN_API_KEY", "factory-admin")
    client = TestClient(create_app(path))
    assert client.post("/tools/query_order", json={"order_id": "JD2026001"}, headers={"X-API-Key": "factory-tool"}).status_code == 200


def test_concurrent_confirmation_and_different_drafts_do_not_duplicate(service):
    client, path = service
    draft = prepare(client)
    second = prepare(client, summary="另一份同一订单的延迟处理草稿")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: confirm(client, draft), range(4)))
    assert all(result.status_code == 200 for result in results)
    assert sum(result.json()["created"] for result in results) == 1
    assert confirm(client, second).json()["created"] is False
    assert "existing_ticket" in prepare(client)
    with Database(path).connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ticket_events").fetchone()[0] == 1


def test_expired_proposal_and_unknown_order(service):
    client, path = service
    assert post(client, "prepare_ticket", {**CONTEXT, "order_id": "JD9999999", "summary": "不存在订单的异常处理"}).status_code == 404
    draft = prepare(client)
    with Database(path).connect(write=True) as conn:
        conn.execute("UPDATE proposals SET expires_at='2000-01-01T00:00:00+00:00'")
    assert confirm(client, draft).json()["detail"]["error"] == "proposal_expired"


def test_agent_openapi_excludes_operator_and_credentials(service):
    client, _ = service
    spec = client.get("/agent-openapi.json").json()
    assert spec["openapi"] == "3.0.3"
    assert len(spec["paths"]) == 6
    assert all(path.startswith("/tools/") for path in spec["paths"])
    assert "test-tool" not in str(spec)
    assert "$ref" not in str(spec)
    assert "X-Admin-Key" not in str(spec)
    for path in spec["paths"].values():
        assert path["post"]["security"] == [{"ToolKey": []}]
