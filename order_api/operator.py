"""Operator CLI for the demo ticket lifecycle; never exposed as an Agent tool."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib import request, error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticket_id")
    parser.add_argument("--expected", required=True, choices=["open", "processing", "resolved"])
    parser.add_argument("--status", required=True, choices=["processing", "resolved", "closed"])
    parser.add_argument("--note", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8018")
    args = parser.parse_args()
    key = os.getenv("LOGISUPPLY_ADMIN_API_KEY")
    local = Path(__file__).resolve().parents[1] / "dify/local/runtime.json"
    if not key and local.exists():
        key = json.loads(local.read_text(encoding="utf-8"))["admin_key"]
    if not key:
        parser.error("请设置 LOGISUPPLY_ADMIN_API_KEY；本地演示可先运行 python -m order_api.run_demo")
    if args.base_url.rstrip("/") != "http://127.0.0.1:8018" and not os.getenv("LOGISUPPLY_ADMIN_API_KEY"):
        parser.error("远程操作需要显式设置 LOGISUPPLY_ADMIN_API_KEY，不自动发送本地密钥")
    if not args.ticket_id.startswith("T-") or any(c not in "0123456789abcdef" for c in args.ticket_id[2:]):
        parser.error("工单号格式无效")
    payload = json.dumps({"expected_status": args.expected, "status": args.status, "note": args.note}).encode()
    req = request.Request(args.base_url.rstrip("/") + "/admin/tickets/" + args.ticket_id + "/status",
                          data=payload, method="PATCH", headers={"Content-Type": "application/json", "X-Admin-Key": key})
    try:
        with request.urlopen(req, timeout=30) as response:
            print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
    except error.HTTPError as exc:
        parser.exit(1, exc.read().decode("utf-8", errors="replace") + "\n")
    except error.URLError:
        parser.exit(1, "无法连接工单服务，请检查地址和服务状态。\n")


if __name__ == "__main__":
    main()
