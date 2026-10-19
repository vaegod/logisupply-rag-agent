"""Local FastAPI + real Embedding + persisted Milvus + optional real model tool loop.

No deployed Dify application or production ticket database is modified.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from order_api.main import create_app
from order_api.rag import load_retriever


def citation_checks(answer: str, citations: list[str]) -> dict:
    # A filename declared once plus its full section path remains a valid
    # source/section reference. Track exact formatting separately from evidence.
    pairs = [citation.strip("[]").split(" / ", 1) for citation in citations]
    return {"source_and_section": any(len(pair) == 2 and pair[0] in answer and pair[1] in answer for pair in pairs),
            "exact_format": any(citation in answer for citation in citations)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm-env", type=Path, help="Optional existing private dotenv with LLM_API_KEY/BASE_URL/MODEL")
    parser.add_argument("--model", help="Override model for this local acceptance only")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    if args.llm_env:
        load_dotenv(args.llm_env, override=False)
    selected_model = args.model or os.getenv("LLM_MODEL", "")
    engine = load_retriever()
    index_name = engine.collection
    assert engine.ready()
    engine.close()
    engine = load_retriever()
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "scope": "local_api_real_embedding_milvus",
              "dify_cloud_republished": False, "checks": {}, "model_runs": []}
    try:
        assert engine.ready() and engine.collection == index_name
        report["index"] = engine.index_info("reopened")
        if report["index"]["vector_backend"] == "milvus_server":
            report["server_version"] = engine.client.get_server_version(timeout=engine.settings.timeout)
        report["checks"]["milvus_reopen"] = True
        with tempfile.TemporaryDirectory() as folder:
            application = create_app(Path(folder) / "acceptance.db", tool_key="acceptance-tool",
                                     admin_key="acceptance-admin", sop_search=engine.search)
            with TestClient(application) as api:
                headers = {"X-API-Key": "acceptance-tool"}
                context = {"user_id": "acceptance-user", "conversation_id": "acceptance-chat"}

                def call(name, body, strict=True):
                    response = api.post("/tools/" + name, headers=headers, json=body)
                    if strict:
                        response.raise_for_status()
                    elif response.status_code != 200:
                        return {"tool_failed": True, "http_status": response.status_code, "detail": response.json()}
                    return response.json()

                evidence = call("search_sop", {"query": "冷链温度报警应该如何处理"})
                assert evidence["retrieval_method"] == "hybrid_bm25_milvus_rrf" and not evidence["degraded"]
                assert any(row["source"] == "03_冷链运输规范.md" for row in evidence["results"])
                report["checks"]["api_real_hybrid_evidence"] = True
                draft = call("prepare_ticket", {**context, "order_id": "JD2026003", "summary": "模拟冷链异常，请人工核实"})
                confirm = {**context, "proposal_id": draft["proposal_id"], "user_message": draft["confirmation_phrase"]}
                ticket = call("create_ticket", confirm)["ticket"]
                replay = call("create_ticket", confirm)
                assert replay["created"] is False and replay["ticket"]["ticket_id"] == ticket["ticket_id"]
                report["checks"]["confirmation_idempotency"] = True
                state = "open"
                for target in ("processing", "resolved", "closed"):
                    response = api.patch(f"/admin/tickets/{ticket['ticket_id']}/status",
                                         headers={"X-Admin-Key": "acceptance-admin"},
                                         json={"expected_status": state, "status": target, "note": "本地验收模拟处理"})
                    response.raise_for_status()
                    state = target
                found = call("query_ticket", {"user_id": context["user_id"], "ticket_id": ticket["ticket_id"]})
                assert found["tickets"][0]["status"] == "closed"
                assert len(found["tickets"][0]["events"]) == 4
                report["checks"]["ticket_lifecycle"] = True

                if args.llm_env:
                    spec = api.get("/agent-openapi.json").json()
                    names = ("query_order", "query_tracking", "search_sop", "prepare_ticket")
                    tools = []
                    for name in names:
                        operation = spec["paths"]["/tools/" + name]["post"]
                        schema = operation["requestBody"]["content"]["application/json"]["schema"]
                        schema = json.loads(json.dumps(schema))
                        for key in ("user_id", "conversation_id"):
                            schema["properties"].pop(key, None)
                            if key in schema.get("required", []):
                                schema["required"].remove(key)
                        tools.append({"type": "function", "function": {"name": name,
                                     "description": operation["description"], "parameters": schema}})
                    prompt = (ROOT / "prompts/logistics_agent_prompt.md").read_text(encoding="utf-8").split("---", 1)[-1]
                    queries = ["冷藏车里的医药样本出现温度报警，应该如何处理？请检索并引用文件和章节。",
                               "JD2026002 延迟该怎么办？查询订单并检索制度，帮我准备工单草稿。",
                               "根据物流SOP告诉我明天上海会不会下雨；没有相关依据就明确说明。"]
                    with httpx.Client(timeout=90) as model_api:
                        for query in queries:
                            messages = [{"role": "system", "content": prompt}, {"role": "user", "content": query}]
                            trace = []
                            for _ in range(8):
                                response = model_api.post(os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions",
                                                          headers={"Authorization": "Bearer " + os.environ["LLM_API_KEY"]},
                                                          json={"model": selected_model, "messages": messages,
                                                                "tools": tools, "tool_choice": "auto", "enable_thinking": False,
                                                                "temperature": 0, "max_tokens": 1800})
                                if response.status_code != 200:
                                    raise RuntimeError(f"model_http_{response.status_code}")
                                answer = response.json()["choices"][0]["message"]
                                messages.append({key: answer[key] for key in ("role", "content", "tool_calls") if key in answer})
                                calls = answer.get("tool_calls") or []
                                if not calls:
                                    assert answer.get("content")
                                    report["model_runs"].append({"question": query, "tools": trace, "answer": answer["content"],
                                                                 "model": selected_model})
                                    break
                                for item in calls:
                                    name = item["function"]["name"]
                                    if name not in names:
                                        raise AssertionError("Model selected a tool outside the allowlist")
                                    body = json.loads(item["function"]["arguments"])
                                    if name == "prepare_ticket":
                                        body.update(context)
                                    result = call(name, body, strict=False)
                                    trace.append({"name": name, "retrieval_method": result.get("retrieval_method"),
                                                  "arguments": body, "tool_failed": result.get("tool_failed", False),
                                                  "citations": [r["citation"] for r in result.get("results", [])]})
                                    messages.append({"role": "tool", "tool_call_id": item["id"], "content": json.dumps(result, ensure_ascii=False)})
                            else:
                                raise AssertionError("Model did not finish within iteration budget")
                    report["checks"]["real_model_sop_tool"] = any(t["name"] == "search_sop" and not t["tool_failed"] for t in report["model_runs"][0]["tools"])
                    citations = [c for t in report["model_runs"][0]["tools"] for c in t["citations"]]
                    citation_result = citation_checks(report["model_runs"][0]["answer"], citations)
                    report["checks"]["real_model_citation"] = citation_result["source_and_section"]
                    report["citation_exact_format"] = citation_result["exact_format"]
                    report["checks"]["real_model_order_sop_draft"] = {"query_order", "search_sop", "prepare_ticket"} <= {t["name"] for t in report["model_runs"][1]["tools"] if not t["tool_failed"]}
                    report["checks"]["out_of_scope_weather_refusal"] = not report["model_runs"][2]["tools"] and any(
                        term in report["model_runs"][2]["answer"] for term in ("无法", "不能", "没有", "未提及", "不包含"))
                    report["note"] = "本地自定义工具循环验收，不等于重新发布Dify；模型输出供人工复核，不作为通用准确率"
        passed = all(report["checks"].values())
        report["status"] = "passed" if passed else "model_review_required"
        path = ROOT / ("evaluation/results/hybrid_acceptance.json" if passed else "evaluation/results/hybrid_acceptance_initial.json")
        if not passed and path.exists():
            path = path.with_stem(path.stem + "_" + datetime.now(timezone.utc).strftime("%H%M%S%f"))
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"report": str(path), "checks": report["checks"], "model_runs": len(report["model_runs"])}, ensure_ascii=False))
        if not passed:
            raise SystemExit(1)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
