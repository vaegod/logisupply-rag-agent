"""Same-origin gateway. Secrets stay server-side; clients cannot choose user IDs.

Anonymous browser sessions are a demo identity, not enterprise order ownership.
Conversation ownership is persisted before streaming; Dify IDs are accepted only
from the upstream service. Ticket ownership follows that verified conversation.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal
from uuid import uuid4
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .database import Database
from .tickets import Tickets, now, ticket_dict


class ChatBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    conversation_id: str | None = Field(default=None, max_length=36)


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=256)


class TransitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_status: Literal["open", "processing", "resolved", "closed"]
    status: Literal["processing", "resolved", "closed"]
    note: str = Field(min_length=5, max_length=2000, pattern=r"\S")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def register_web_routes(app: FastAPI, db: Database, *, dify_key: str = "",
                        dify_base: str = "https://api.dify.ai/v1", operator_password: str = "",
                        public_url: str = "", transport=None,
                        allow_local_dify_http: bool = False, dify_console_url: str = ""):
    # Tests inject MockTransport. The upstream URL is server configuration only.
    address = urlsplit(dify_base)
    local_dify = (address.scheme == "http" and allow_local_dify_http and address.hostname in
                  {"localhost", "127.0.0.1", "::1", "nginx", "dify-nginx"})
    if dify_key and (address.scheme != "https" and not local_dify or address.username or address.password):
        raise ValueError("Dify API must use HTTPS or an explicitly enabled local Dify endpoint")
    if operator_password and len(operator_password) < 24:
        raise ValueError("Web operator password must contain at least 24 characters")
    ready = False
    inflight: set[str] = set()
    login_attempts: dict[str, deque] = defaultdict(deque)
    service = Tickets(db)

    def initialize():
        nonlocal ready
        if ready:
            return
        with db.connect(write=True) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS web_sessions (
                    token_hash TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    role TEXT NOT NULL, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS web_conversations (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    dify_id TEXT UNIQUE, title TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS web_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES web_conversations(id),
                    role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'complete');
                CREATE TABLE IF NOT EXISTS web_usage (
                    session_id TEXT NOT NULL, occurred_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS web_usage_time ON web_usage(occurred_at);
                CREATE INDEX IF NOT EXISTS web_session_conversations ON web_conversations(session_id);
            """)
        ready = True

    def cookie_secure(request: Request):
        return public_url.startswith("https://") or request.url.scheme == "https"

    def set_session(response: Response, request: Request, role: str):
        initialize()
        token, sid = secrets.token_urlsafe(32), uuid4().hex
        age = 8 * 3600 if role == "operator" else 30 * 86400
        with db.connect(write=True) as conn:
            conn.execute("DELETE FROM web_sessions WHERE expires_at<?", (time.time(),))
            conn.execute("INSERT INTO web_sessions VALUES (?,?,?,?)",
                         (token_hash(token), sid, role, time.time() + age))
        response.set_cookie("ls_operator" if role == "operator" else "ls_session", token,
                            httponly=True, secure=cookie_secure(request), samesite="strict", max_age=age)
        return sid

    def session(request: Request, role="user", optional=False):
        initialize()
        token = request.cookies.get("ls_operator" if role == "operator" else "ls_session", "")
        with db.connect() as conn:
            row = conn.execute("SELECT session_id FROM web_sessions WHERE token_hash=? AND role=? AND expires_at>?",
                               (token_hash(token), role, time.time())).fetchone()
        if row:
            return row[0]
        if not optional:
            raise HTTPException(401, "登录会话已失效，请刷新页面后重试。" if role == "user" else "请先登录操作员工作台。")
        return None

    def same_origin(request: Request):
        origin = request.headers.get("origin")
        allowed = {str(request.base_url).rstrip("/")}
        if public_url:
            allowed.add(public_url.rstrip("/"))
        if origin and origin not in allowed:
            raise HTTPException(403, "请求来源不匹配。")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "不接受跨站请求。")

    def user(request: Request):
        return session(request)

    def operator(request: Request):
        return session(request, "operator")

    def conversation(cid: str, sid: str):
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM web_conversations WHERE id=? AND session_id=?", (cid, sid)).fetchone()
        if not row:
            raise HTTPException(404, "会话不存在或不属于当前浏览器。")
        return dict(row)

    def user_ticket(conn, tid: str, sid: str):
        row = conn.execute("SELECT t.* FROM tickets t JOIN proposals p ON p.proposal_id=t.proposal_id "
                           "JOIN web_conversations c ON c.dify_id=p.conversation_id "
                           "WHERE t.ticket_id=? AND c.session_id=?", (tid, sid)).fetchone()
        if not row:
            raise HTTPException(404, "未找到当前浏览器会话的工单。")
        return ticket_dict(conn, row)

    @app.middleware("http")
    async def browser_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/web/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path in {"/", "/operator"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        return response

    @app.get("/web/bootstrap")
    def bootstrap(request: Request, response: Response):
        sid = session(request, optional=True) or set_session(response, request, "user")
        with db.connect() as conn:
            rows = conn.execute("SELECT id,title,created_at FROM web_conversations WHERE session_id=? "
                                "ORDER BY created_at DESC", (sid,)).fetchall()
        return {"conversations": [dict(r) for r in rows], "orders": db.load_orders(),
                "operator": bool(session(request, "operator", optional=True)), "chat_available": bool(dify_key),
                "deployment_mode": "local" if local_dify else "remote",
                "dify_console_url": dify_console_url,
                "identity_notice": "当前浏览器的匿名演示会话；清除 Cookie 后无法恢复。订单为历史演示快照。"}

    @app.get("/web/conversations/{cid}")
    def get_conversation(cid: str, sid=Depends(user)):
        conv = conversation(cid, sid)
        with db.connect() as conn:
            messages = [dict(r) for r in conn.execute("SELECT id,role,content,created_at,state FROM web_messages "
                                                     "WHERE conversation_id=? ORDER BY id", (cid,))]
            draft = conn.execute("SELECT p.* FROM proposals p WHERE p.conversation_id=? "
                                 "AND NOT EXISTS (SELECT 1 FROM tickets t WHERE t.proposal_id=p.proposal_id) "
                                 "AND NOT EXISTS (SELECT 1 FROM tickets t WHERE t.user_id=p.user_id "
                                 "AND t.order_id=p.order_id AND t.status!='closed') "
                                 "ORDER BY p.created_at DESC,p.rowid DESC LIMIT 1", (conv["dify_id"],)).fetchone()
            proposal = None if not draft else {k: draft[k] for k in ("proposal_id", "order_id", "summary", "expires_at")}
            if proposal:
                proposal["confirmation_phrase"] = "确认创建工单 " + proposal["proposal_id"]
                proposal["expired"] = proposal["expires_at"] <= now()
            rows = conn.execute("SELECT t.* FROM tickets t JOIN proposals p ON p.proposal_id=t.proposal_id "
                                "WHERE p.conversation_id=? ORDER BY t.created_at DESC", (conv["dify_id"],)).fetchall()
            return {"id": cid, "messages": messages, "proposal": proposal,
                    "tickets": [ticket_dict(conn, r) for r in rows]}

    @app.get("/web/tickets")
    def list_user_tickets(sid=Depends(user)):
        with db.connect() as conn:
            rows = conn.execute("SELECT t.* FROM tickets t JOIN proposals p ON p.proposal_id=t.proposal_id "
                                "JOIN web_conversations c ON c.dify_id=p.conversation_id "
                                "WHERE c.session_id=? ORDER BY t.updated_at DESC,t.ticket_id", (sid,)).fetchall()
            return {"tickets": [ticket_dict(conn, r) for r in rows]}

    @app.get("/web/tickets/{tid}")
    def get_user_ticket(tid: str, sid=Depends(user)):
        with db.connect() as conn:
            return {"ticket": user_ticket(conn, tid, sid)}

    @app.post("/web/chat", dependencies=[Depends(same_origin)])
    async def chat(body: ChatBody, sid=Depends(user)):
        if not dify_key:
            raise HTTPException(503, "尚未配置 Dify 服务连接，请联系项目维护者。")
        cid = body.conversation_id or str(uuid4())
        if body.conversation_id:
            conv = conversation(cid, sid)
        else:
            conv = {"dify_id": None}
        if cid in inflight or len(inflight) >= 4:
            raise HTTPException(409, "当前会话正在回复或服务繁忙，请稍后重试。")
        with db.connect(write=True) as conn:
            count = conn.execute("SELECT COUNT(*) FROM web_usage WHERE session_id=? AND occurred_at>?",
                                 (sid, time.time() - 600)).fetchone()[0]
            daily = conn.execute("SELECT COUNT(*) FROM web_usage WHERE occurred_at>?", (time.time() - 86400,)).fetchone()[0]
            if count >= 15 or daily >= 300:
                raise HTTPException(429, "演示服务调用额度已达上限，请稍后重试。")
            conn.execute("DELETE FROM web_usage WHERE occurred_at<?", (time.time() - 86400,))
            conn.execute("INSERT INTO web_usage VALUES (?,?)", (sid, time.time()))
            if not body.conversation_id:
                conn.execute("INSERT INTO web_conversations VALUES (?,?,?,?,?)", (cid, sid, None, body.query[:40], now()))
            conn.execute("INSERT INTO web_messages(conversation_id,role,content,created_at) VALUES (?,'user',?,?)",
                         (cid, body.query, now()))
            msg_id = conn.execute("INSERT INTO web_messages(conversation_id,role,content,created_at,state) "
                                  "VALUES (?,'assistant','',?,'streaming')", (cid, now())).lastrowid
        inflight.add(cid)

        def event(kind, **data):
            return "data: " + json.dumps({"type": kind, **data}, ensure_ascii=False) + "\n\n"

        async def stream():
            answer, complete = "", False
            try:
                yield event("conversation", conversation_id=cid)
                yield event("status", text="正在分析需求并调用工具…")
                async with asyncio.timeout(180):
                    async with httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(120, connect=15)) as client:
                        async with client.stream("POST", dify_base.rstrip("/") + "/chat-messages",
                                                 headers={"Authorization": "Bearer " + dify_key},
                                                 json={"inputs": {}, "query": body.query, "user": "web-" + sid,
                                                       "conversation_id": conv["dify_id"] or "",
                                                       "response_mode": "streaming", "auto_generate_name": False}) as upstream:
                            if upstream.status_code != 200:
                                raise RuntimeError("智能体服务暂时不可用，请稍后重试。")
                            async for line in upstream.aiter_lines():
                                if not line.startswith("data:"):
                                    continue
                                try:
                                    data = json.loads(line[5:].strip())
                                except json.JSONDecodeError:
                                    continue
                                did = data.get("conversation_id")
                                if did:
                                    if conv["dify_id"] and conv["dify_id"] != did:
                                        raise RuntimeError("会话响应不匹配，请刷新后重试。")
                                    if not conv["dify_id"]:
                                        with db.connect(write=True) as conn:
                                            conn.execute("UPDATE web_conversations SET dify_id=? WHERE id=? AND session_id=?",
                                                         (did, cid, sid))
                                        conv["dify_id"] = did
                                kind = data.get("event")
                                if kind == "error":
                                    raise RuntimeError("本轮智能体执行失败，请检查工单状态后再重试。")
                                if kind in {"message", "agent_message"}:
                                    chunk = data.get("answer", "")
                                    answer += chunk
                                    yield event("delta", text=chunk)
                                elif kind == "message_replace":
                                    answer = data.get("answer", "")
                                    yield event("replace", text=answer)
                                elif kind == "message_end":
                                    complete = bool(answer.strip())
                                elif kind == "node_started":
                                    title = data.get("data", {}).get("title", "")
                                    if title:
                                        yield event("status", text="正在执行：" + title[:60])
                            if not complete:
                                raise RuntimeError("回复连接中断，可能已执行工具。请先刷新工单状态，确认后再重试。")
                yield event("done", conversation_id=cid)
            except (httpx.HTTPError, TimeoutError):
                yield event("error", message="连接超时或中断。请先刷新工单状态，避免重复操作。")
            except RuntimeError as exc:
                yield event("error", message=str(exc))
            finally:
                with db.connect(write=True) as conn:
                    conn.execute("UPDATE web_messages SET content=?,state=? WHERE id=?",
                                 (answer, "complete" if complete else "interrupted", msg_id))
                inflight.discard(cid)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/web/operator/login", dependencies=[Depends(same_origin)])
    def login(body: LoginBody, request: Request, response: Response):
        bucket = login_attempts[request.client.host if request.client else "unknown"]
        while bucket and bucket[0] < time.time() - 600:
            bucket.popleft()
        if len(bucket) >= 5:
            raise HTTPException(429, "尝试次数过多，请十分钟后重试。")
        if not operator_password or not secrets.compare_digest(token_hash(body.password), token_hash(operator_password)):
            bucket.append(time.time())
            raise HTTPException(401, "操作员访问口令不正确。")
        old = request.cookies.get("ls_operator", "")
        initialize()
        with db.connect(write=True) as conn:
            conn.execute("DELETE FROM web_sessions WHERE token_hash=? AND role='operator'", (token_hash(old),))
        set_session(response, request, "operator")
        return {"authenticated": True}

    @app.post("/web/operator/logout", dependencies=[Depends(same_origin)])
    def logout(request: Request, response: Response):
        initialize()
        with db.connect(write=True) as conn:
            conn.execute("DELETE FROM web_sessions WHERE token_hash=? AND role='operator'",
                         (token_hash(request.cookies.get("ls_operator", "")),))
        response.delete_cookie("ls_operator", secure=cookie_secure(request), httponly=True, samesite="strict")
        return {"authenticated": False}

    @app.get("/web/operator/tickets")
    def operator_list(status: Literal["all", "open", "processing", "resolved", "closed"] = "all",
                      q: str = "", page: int = 1, sid=Depends(operator)):
        page = max(1, page)
        # Parameterized query; LIKE wildcards are a useful search feature here.
        where, params = " WHERE 1=1", []
        if status != "all":
            where += " AND status=?"
            params.append(status)
        if q:
            where += " AND (ticket_id LIKE ? OR order_id LIKE ? OR summary LIKE ?)"
            params += ["%" + q[:100] + "%"] * 3
        with db.connect() as conn:
            counts = {r[0]: r[1] for r in conn.execute("SELECT status,COUNT(*) FROM tickets GROUP BY status")}
            total = conn.execute("SELECT COUNT(*) FROM tickets" + where, params).fetchone()[0]
            rows = conn.execute("SELECT * FROM tickets" + where + " ORDER BY updated_at DESC,ticket_id LIMIT 20 OFFSET ?",
                                [*params, (page - 1) * 20]).fetchall()
            return {"tickets": [dict(r) for r in rows], "counts": counts, "total": total, "page": page, "page_size": 20}

    @app.get("/web/operator/tickets/{tid}")
    def operator_detail(tid: str, sid=Depends(operator)):
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (tid,)).fetchone()
            if not row:
                raise HTTPException(404, "工单不存在。")
            return {"ticket": ticket_dict(conn, row)}

    @app.patch("/web/operator/tickets/{tid}", dependencies=[Depends(same_origin)])
    def operator_update(tid: str, body: TransitionBody, sid=Depends(operator)):
        return service.transition(tid, body.expected_status, body.status, body.note)

    dist = Path(os.getenv("LOGISUPPLY_WEB_DIST", str(Path(__file__).parents[1] / "web" / "dist")))
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="web-assets")
    if (dist / "index.html").is_file():
        @app.get("/", include_in_schema=False)
        @app.get("/operator", include_in_schema=False)
        @app.get("/tickets", include_in_schema=False)
        def frontend():
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
