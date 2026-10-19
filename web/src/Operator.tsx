import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ClipboardCheck,
  Inbox,
  KeyRound,
  LogOut,
  Search,
  ShieldCheck,
} from "lucide-react";
import { api, ApiError } from "./api";
import type { Status, Ticket, TicketList } from "./types";
import { date, labels } from "./types";
import TicketDetail, { StatusBadge } from "./TicketDetail";

export default function Operator({
  authenticated,
  onAuth,
}: {
  authenticated: boolean;
  onAuth: (value: boolean) => void;
}) {
  const [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<Status | "all">("all"),
    [q, setQ] = useState(""),
    [search, setSearch] = useState(""),
    [page, setPage] = useState(1);
  const [list, setList] = useState<TicketList | null>(null),
    [selected, setSelected] = useState<string | null>(null),
    [ticket, setTicket] = useState<Ticket | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const selection = useRef(selected),
    listRequest = useRef(0);
  selection.current = selected;
  const refreshList = useCallback(async () => {
    const requestId = ++listRequest.current;
    try {
      const result = await api<TicketList>(
        `/web/operator/tickets?status=${status}&q=${encodeURIComponent(search)}&page=${page}`,
      );
      if (requestId === listRequest.current) {
        setList(result);
        setError("");
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onAuth(false);
      setError((err as Error).message);
    }
  }, [status, search, page, onAuth]);
  const refreshTicket = useCallback(async () => {
    if (!selected) return;
    setRefreshing(true);
    try {
      const result = await api<{ ticket: Ticket }>(
        `/web/operator/tickets/${selected}`,
      );
      if (selection.current === selected) setTicket(result.ticket);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onAuth(false);
      setError((err as Error).message);
    } finally {
      setRefreshing(false);
    }
  }, [selected, onAuth]);
  useEffect(() => {
    if (authenticated) {
      void refreshList();
      const id = setInterval(() => {
        if (!document.hidden) void refreshList();
      }, 5000);
      return () => clearInterval(id);
    }
  }, [authenticated, refreshList]);
  useEffect(() => {
    if (authenticated && selected) {
      setTicket(null);
      void refreshTicket();
      const id = setInterval(() => {
        if (!document.hidden) void refreshTicket();
      }, 5000);
      return () => clearInterval(id);
    }
  }, [authenticated, selected, refreshTicket]);
  async function login(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api("/web/operator/login", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setPassword("");
      onAuth(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }
  async function logout() {
    try {
      await api("/web/operator/logout", { method: "POST" });
      onAuth(false);
      setList(null);
      setTicket(null);
      setSelected(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }
  if (!authenticated)
    return (
      <div className="login-layout">
        <div className="login-story">
          <span className="eyebrow">OPERATIONS / 运营协作</span>
          <h1>
            让异常有回应，
            <br />
            让处理有记录。
          </h1>
          <p>从受理到关闭，每一步都清晰可追踪。</p>
          <div className="login-flow">
            受理 <ArrowRight size={18} /> 处理 <ArrowRight size={18} /> 解决{" "}
            <ArrowRight size={18} /> 关闭
          </div>
          <ClipboardCheck
            size={140}
            strokeWidth={0.7}
            className="login-illustration"
          />
        </div>
        <form className="login-card" onSubmit={login}>
          <div className="login-icon">
            <KeyRound size={24} />
          </div>
          <h2>操作员登录</h2>
          <p>使用项目维护者提供的访问口令。</p>
          <label htmlFor="operator-password">访问口令</label>
          <input
            id="operator-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            disabled={loading}
            placeholder="输入操作员口令"
          />
          {error && (
            <p role="alert" className="inline-error">
              {error}
            </p>
          )}
          <button className="primary-button" disabled={loading || !password}>
            {loading ? "正在验证…" : "进入处理工作台"}
            <ArrowRight size={17} />
          </button>
          <small>
            <ShieldCheck size={14} />
            仅授权操作员可查看和推进全部工单
          </small>
        </form>
      </div>
    );
  return (
    <div className="operator-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">OPERATIONS CENTER</span>
          <h1>
            工单处理工作台<span className="heading-dot">.</span>
          </h1>
          <p>及时响应每一个异常，记录每一次处理。</p>
        </div>
        <button className="secondary-button" onClick={() => void logout()}>
          <LogOut size={16} />
          退出登录
        </button>
      </header>
      <div className="stat-grid">
        {(["open", "processing", "resolved", "closed"] as Status[]).map(
          (s, i) => (
            <button
              className={`stat-card stat-${s} ${status === s ? "selected" : ""}`}
              key={s}
              onClick={() => {
                setStatus(s);
                setPage(1);
              }}
            >
              <span>
                {labels[s]}
                <span className="stat-index">0{i + 1}</span>
              </span>
              <strong>{list?.counts[s] ?? "—"}</strong>
              <small>
                {
                  [
                    "等待开始受理",
                    "正在跟进核实",
                    "等待确认关闭",
                    "完整记录已归档",
                  ][i]
                }
              </small>
            </button>
          ),
        )}
      </div>
      <div className={`operator-grid ${selected ? "with-detail" : ""}`}>
        <section className="ticket-table-panel">
          <div className="table-toolbar">
            <div className="filter-tabs">
              {(
                ["all", "open", "processing", "resolved", "closed"] as const
              ).map((s) => (
                <button
                  key={s}
                  aria-pressed={status === s}
                  className={status === s ? "active" : ""}
                  onClick={() => {
                    setStatus(s);
                    setPage(1);
                  }}
                >
                  {s === "all" ? "全部工单" : labels[s]}
                </button>
              ))}
            </div>
            <form
              className="search-field"
              onSubmit={(e) => {
                e.preventDefault();
                setSearch(q);
                setPage(1);
              }}
            >
              <Search size={16} />
              <input
                aria-label="搜索工单"
                placeholder="订单号、工单号或摘要"
                value={q}
                maxLength={100}
                onChange={(e) => setQ(e.target.value)}
              />
              <button aria-label="执行搜索">
                <ArrowRight size={16} />
              </button>
            </form>
          </div>
          {error && (
            <p className="inline-error panel-error" role="alert">
              {error}
            </p>
          )}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>订单 / 工单</th>
                  <th>问题摘要</th>
                  <th>当前状态</th>
                  <th>更新时间</th>
                  <th>
                    <span className="sr-only">操作</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list?.tickets.map((t) => (
                  <tr
                    key={t.ticket_id}
                    className={selected === t.ticket_id ? "selected" : ""}
                  >
                    <td>
                      <strong>{t.order_id}</strong>
                      <code>{t.ticket_id}</code>
                    </td>
                    <td className="summary-cell">{t.summary}</td>
                    <td>
                      <StatusBadge status={t.status} />
                    </td>
                    <td className="time-cell">{date(t.updated_at)}</td>
                    <td>
                      <button
                        className="row-action"
                        aria-label={`处理工单 ${t.ticket_id}`}
                        onClick={() => {
                          setTicket(null);
                          setSelected(t.ticket_id);
                        }}
                      >
                        查看
                        <ArrowRight size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {list && list.tickets.length === 0 && (
            <div className="empty-state">
              <Inbox size={38} />
              <h3>没有符合条件的工单</h3>
              <p>试试其他状态，或清空搜索条件。</p>
            </div>
          )}
          {!list && !error && (
            <div className="empty-state">
              <span className="loading-ring" />
              <p>正在读取工单…</p>
            </div>
          )}
          {list && (
            <div className="pagination">
              <span>
                共 {list.total} 张工单 · 第 {page} 页
              </span>
              <div>
                <button
                  className="icon-button"
                  aria-label="上一页"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ArrowLeft size={16} />
                </button>
                <button
                  className="icon-button"
                  aria-label="下一页"
                  disabled={page * list.page_size >= list.total}
                  onClick={() => setPage((p) => p + 1)}
                >
                  <ArrowRight size={16} />
                </button>
              </div>
            </div>
          )}
        </section>
        {selected && (
          <aside className="operator-detail-panel">
            <button
              className="detail-back"
              onClick={() => {
                setSelected(null);
                setTicket(null);
              }}
            >
              <ArrowLeft size={14} />
              返回工单列表
            </button>
            {ticket ? (
              <TicketDetail
                ticket={ticket}
                operator
                refreshing={refreshing}
                onRefresh={() => void refreshTicket()}
                onUpdated={(t) => {
                  setTicket(t);
                  void refreshList();
                }}
              />
            ) : (
              <div className="empty-state">
                <span className="loading-ring" />
                <p>正在读取详情…</p>
              </div>
            )}
          </aside>
        )}
      </div>
      <p className="workspace-footnote">
        <ShieldCheck size={14} />
        演示业务环境 · 状态变更与处理记录同步保存 · 列表每 5 秒刷新
      </p>
    </div>
  );
}
