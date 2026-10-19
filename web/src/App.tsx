import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Box,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  ExternalLink,
  Menu,
  MessageSquare,
  Package,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Truck,
  X,
} from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, chat } from "./api";
import type {
  Bootstrap,
  ConversationDetail,
  Message,
  Order,
  Ticket,
} from "./types";
import { date } from "./types";
import TicketDetail, { StatusBadge } from "./TicketDetail";
import Operator from "./Operator";

type View = "chat" | "tickets" | "operator";
const suggestions = [
  {
    title: "查一查订单",
    text: "查询 JD2026002 的订单状态和物流轨迹。",
    icon: Package,
    desc: "查看当前节点与已知轨迹",
  },
  {
    title: "处理物流异常",
    text: "查询 JD2026003 的温度异常情况，检索处理规范，并帮我准备异常工单。",
    icon: ShieldCheck,
    desc: "核实问题，准备处理工单",
  },
  {
    title: "了解处理规范",
    text: "货物外包装破损应该怎么处理？请检索 SOP 并注明来源。",
    icon: ClipboardList,
    desc: "按 SOP 获取处理建议",
  },
];

function OrderContext({
  orders,
  orderId,
  onChange,
  onAsk,
  disabled,
}: {
  orders: Order[];
  orderId: string;
  onChange: (id: string) => void;
  onAsk: (query: string) => void;
  disabled: boolean;
}) {
  const order = orders.find((o) => o.order_id === orderId);
  return (
    <section className="order-context">
      <div className="section-top">
        <span className="eyebrow">ORDER SNAPSHOT</span>
        <Box size={17} />
      </div>
      <h3>订单上下文</h3>
      <label className="sr-only" htmlFor="demo-order">
        选择演示订单
      </label>
      <select
        id="demo-order"
        value={orderId}
        onChange={(e) => onChange(e.target.value)}
      >
        {orders.map((o) => (
          <option key={o.order_id} value={o.order_id}>
            {o.order_id} · {o.product_type}
          </option>
        ))}
      </select>
      {order && (
        <>
          <div className="order-status">
            <strong>{order.status}</strong>
            <span
              className={
                order.exception_type === "无异常"
                  ? "normal-label"
                  : "exception-label"
              }
            >
              {order.exception_type}
            </span>
          </div>
          <div className="route-sketch">
            <div className="route-point start" />
            <div className="route-line" />
            <Truck size={23} />
            <div className="route-line faded" />
            <div className="route-point end" />
          </div>
          <dl>
            <div>
              <dt>已知节点</dt>
              <dd>{order.current_node}</dd>
            </div>
            <div>
              <dt>历史预计送达</dt>
              <dd>{order.expected_arrival}</dd>
            </div>
            <div>
              <dt>快照时间</dt>
              <dd>{order.last_update}</dd>
            </div>
          </dl>
          <button
            className="context-action"
            disabled={disabled}
            onClick={() =>
              onAsk(`查询 ${order.order_id} 的订单状态和物流轨迹。`)
            }
          >
            让助手查询这笔订单
            <ArrowUpRight size={16} />
          </button>
        </>
      )}
      <p className="snapshot-note">历史演示快照，不代表实时承运商信息。</p>
    </section>
  );
}

function ProposalCard({
  proposal,
  disabled,
  onConfirm,
}: {
  proposal: NonNullable<ConversationDetail["proposal"]>;
  disabled: boolean;
  onConfirm: (query: string) => void;
}) {
  const expired =
    proposal.expired || Date.parse(proposal.expires_at) <= Date.now();
  return (
    <section className="proposal-card" aria-label="待确认工单">
      <div className="proposal-icon">
        <ClipboardList size={22} />
      </div>
      <div className="proposal-content">
        <div className="proposal-heading">
          <h3>工单已准备好，等待你确认</h3>
          <span>{expired ? "草稿已过期" : "待确认"}</span>
        </div>
        <strong>{proposal.order_id}</strong>
        <p>{proposal.summary}</p>
        <small>
          有效期至 {date(proposal.expires_at)} · 点击确认后才会正式建单
        </small>
        <div className="proposal-footer">
          <code>{proposal.proposal_id}</code>
          <button
            className="primary-button"
            disabled={disabled || expired}
            onClick={() => onConfirm(proposal.confirmation_phrase)}
          >
            <Check size={16} />
            {expired ? "请让助手重新准备" : "确认并创建工单"}
          </button>
        </div>
      </div>
    </section>
  );
}

