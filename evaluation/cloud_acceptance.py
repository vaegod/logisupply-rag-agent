"""Real cloud API + Dify multi-turn acceptance. Never reports success without calls.

Requires LOGISUPPLY_PUBLIC_URL, LOGISUPPLY_TOOL_API_KEY,
LOGISUPPLY_ADMIN_API_KEY and DIFY_API_KEY in the process environment.
Creates and closes synthetic acceptance tickets; writes a report only on success.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error
from urllib.parse import urlsplit
from uuid import uuid4

LAST_REPORT: dict = {}


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("replace-"):
        raise RuntimeError(f"Missing deployment setting: {name}")
    return value


def invoke(url: str, body: dict | None, headers: dict, method="POST"):
    req = request.Request(url, data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                          method=method, headers={"Content-Type": "application/json", **headers})
    try:
        with request.urlopen(req, timeout=60) as response:
            return json.load(response)
    except error.HTTPError as exc:
        # Do not include request headers or secrets in error output.
        raise RuntimeError(f"Cloud endpoint returned HTTP {exc.code}: {urlsplit(url).path}") from exc


def main():
    global LAST_REPORT
    base = required("LOGISUPPLY_PUBLIC_URL").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise RuntimeError("Use the actual HTTPS cloud backend origin")
    if parsed.hostname in {"localhost", "127.0.0.1", "replace-me.example.com"}:
        raise RuntimeError("A local or placeholder address is not cloud acceptance")
    tool_headers = {"X-API-Key": required("LOGISUPPLY_TOOL_API_KEY")}
    admin_headers = {"X-Admin-Key": required("LOGISUPPLY_ADMIN_API_KEY")}
    dify_headers = {"Authorization": "Bearer " + required("DIFY_API_KEY")}
    dify_base = os.getenv("DIFY_API_BASE", "https://api.dify.ai/v1").rstrip("/")
    run_id = uuid4().hex
    report = {"scope": "real deployed backend plus published Dify multi-turn acceptance",
              "run_id": run_id, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "backend_origin": base, "steps": [], "dify_turns": []}
    LAST_REPORT = report
    def tool(name, body):
        return invoke(base + "/tools/" + name, body, tool_headers)
    def transition(ticket_id, previous, status):
        return invoke(base + "/admin/tickets/" + ticket_id + "/status",
                      {"expected_status": previous, "status": status, "note": "云端验收模拟处理步骤：" + status},
                      admin_headers, "PATCH")
    assert invoke(base + "/health", None, {}, "GET")["status"] == "ok"
    assert tool("query_order", {"order_id": "JD2026002"})["order"]["order_id"] == "JD2026002"
    assert tool("query_tracking", {"order_id": "JD2026002"})["events"]
    assert tool("search_sop", {"query": "订单延迟处理"})["results"]
    report["steps"].append("Public HTTPS health, order, tracking and SOP tools succeeded")
    context = {"user_id": "api-acceptance-" + run_id, "conversation_id": run_id}
    draft = tool("prepare_ticket", {**context, "order_id": "JD2026002", "summary": "云端 API 验收模拟：订单延迟需核实"})
    confirmation = {**context, "proposal_id": draft["proposal_id"], "user_message": draft["confirmation_phrase"]}
    created = tool("create_ticket", confirmation)
    ticket_id = created["ticket"]["ticket_id"]
    assert created["created"] and not tool("create_ticket", confirmation)["created"]
    for previous, status in [("open", "processing"), ("processing", "resolved"), ("resolved", "closed")]:
        transition(ticket_id, previous, status)
    ticket = tool("query_ticket", {"user_id": context["user_id"], "ticket_id": ticket_id})["tickets"][0]
    assert [event["to_status"] for event in ticket["events"]] == ["open", "processing", "resolved", "closed"]
    report["api_ticket_id"] = ticket_id
    report["steps"].append("Real cloud ticket creation, idempotency and operator lifecycle succeeded")

    conversation = ""
    def chat(query):
        nonlocal conversation
        started = time.perf_counter()
        result = invoke(dify_base + "/chat-messages",
                        {"inputs": {}, "query": query, "user": "dify-acceptance-" + run_id,
                         "response_mode": "blocking", "conversation_id": conversation}, dify_headers)
        conversation = result["conversation_id"]
        answer = result.get("answer", "")
        assert answer and "{{#" not in answer, "Empty answer or unexpanded Dify variable"
        report["dify_turns"].append({"query": query, "answer": answer,
                                     "message_id": result.get("message_id"),
                                     "latency_seconds": round(time.perf_counter() - started, 3)})
        return answer

    answer = chat("查询 JD2026003 温度异常情况，检索处理规范，并帮我准备异常工单。")
    phrase = re.search(r"确认创建工单 (P-[0-9a-f]{16})", answer)
    assert phrase, "Dify did not return a real proposal confirmation phrase"
    confirmed = chat(phrase.group(0))
    match = re.search(r"T-[0-9a-f]{16}", confirmed)
    assert match, "Dify did not return a ticket ID"
    dify_ticket = match.group(0)
    assert dify_ticket in chat(phrase.group(0)), "Duplicate confirmation changed the ticket ID"
    # The first transition proves the model's ticket ID exists on the real backend.
    for previous, status, terms in [("open", "processing", ("处理中", "processing")),
                                    ("processing", "resolved", ("已解决", "resolved")),
                                    ("resolved", "closed", ("已关闭", "closed"))]:
        transition(dify_ticket, previous, status)
        answer = chat(f"查询工单 {dify_ticket} 的当前处理状态和记录。")
        assert any(term in answer for term in terms), f"Dify did not report state {status}: {answer}"
    report["dify_ticket_id"] = dify_ticket
    report["conversation_id"] = conversation
    report["steps"].append("Dify draft, exact user confirmation, duplicate confirmation and lifecycle progress succeeded")
    report["passed"] = True
    output = Path(__file__).parent / "results/cloud_acceptance.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "report": str(output), "dify_ticket_id": dify_ticket}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, AssertionError, error.URLError, TimeoutError) as exc:
        if LAST_REPORT:
            LAST_REPORT.update(passed=False, error=str(exc))
            output = Path(__file__).parent / "results/cloud_acceptance_failed.json"
            output.write_text(json.dumps(LAST_REPORT, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(f"Cloud acceptance did not pass: {exc}")
