"""Transactional proposals, user confirmation and operator status transitions."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from .database import Database


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fail(code: int, error: str, message: str):
    raise HTTPException(code, detail={"error": error, "message": message})


def ticket_dict(conn, row) -> dict:
    ticket = dict(row)
    ticket["events"] = [dict(event) for event in conn.execute(
        "SELECT from_status,to_status,note,actor,occurred_at FROM ticket_events "
        "WHERE ticket_id=? ORDER BY event_id", (row["ticket_id"],))]
    return ticket


class Tickets:
    def __init__(self, db: Database):
        self.db = db

    def prepare(self, order_id: str, summary: str, user_id: str, conversation_id: str) -> dict:
        order_id = order_id.strip().upper()
        if self.db.find_order(order_id) is None:
            fail(404, "order_not_found", "未找到订单，不能生成工单草稿。")
        current = now()
        with self.db.connect(write=True) as conn:
            existing = conn.execute(
                "SELECT * FROM tickets WHERE user_id=? AND order_id=? AND status!='closed'",
                (user_id, order_id)).fetchone()
            if existing:
                return {"needs_confirmation": False, "existing_ticket": ticket_dict(conn, existing)}
            proposal = conn.execute(
                "SELECT * FROM proposals WHERE user_id=? AND conversation_id=? AND order_id=? "
                "AND summary=? AND expires_at>? "
                "AND NOT EXISTS(SELECT 1 FROM tickets WHERE tickets.proposal_id=proposals.proposal_id) "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id, conversation_id, order_id, summary, current)).fetchone()
            if not proposal:
                proposal_id = "P-" + secrets.token_hex(8)
                expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(timespec="seconds")
                conn.execute("INSERT INTO proposals VALUES (?,?,?,?,?,?,?)",
                             (proposal_id, user_id, conversation_id, order_id, summary, current, expires))
                proposal = conn.execute("SELECT * FROM proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
            return {"needs_confirmation": True,
                    "proposal_id": proposal["proposal_id"], "order_id": order_id,
                    "summary": summary, "expires_at": proposal["expires_at"],
                    "confirmation_phrase": "确认创建工单 " + proposal["proposal_id"]}

    def create(self, proposal_id: str, user_message: str, user_id: str, conversation_id: str) -> dict:
        with self.db.connect(write=True) as conn:
            proposal = conn.execute(
                "SELECT * FROM proposals WHERE proposal_id=? AND user_id=? AND conversation_id=?",
                (proposal_id, user_id, conversation_id)).fetchone()
            if not proposal:
                fail(404, "proposal_not_found", "草稿不存在或不属于当前会话。")
            if user_message.strip() != "确认创建工单 " + proposal_id:
                fail(409, "confirmation_required", "请由用户发送草稿中的完整确认短语。")
            existing = conn.execute("SELECT * FROM tickets WHERE proposal_id=?", (proposal_id,)).fetchone()
            if existing:
                return {"created": False, "ticket": ticket_dict(conn, existing)}
            if proposal["expires_at"] <= now():
                fail(409, "proposal_expired", "草稿已过期，请重新生成并确认。")
            existing = conn.execute(
                "SELECT * FROM tickets WHERE user_id=? AND order_id=? AND status!='closed'",
                (user_id, proposal["order_id"])).fetchone()
            if existing:
                return {"created": False, "ticket": ticket_dict(conn, existing)}
            ticket_id, current = "T-" + secrets.token_hex(8), now()
            conn.execute("INSERT INTO tickets VALUES (?,?,?,?,?,'open','',?,?)",
                         (ticket_id, proposal_id, user_id, proposal["order_id"], proposal["summary"], current, current))
            conn.execute("INSERT INTO ticket_events(ticket_id,from_status,to_status,note,actor,occurred_at) "
                         "VALUES (?,NULL,'open',?,?,?)",
                         (ticket_id, "用户确认创建：" + proposal["summary"], "user:" + user_id, current))
            row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
            return {"created": True, "ticket": ticket_dict(conn, row)}

    def query(self, user_id: str, ticket_id: str | None, order_id: str | None) -> dict:
        with self.db.connect() as conn:
            if ticket_id:
                rows = conn.execute("SELECT * FROM tickets WHERE ticket_id=? AND user_id=?",
                                    (ticket_id, user_id)).fetchall()
                if not rows:
                    fail(404, "ticket_not_found", "未找到属于当前用户的工单。")
            else:
                rows = conn.execute("SELECT * FROM tickets WHERE order_id=? AND user_id=? ORDER BY created_at,ticket_id",
                                    (order_id.strip().upper(), user_id)).fetchall()
            return {"tickets": [ticket_dict(conn, row) for row in rows]}

    def transition(self, ticket_id: str, expected_status: str, status: str, note: str) -> dict:
        allowed = {"open": {"processing"}, "processing": {"resolved"},
                   "resolved": {"closed", "processing"}, "closed": set()}
        with self.db.connect(write=True) as conn:
            row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
            if not row:
                fail(404, "ticket_not_found", "工单不存在。")
            if row["status"] != expected_status:
                fail(409, "status_conflict", "工单状态已改变，请重新查询。")
            if status not in allowed[row["status"]]:
                fail(409, "invalid_transition", "不允许跳过处理步骤或修改已关闭工单。")
            current = now()
            resolution = note if status == "resolved" else ("" if status == "processing" else row["resolution"])
            conn.execute("UPDATE tickets SET status=?,resolution=?,updated_at=? WHERE ticket_id=?",
                         (status, resolution, current, ticket_id))
            conn.execute("INSERT INTO ticket_events(ticket_id,from_status,to_status,note,actor,occurred_at) VALUES (?,?,?,?,?,?)",
                         (ticket_id, row["status"], status, note, "operator", current))
            return {"ticket": ticket_dict(conn, conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone())}