function UserTickets({ onError }: { onError: (message: string) => void }) {
  const [tickets, setTickets] = useState<Ticket[]>([]),
    [selected, setSelected] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false),
    [refreshing, setRefreshing] = useState(false);
  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setTickets((await api<{ tickets: Ticket[] }>("/web/tickets")).tickets);
      setLoaded(true);
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setRefreshing(false);
    }
  }, [onError]);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 5000);
    return () => clearInterval(timer);
  }, [refresh]);
  const ticket = tickets.find((t) => t.ticket_id === selected);
  return (
    <div className="user-ticket-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">YOUR REQUESTS</span>
          <h1>
            每一步进展，都看得见<span className="heading-dot">.</span>
          </h1>
          <p>查看当前浏览器创建的工单与完整处理记录。</p>
        </div>
        <button
          className="secondary-button"
          onClick={() => void refresh()}
          disabled={refreshing}
        >
          <RefreshCw size={16} className={refreshing ? "spin" : ""} />
          刷新进度
        </button>
      </header>
      {!loaded ? (
        <div className="empty-state">
          <span className="loading-ring" />
          <p>正在读取工单…</p>
        </div>
      ) : tickets.length === 0 ? (
        <div className="large-empty">
          <div className="empty-graphic">
            <ClipboardList size={48} strokeWidth={1} />
          </div>
          <h2>还没有需要跟进的工单</h2>
          <p>
            在智能助手中描述问题，确认草稿后，
            <br />
            就可以在这里跟踪处理进度。
          </p>
        </div>
      ) : (
        <div className="user-tickets-grid">
          <div className="user-ticket-list">
            <div className="section-top">
              <h3>我的工单</h3>
              <span>{tickets.length} 张</span>
            </div>
            {tickets.map((t) => (
              <button
                key={t.ticket_id}
                className={`user-ticket-card ${selected === t.ticket_id ? "selected" : ""}`}
                onClick={() => setSelected(t.ticket_id)}
              >
                <div>
                  <strong>{t.order_id}</strong>
                  <StatusBadge status={t.status} />
                </div>
                <p>{t.summary}</p>
                <code>{t.ticket_id}</code>
                <footer>
                  <span>{date(t.updated_at)}</span>
                  <span>
                    查看详情
                    <ChevronRight size={14} />
                  </span>
                </footer>
              </button>
            ))}
          </div>
          <aside className="user-ticket-detail">
            {ticket ? (
              <TicketDetail
                ticket={ticket}
                refreshing={refreshing}
                onRefresh={() => void refresh()}
              />
            ) : (
              <div className="large-empty">
                <ArrowRight size={32} />
                <h3>选择一张工单</h3>
                <p>查看处理时间线与当前进度</p>
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [boot, setBoot] = useState<Bootstrap | null>(null),
    [error, setError] = useState("");
  const [view, setView] = useState<View>(
      location.pathname === "/operator"
        ? "operator"
        : location.pathname === "/tickets"
          ? "tickets"
          : "chat",
    ),
    [navOpen, setNavOpen] = useState(false);
  const [cid, setCid] = useState<string | null>(null),
    [messages, setMessages] = useState<Message[]>([]),
    [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [loadingConversation, setLoadingConversation] = useState(false),
    [activity, setActivity] = useState("");
  const [orderId, setOrderId] = useState("JD2026002"),
    [ticketId, setTicketId] = useState<string | null>(null),
    [ticket, setTicket] = useState<Ticket | null>(null);
  const bottom = useRef<HTMLDivElement>(null),
    current = useRef<string | null>(null),
    busyRef = useRef(false);
  const showError = useCallback((message: string) => setError(message), []);
  const auth = useCallback(
    (operator: boolean) => setBoot((b) => (b ? { ...b, operator } : b)),
    [],
  );
  const loadBootstrap = useCallback(async () => {
    try {
      setBoot(await api<Bootstrap>("/web/bootstrap"));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);
  useEffect(() => {
    void loadBootstrap();
  }, [loadBootstrap]);
  useEffect(() => {
    const pop = () =>
      setView(
        location.pathname === "/operator"
          ? "operator"
          : location.pathname === "/tickets"
            ? "tickets"
            : "chat",
      );
    addEventListener("popstate", pop);
    return () => removeEventListener("popstate", pop);
  }, []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, activity, detail?.proposal]);
  const refreshDetail = useCallback(
    async (id: string, includeMessages = false) => {
      try {
        const result = await api<ConversationDetail>(
          `/web/conversations/${id}`,
        );
        if (current.current !== id) return;
        setDetail(result);
        if (includeMessages) setMessages(result.messages);
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [],
  );
  useEffect(() => {
    if (cid && view === "chat" && !busy) {
      const timer = setInterval(() => {
        if (!document.hidden) void refreshDetail(cid);
      }, 5000);
      return () => clearInterval(timer);
    }
  }, [cid, view, busy, refreshDetail]);
  const refreshTicket = useCallback(async () => {
    if (!ticketId) return;
    try {
      setTicket(
        (await api<{ ticket: Ticket }>(`/web/tickets/${ticketId}`)).ticket,
      );
    } catch (err) {
      setError((err as Error).message);
    }
  }, [ticketId]);
  useEffect(() => {
    if (ticketId) {
      void refreshTicket();
      const timer = setInterval(() => {
        if (!document.hidden) void refreshTicket();
      }, 5000);
      return () => clearInterval(timer);
    }
  }, [ticketId, refreshTicket]);
  function navigate(next: View) {
    if (busyRef.current) return;
    setView(next);
    setNavOpen(false);
    history.pushState(
      {},
      "",
      next === "operator" ? "/operator" : next === "tickets" ? "/tickets" : "/",
    );
    setError("");
  }
  function newChat() {
    if (busyRef.current) return;
    navigate("chat");
    current.current = null;
    setCid(null);
    setMessages([]);
    setDetail(null);
    setInput("");
    setTicketId(null);
    setTicket(null);
  }
  async function selectConversation(id: string) {
    if (busyRef.current) return;
    navigate("chat");
    current.current = id;
    setCid(id);
    setDetail(null);
    setMessages([]);
    setLoadingConversation(true);
    setTicketId(null);
    setTicket(null);
    await refreshDetail(id, true);
    setLoadingConversation(false);
  }
  async function send(query: string) {
    query = query.trim();
    if (!query || busyRef.current || loadingConversation) return;
    const mentioned = boot?.orders.filter((order) =>
      query.toUpperCase().includes(order.order_id),
    );
    if (mentioned?.length === 1) setOrderId(mentioned[0].order_id);
    busyRef.current = true;
    setBusy(true);
    setError("");
    setInput("");
    setActivity("正在连接智能体…");
    setTicketId(null);
    setTicket(null);
    const optimistic = Date.now();
    setMessages((m) => [
      ...m,
      { id: optimistic, role: "user", content: query },
      { id: optimistic + 1, role: "assistant", content: "" },
    ]);
    let active = current.current;
    try {
      await chat(query, active, (event) => {
        if (event.type === "conversation" && event.conversation_id) {
          active = event.conversation_id;
          current.current = active;
          setCid(active);
        }
        if (event.type === "status") setActivity(event.text || "");
        if (event.type === "delta" || event.type === "replace")
          setMessages((m) =>
            m.map((item) =>
              item.id === optimistic + 1
                ? {
                    ...item,
                    content:
                      event.type === "replace"
                        ? event.text || ""
                        : item.content + (event.text || ""),
                  }
                : item,
            ),
          );
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      if (active) await refreshDetail(active, true);
      await loadBootstrap();
      setBusy(false);
      busyRef.current = false;
      setActivity("");
    }
  }
  if (!boot)
    return (
      <div className="boot-screen">
        <div className="brand-mark">
          <Package size={25} />
        </div>
        <h1>LogiSupply</h1>
        {error ? (
          <>
            <p role="alert">{error}</p>
            <button
              className="primary-button"
              onClick={() => void loadBootstrap()}
            >
              重新连接
            </button>
          </>
        ) : (
          <>
            <span className="loading-ring" />
            <p>正在连接物流工作台…</p>
          </>
        )}
      </div>
    );
  return (
    <div className="app-shell">
      {navOpen && (
        <button
          className="nav-scrim"
          aria-label="收起导航"
          onClick={() => setNavOpen(false)}
        />
      )}
      <aside className={`sidebar ${navOpen ? "nav-open" : ""}`}>
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            newChat();
          }}
        >
          <span className="brand-mark">
            <Package size={23} strokeWidth={1.6} />
          </span>
          <span>
            LogiSupply<small>物流协作工作台</small>
          </span>
        </a>
        <div className="workspace-label">
          <span className="workspace-avatar">L</span>
          <div>
            物流演示空间<small>PERSONAL WORKSPACE</small>
          </div>
          <span className="demo-tag">DEMO</span>
        </div>
        <span className="nav-caption">工作空间</span>
        <nav aria-label="主导航">
          <button
            className={view === "chat" ? "active" : ""}
            onClick={() => navigate("chat")}
            disabled={busy}
          >
            <MessageSquare size={18} />
            智能助手
            <span className="nav-active-dot" />
          </button>
          <button
            className={view === "tickets" ? "active" : ""}
            onClick={() => navigate("tickets")}
            disabled={busy}
          >
            <ClipboardList size={18} />
            我的工单
          </button>
          <button
            className={view === "operator" ? "active" : ""}
            onClick={() => navigate("operator")}
            disabled={busy}
          >
            <ShieldCheck size={18} />
            操作员工作台
            <ArrowUpRight size={14} className="nav-end" />
          </button>
        </nav>
        <div className="recent-heading">
          <span className="nav-caption">最近会话</span>
          <button
            aria-label="新建会话"
            className="sidebar-plus"
            onClick={newChat}
            disabled={busy}
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="recent-list">
          {boot.conversations.length === 0 && (
            <p className="no-conversations">从一个物流问题开始</p>
          )}
          {boot.conversations.slice(0, 12).map((c) => (
            <button
              key={c.id}
              className={cid === c.id && view === "chat" ? "selected" : ""}
              disabled={busy}
              onClick={() => void selectConversation(c.id)}
            >
              <MessageSquare size={13} />
              <span>{c.title}</span>
            </button>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="help-note">
            <CircleHelp size={17} />
            <div>
              一个完整的处理闭环<small>查询 · 确认 · 跟进 · 归档</small>
            </div>
          </div>
          <div className="identity">
            <span>访</span>
            <div>
              访客演示会话<small>仅保存在当前浏览器</small>
            </div>
            <span className="identity-dot" />
          </div>
        </div>
      </aside>
      <main className="main-area">
        <div className="topbar">
          <div className="breadcrumb">
            <button
              className="mobile-menu icon-button"
              aria-label="展开导航"
              onClick={() => setNavOpen(true)}
            >
              <Menu size={20} />
            </button>
            <span>工作空间</span>
            <ChevronRight size={13} />
            <strong>
              {view === "operator"
                ? "操作员工作台"
                : view === "tickets"
                  ? "我的工单"
                  : "智能助手"}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="connection">
              <i />
              {boot.chat_available ? "云端已连接" : "聊天待配置"}
            </span>
            <a
              href="https://udify.app/chat/iQSkaDn48xNeqMpK"
              target="_blank"
              rel="noreferrer"
            >
              Dify 原版
              <ExternalLink size={13} />
            </a>
          </div>
        </div>
        <div className="demo-banner">
          <span>演示环境</span>
          订单与物流轨迹为历史快照；工单会实际保存并记录处理进度。
        </div>
        {error && (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button aria-label="关闭提示" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {view === "operator" ? (
          <Operator authenticated={boot.operator} onAuth={auth} />
        ) : view === "tickets" ? (
          <UserTickets onError={showError} />
        ) : (
          <div className="chat-page">
            <div className="chat-heading">
              <div>
                <span className="eyebrow">LOGISTICS COPILOT</span>
                <h1>
                  智能物流助手<span className="heading-dot">.</span>
                </h1>
              </div>
              <button
                className="secondary-button"
                disabled={busy || loadingConversation}
                onClick={newChat}
              >
                <Plus size={16} />
                新对话
              </button>
            </div>
            <div className="chat-layout">
              <section className="chat-panel" aria-label="用户聊天">
                <div className="chat-panel-top">
                  <div className="assistant-avatar">
                    <Sparkles size={17} />
                  </div>
                  <div>
                    <strong>LogiSupply 助手</strong>
                    <small>查询事实，协助处理物流异常</small>
                  </div>
                  <span className="online-dot" />
                </div>
                <div
                  className="message-scroll"
                  aria-live="polite"
                  aria-relevant="additions text"
                >
                  {messages.length === 0 && !loadingConversation && (
                    <div className="chat-welcome">
                      <div className="welcome-symbol">
                        <Package size={37} strokeWidth={1.25} />
                        <span className="welcome-star">✳</span>
                      </div>
                      <span className="eyebrow">从问题到处理</span>
                      <h2>
                        每一次异常，
                        <br />
                        都有下一步。
                      </h2>
                      <p>
                        告诉我订单号和遇到的问题。
                        <br />
                        我会核实已知信息，查找规范，并帮你准备工单。
                      </p>
                      <div className="suggestions">
                        {suggestions.map(
                          ({ title, text, icon: Icon, desc }) => (
                            <button
                              key={title}
                              disabled={busy || !boot.chat_available}
                              onClick={() => void send(text)}
                            >
                              <Icon size={20} strokeWidth={1.5} />
                              <div>
                                <strong>{title}</strong>
                                <small>{desc}</small>
                              </div>
                              <ArrowUpRight size={16} />
                            </button>
                          ),
                        )}
                      </div>
                    </div>
                  )}
                  {loadingConversation && (
                    <div className="empty-state">
                      <span className="loading-ring" />
                      <p>正在恢复对话…</p>
                    </div>
                  )}
                  {messages.map((m) => (
                    <article key={m.id} className={`message ${m.role}`}>
                      <span className="message-avatar">
                        {m.role === "assistant" ? <Sparkles size={15} /> : "我"}
                      </span>
                      <div className="message-main">
                        <span className="message-author">
                          {m.role === "assistant" ? "LogiSupply 助手" : "你"}
                        </span>
                        <div className="message-content">
                          {m.content ? (
                            m.role === "assistant" ? (
                              <Markdown
                                remarkPlugins={[remarkGfm]}
                                components={{
                                  a: (props) => (
                                    <a
                                      {...props}
                                      target="_blank"
                                      rel="noreferrer"
                                    />
                                  ),
                                }}
                              >
                                {m.content}
                              </Markdown>
                            ) : (
                              <p>{m.content}</p>
                            )
                          ) : busy ? (
                            <span className="thinking-dots">
                              <i />
                              <i />
                              <i />
                            </span>
                          ) : (
                            <p className="muted">本轮未收到完整回复。</p>
                          )}
                        </div>
                        {m.state === "interrupted" && (
                          <small className="inline-error">
                            回复中断，请先刷新工单状态。
                          </small>
                        )}
                      </div>
                    </article>
                  ))}
                  {!busy && detail?.proposal && (
                    <ProposalCard
                      proposal={detail.proposal}
                      disabled={!boot.chat_available}
                      onConfirm={(q) => void send(q)}
                    />
                  )}
                  {!busy &&
                    detail?.tickets.map((t) => (
                      <button
                        key={t.ticket_id}
                        className="inline-ticket"
                        onClick={() => {
                          setTicket(t);
                          setTicketId(t.ticket_id);
                        }}
                      >
                        <span className="inline-ticket-icon">
                          <ClipboardList size={20} />
                        </span>
                        <div>
                          <strong>{t.order_id} · 工单已创建</strong>
                          <code>{t.ticket_id}</code>
                        </div>
                        <StatusBadge status={t.status} />
                        <ArrowRight size={17} />
                      </button>
                    ))}
                  <div ref={bottom} />
                </div>
                {busy && (
                  <div className="activity-line" role="status">
                    <span className="loading-ring" />
                    {activity}
                  </div>
                )}
                <form
                  className="composer"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void send(input);
                  }}
                >
                  <label className="sr-only" htmlFor="chat-input">
                    描述你的物流问题
                  </label>
                  <textarea
                    id="chat-input"
                    rows={2}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="输入订单号，或描述你遇到的物流问题…"
                    maxLength={2000}
                    disabled={
                      busy || loadingConversation || !boot.chat_available
                    }
                    onKeyDown={(e) => {
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        !e.nativeEvent.isComposing
                      ) {
                        e.preventDefault();
                        void send(input);
                      }
                    }}
                  />
                  <div className="composer-bottom">
                    <span>
                      <ShieldCheck size={13} />
                      建单前需要你的明确确认
                    </span>
                    <button
                      aria-label="发送消息"
                      type="submit"
                      disabled={
                        busy ||
                        loadingConversation ||
                        !input.trim() ||
                        !boot.chat_available
                      }
                    >
                      <Send size={17} />
                    </button>
                  </div>
                </form>
                <p className="composer-footnote">
                  Enter 发送 · Shift + Enter 换行 · 建议以已知订单事实与 SOP
                  为准
                </p>
              </section>
              <aside className="context-column">
                {ticket ? (
                  <div className="context-ticket">
                    <button
                      className="detail-back"
                      onClick={() => {
                        setTicketId(null);
                        setTicket(null);
                      }}
                    >
                      <ArrowDown size={14} />
                      返回订单信息
                    </button>
                    <TicketDetail
                      ticket={ticket}
                      onRefresh={() => void refreshTicket()}
                    />
                  </div>
                ) : (
                  <>
                    <OrderContext
                      orders={boot.orders}
                      orderId={orderId}
                      onChange={setOrderId}
                      onAsk={(q) => void send(q)}
                      disabled={busy || !boot.chat_available}
                    />
                    <section className="how-it-works">
                      <span className="eyebrow">HOW IT WORKS</span>
                      <h3>有确认，才有下一步</h3>
                      <ol>
                        <li>
                          <span>01</span>
                          <div>
                            <strong>描述问题</strong>
                            <p>助手查询订单与处理规范</p>
                          </div>
                        </li>
                        <li>
                          <span>02</span>
                          <div>
                            <strong>确认工单</strong>
                            <p>核对草稿，再明确确认建单</p>
                          </div>
                        </li>
                        <li>
                          <span>03</span>
                          <div>
                            <strong>跟进处理</strong>
                            <p>操作员推进，进度随时可查</p>
                          </div>
                        </li>
                      </ol>
                      <button onClick={() => navigate("tickets")}>
                        查看我的工单
                        <ArrowRight size={15} />
                      </button>
                    </section>
                  </>
                )}
              </aside>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
