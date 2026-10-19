"""Exercise the running local API; this does NOT evaluate model tool selection."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dify.build_agent import GATE_CODE


def main():
    runtime = json.loads((ROOT / "dify/local/runtime.json").read_text(encoding="utf-8"))
    base = "http://127.0.0.1:" + str(runtime.get("port", 8018))
    def call(path, body, *, admin=False, method="POST"):
        req = request.Request(base + path, data=json.dumps(body).encode(), method=method,
                              headers={"Content-Type": "application/json",
                                       "X-Admin-Key" if admin else "X-API-Key": runtime["admin_key" if admin else "tool_key"]})
        try:
            with request.urlopen(req, timeout=15) as response:
                return response.status, json.load(response)
        except error.HTTPError as exc:
            return exc.code, json.load(exc)

    context = {"user_id": "local-acceptance-demo", "conversation_id": "acceptance-" + datetime.now(timezone.utc).isoformat()}
    checks = []
    code, order = call("/tools/query_order", {"order_id": "JD2026002"})
    assert code == 200 and order["data_source"] == "demo_snapshot"
    checks.append("SQLite order lookup via running HTTP service")
    code, tracking = call("/tools/query_tracking", {"order_id": "JD2026002"})
    assert code == 200 and tracking["events"]
    code, evidence = call("/tools/search_sop", {"query": "订单延迟如何处理"})
    assert code == 200 and evidence["results"][0]["source"] == "04_订单延迟处理SOP.md"
    checks.append("Tracking snapshot and citable SOP retrieval")
    code, draft = call("/tools/prepare_ticket", {**context, "order_id": "JD2026002", "summary": "本地验收模拟：延迟订单需核实节点"})
    assert code == 200 and draft["needs_confirmation"]
    payload = {**context, "proposal_id": draft["proposal_id"], "user_message": "好的"}
    assert call("/tools/create_ticket", payload)[0] == 409
    checks.append("Generic assent rejected without ticket creation")
    scope = {}
    exec(GATE_CODE, scope)
    gate = scope["main"](draft["confirmation_phrase"], context["user_id"], context["conversation_id"])
    assert gate["is_confirmation"] == "yes"
    payload = json.loads(gate["body"])
    code, result = call("/tools/create_ticket", payload)
    assert code == 200 and result["created"]
    ticket_id = result["ticket"]["ticket_id"]
    assert call("/tools/create_ticket", payload)[1]["created"] is False
    checks.append("Deterministic gate confirmation and idempotent creation")
    for previous, status in [("open", "processing"), ("processing", "resolved"), ("resolved", "closed")]:
        code, _ = call("/admin/tickets/" + ticket_id + "/status",
                       {"expected_status": previous, "status": status, "note": "本地验收模拟处理步骤：" + status}, admin=True, method="PATCH")
        assert code == 200
    code, queried = call("/tools/query_ticket", {"user_id": context["user_id"], "ticket_id": ticket_id})
    ticket = queried["tickets"][0]
    assert code == 200 and ticket["status"] == "closed"
    assert [event["to_status"] for event in ticket["events"]] == ["open", "processing", "resolved", "closed"]
    checks.append("Operator lifecycle and persisted event history via HTTP")
    report = {"scope": "local HTTP API and deterministic confirmation only; no Dify or LLM inference",
              "timestamp_utc": datetime.now(timezone.utc).isoformat(), "passed": True,
              "checks": checks, "ticket_id": ticket_id, "final_status": ticket["status"]}
    output = ROOT / "evaluation/results/agent_local_acceptance.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
