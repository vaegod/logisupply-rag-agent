"""Generate a Dify classic Agent Chatflow and its OpenAPI tool specification.

Run at repository root: python dify/build_agent.py --help
Workspace-specific output belongs under dify/local/ (gitignored).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from order_api.main import create_app

GATE_CODE = '''import json
import re

def main(query: str, user_id: str, conversation_id: str) -> dict:
    match = re.fullmatch(r"确认创建工单 (P-[0-9a-f]{16})", query.strip())
    ticket_ids = set(re.findall(r"T-[0-9a-f]{16}", query))
    ticket_query = len(ticket_ids) == 1 and any(word in query for word in ("查", "进度", "状态", "记录", "结果"))
    return {"is_confirmation": "yes" if match else "no",
            "is_ticket_query": "yes" if ticket_query else "no",
            "ticket_query_body": json.dumps({"user_id": user_id, "ticket_id": next(iter(ticket_ids)) if ticket_query else ""}, ensure_ascii=False),
            "body": json.dumps({"proposal_id": match.group(1) if match else "",
                                "user_message": query, "user_id": user_id,
                                "conversation_id": conversation_id}, ensure_ascii=False)}
'''

QUERY_FORMAT_CODE = '''import json

def main(body: str, status_code: int) -> dict:
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return {"text": "工单查询服务响应异常，无法确认最新状态，请稍后重试。"}
    tickets = data.get("tickets", []) if isinstance(data, dict) else []
    if status_code != 200 or not tickets:
        return {"text": "未查询到属于当前用户的工单，或查询服务暂不可用。请核对工单号后重试。"}
    ticket = tickets[0]
    labels = {"open": "待处理", "processing": "处理中", "resolved": "已解决", "closed": "已关闭"}
    status = ticket["status"]
    lines = ["工单号：" + ticket["ticket_id"], "订单号：" + ticket["order_id"],
             "当前状态：" + labels.get(status, status) + "（" + status + "）",
             "更新时间：" + ticket["updated_at"], "摘要：" + ticket["summary"]]
    if ticket.get("resolution"):
        lines.append("解决说明：" + ticket["resolution"])
    lines.append("处理记录：")
    for event in ticket.get("events", []):
        lines.append(event["occurred_at"] + " | " + (event.get("from_status") or "新建")
                     + " → " + event["to_status"] + " | " + event["note"])
    lines.append("以上状态来自本轮工单接口查询。")
    return {"text": "\\n".join(lines)}
'''

FORMAT_CODE = '''import json

def main(body: str, status_code: int) -> dict:
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return {"text": "工单服务响应异常，未确认创建成功，请稍后重试或查询工单。"}
    if status_code != 200 or not isinstance(data, dict) or "ticket" not in data:
        detail = data.get("detail", {}) if isinstance(data, dict) else {}
        message = detail.get("message", "草稿可能已过期或服务暂不可用") if isinstance(detail, dict) else "服务暂不可用"
        return {"text": "未创建新工单：" + message + "。请重新查询或生成草稿。"}
    ticket = data["ticket"]
    prefix = "工单已创建" if data.get("created") else "工单已存在，本次未重复创建"
    return {"text": prefix + "\\n工单号：" + ticket["ticket_id"] + "\\n订单号：" + ticket["order_id"]
            + "\\n状态：" + ticket["status"] + "\\n摘要：" + ticket["summary"]
            + "\\n可继续询问工单进度；处理状态由运营人员更新。"}
'''


def node(node_id: str, kind: str, title: str, x: int, y: int, **data) -> dict:
    return {"id": node_id, "type": "custom", "position": {"x": x, "y": y},
            "sourcePosition": "right", "targetPosition": "left", "width": 244, "height": 110,
            "data": {"type": kind, "title": title, "desc": "", "selected": False, **data}}


def variable(name: str, selector: list[str]) -> dict:
    return {"variable": name, "value_selector": selector, "value_type": "string"}


def build(provider_id="REPLACE_API_PROVIDER_ID", model_provider="", model_name="",
          plugin_id="", api_base="https://replace-me.example.com") -> tuple[dict, dict]:
    spec = TestClient(create_app()).get("/agent-openapi.json").json()
    spec["servers"] = [{"url": api_base.rstrip("/")}]
    tools = []
    for path in spec["paths"].values():
        operation = path["post"]
        if operation["operationId"] == "create_ticket":
            continue  # Only the deterministic branch may write a ticket.
        body = operation["requestBody"]["content"]["application/json"]["schema"]
        parameters = {}
        for name, definition in body["properties"].items():
            manual = name in {"user_id", "conversation_id"}
            parameters[name] = {"auto": 0 if manual else 1,
                                "value": {"type": "mixed", "value": "{{#sys." + name + "#}}"} if manual else None}
        tools.append({"enabled": True, "type": "api", "provider_name": provider_id,
                      "provider_show_name": "LogiSupply V2 物流工具", "plugin_id": None,
                      "tool_name": operation["operationId"], "tool_label": operation["operationId"],
                      "tool_description": operation.get("description", ""),
                      "extra": {"description": operation.get("description", "")},
                      "parameters": parameters, "settings": {}})
    prompt = (ROOT / "prompts/logistics_agent_prompt.md").read_text(encoding="utf-8").split("---\n", 1)[1].strip()
    nodes = [
        node("start", "start", "用户输入", 0, 300, variables=[]),
        node("confirmation_gate", "code", "识别确认与实时工单查询", 300, 300,
             code_language="python3", code=GATE_CODE,
             variables=[variable("query", ["sys", "query"]), variable("user_id", ["sys", "user_id"]),
                        variable("conversation_id", ["sys", "conversation_id"])],
             outputs={name: {"type": "string", "children": None} for name in
                      ("is_confirmation", "body", "is_ticket_query", "ticket_query_body")}),
        node("confirmation_branch", "if-else", "确认、实时查询或智能体", 600, 300,
             cases=[{"id": "confirmed", "case_id": "confirmed", "logical_operator": "and", "conditions": [
                 {"id": "confirmed-condition", "variable_selector": ["confirmation_gate", "is_confirmation"],
                  "varType": "string", "comparison_operator": "is", "value": "yes"}]},
                    {"id": "ticket_query", "case_id": "ticket_query", "logical_operator": "and", "conditions": [
                        {"id": "ticket-query-condition", "variable_selector": ["confirmation_gate", "is_ticket_query"],
                         "varType": "string", "comparison_operator": "is", "value": "yes"}]}]),
        node("logistics_agent", "agent", "物流工具调用智能体", 900, 500,
             agent_strategy_provider_name="langgenius/agent/agent", agent_strategy_name="function_calling",
             agent_strategy_label="FunctionCalling", plugin_unique_identifier=plugin_id,
             tool_node_version="2", output_schema={},
             memory={"query_prompt_template": "{{#sys.query#}}", "window": {"enabled": True, "size": 20}},
             agent_parameters={
                 "model": {"type": "constant", "value": {"provider": model_provider, "model": model_name,
                            "model_type": "llm", "mode": "chat", "type": "model-selector",
                            "completion_params": {"temperature": 0.1}}},
                 "instruction": {"type": "constant", "value": prompt},
                 "query": {"type": "constant", "value": "{{#sys.query#}}"},
                 "maximum_iterations": {"type": "constant", "value": 8},
                 "tools": {"type": "constant", "value": tools}}),
        node("answer_agent", "answer", "智能体回答", 1200, 500, answer="{{#logistics_agent.text#}}", variables=[]),
        node("create_ticket", "http-request", "用户确认后创建工单", 900, 100,
             method="POST", url="{{#env.ORDER_API_BASE#}}/tools/create_ticket",
             authorization={"type": "no-auth", "config": None},
             headers="Content-Type:application/json\nX-API-Key:{{#env.LOGISUPPLY_TOOL_API_KEY#}}", params="",
             body={"type": "json", "data": [{"id": "confirmation-body", "key": "", "type": "text",
                                          "value": "{{#confirmation_gate.body#}}"}]},
             timeout={"connect": 10, "read": 30, "write": 30},
             retry_config={"retry_enabled": True, "max_retries": 1, "retry_interval": 500}),
        node("format_ticket", "code", "工单写入结果", 1200, 100,
             code_language="python3", code=FORMAT_CODE,
             variables=[variable("body", ["create_ticket", "body"]),
                        {"variable": "status_code", "value_selector": ["create_ticket", "status_code"], "value_type": "number"}],
             outputs={"text": {"type": "string", "children": None}}),
        node("answer_ticket", "answer", "工单确认答复", 1500, 100, answer="{{#format_ticket.text#}}", variables=[]),
        node("query_ticket_live", "http-request", "实时查询工单状态", 900, 850,
             method="POST", url="{{#env.ORDER_API_BASE#}}/tools/query_ticket",
             authorization={"type": "no-auth", "config": None},
             headers="Content-Type:application/json\nX-API-Key:{{#env.LOGISUPPLY_TOOL_API_KEY#}}", params="",
             body={"type": "json", "data": [{"id": "ticket-query-body", "key": "", "type": "text",
                                            "value": "{{#confirmation_gate.ticket_query_body#}}"}]},
             timeout={"connect": 10, "read": 30, "write": 30},
             retry_config={"retry_enabled": True, "max_retries": 1, "retry_interval": 500}),
        node("format_ticket_query", "code", "展示本轮实时工单记录", 1200, 850,
             code_language="python3", code=QUERY_FORMAT_CODE,
             variables=[variable("body", ["query_ticket_live", "body"]),
                        {"variable": "status_code", "value_selector": ["query_ticket_live", "status_code"], "value_type": "number"}],
             outputs={"text": {"type": "string", "children": None}}),
        node("answer_ticket_query", "answer", "工单实时状态答复", 1500, 850,
             answer="{{#format_ticket_query.text#}}", variables=[]),
    ]
    by_id = {item["id"]: item for item in nodes}
    def edge(source, target, handle="source"):
        return {"id": source + "-" + target, "source": source, "sourceHandle": handle,
                "target": target, "targetHandle": "target", "type": "custom",
                "data": {"sourceType": by_id[source]["data"]["type"], "targetType": by_id[target]["data"]["type"],
                         "isInIteration": False, "isInLoop": False}}
    features = copy.deepcopy(yaml.safe_load((ROOT / "dify/logisupply_chatflow.dify.yml").read_text(encoding="utf-8"))["workflow"]["features"])
    features["opening_statement"] = "我是物流工具调用助手，可查询历史演示订单、检索 SOP 并生成异常工单草稿。创建工单需要你发送完整确认短语。"
    features["suggested_questions"] = ["查询 JD2026001 的订单状态", "JD2026002 延迟怎么处理？帮我准备工单", "冷链温度报警应该如何处理？"]
    env = [{"id": str(uuid5(NAMESPACE_URL, "logisupply/" + name)), "name": name,
            "selector": ["env", name], "value_type": kind, "value": value, "description": description}
           for name, kind, value, description in [
               ("ORDER_API_BASE", "string", api_base.rstrip("/"), "公网可达工具后端地址"),
               ("LOGISUPPLY_TOOL_API_KEY", "secret", "", "与后端一致的工具密钥；不配置操作员密钥")]]
    dependencies = ([{"current_identifier": None, "type": "marketplace", "value": {
        "marketplace_plugin_unique_identifier": plugin_id}}] if plugin_id else [])
    dsl = {"app": {"name": "物流异常处理智能体 V2", "description": "Agent 自主选工具 + 用户确认创建工单 + SQLite 历史演示数据",
                   "icon": "🚚", "icon_background": "#E4FBCC", "mode": "advanced-chat", "use_icon_as_answer_icon": False},
           "kind": "app", "version": "0.3.1", "dependencies": dependencies,
           "workflow": {"conversation_variables": [], "environment_variables": env, "features": features,
                        "graph": {"nodes": nodes, "edges": [
                            edge("start", "confirmation_gate"), edge("confirmation_gate", "confirmation_branch"),
                            edge("confirmation_branch", "logistics_agent", "false"), edge("logistics_agent", "answer_agent"),
                            edge("confirmation_branch", "create_ticket", "confirmed"), edge("create_ticket", "format_ticket"),
                            edge("format_ticket", "answer_ticket"),
                            edge("confirmation_branch", "query_ticket_live", "ticket_query"),
                            edge("query_ticket_live", "format_ticket_query"),
                            edge("format_ticket_query", "answer_ticket_query")], "viewport": {"x": 0, "y": 0, "zoom": 0.7}}}}
    return dsl, spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-id", default="REPLACE_API_PROVIDER_ID", help="Dify 自定义 API 工具的 provider ID，导出 DSL 可见")
    parser.add_argument("--model-provider", default="", help="工作区中的模型 provider 标识")
    parser.add_argument("--model", default="", help="支持 tool calling 的模型名称")
    parser.add_argument("--agent-plugin-id", default="", help="已安装官方 Agent Strategy 插件完整标识，可从导出 DSL 获取")
    parser.add_argument("--api-base", default="https://replace-me.example.com")
    parser.add_argument("--output", type=Path, default=ROOT / "dify/local/logisupply_agent.dify.yml")
    args = parser.parse_args()
    dsl, spec = build(args.provider_id, args.model_provider, args.model, args.agent_plugin_id, args.api_base)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(dsl, allow_unicode=True, sort_keys=False), encoding="utf-8")
    schema_file = args.output.parent / "agent_tools.openapi.json"
    schema_file.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DSL: {args.output}\nOpenAPI: {schema_file}\n导入后检查工具绑定、模型、策略插件及环境变量。未配置时不能声明线上运行通过。")


if __name__ == "__main__":
    main()
