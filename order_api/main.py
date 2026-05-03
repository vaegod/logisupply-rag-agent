from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="LogiSupply Order API",
    description="用于 Dify Agent 工作流调用的模拟物流订单查询接口",
    version="1.0.0",
)

DATA_FILE = Path(__file__).parent / "orders.json"


class ExceptionRequest(BaseModel):
    order_id: str
    user_problem: str | None = None


def load_orders() -> list[dict]:
    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def find_order(order_id: str) -> dict | None:
    for order in load_orders():
        if order["order_id"].upper() == order_id.upper():
            return order
    return None


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "service": "logisupply-order-api"}


@app.get("/orders/{order_id}")
def get_order(order_id: str) -> dict:
    order = find_order(order_id)
    if order is None:
        raise HTTPException(
            status_code=404,
            detail={"found": False, "message": f"未找到订单：{order_id}"},
        )

    return {"found": True, "order": order}


@app.post("/orders/analyze")
def analyze_order_exception(req: ExceptionRequest) -> dict:
    order = find_order(req.order_id)
    if order is None:
        raise HTTPException(
            status_code=404,
            detail={"found": False, "message": f"未找到订单：{req.order_id}"},
        )

    exception_type = order["exception_type"]

    if exception_type == "无异常":
        risk_level = "低"
        suggestion = "订单当前无异常，建议告知客户订单正在正常流转。"
    elif "延迟" in exception_type:
        risk_level = "中"
        suggestion = "建议查询延迟节点，预估新的送达时间，并主动通知客户。"
    elif "温度" in exception_type:
        risk_level = "高"
        suggestion = "冷链订单出现温度异常，建议立即升级人工处理，并核查温控记录。"
    elif "破损" in exception_type:
        risk_level = "高"
        suggestion = "建议要求站点上传破损照片，登记异常工单，并根据规则判断赔付责任。"
    else:
        risk_level = "中"
        suggestion = "建议创建异常工单，并交由运营人员进一步处理。"

    return {
        "found": True,
        "order": order,
        "risk_level": risk_level,
        "suggestion": suggestion,
        "user_problem": req.user_problem,
    }

