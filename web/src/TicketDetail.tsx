import {
  Check,
  Clock3,
  FileCheck2,
  RefreshCw,
  ArrowRight,
  CornerUpLeft,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "./api";
import { date, labels, transitions } from "./types";
import type { Status, Ticket } from "./types";

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`badge ${status}`}>
      <i />
      {labels[status]}
    </span>
  );
}

export default function TicketDetail({
  ticket,
  operator = false,
  refreshing = false,
  onRefresh,
  onUpdated,
}: {
  ticket: Ticket;
  operator?: boolean;
  refreshing?: boolean;
  onRefresh: () => void;
  onUpdated?: (ticket: Ticket) => void;
}) {
  const [note, setNote] = useState(""),
    [next, setNext] = useState<Status>("processing");
  const [saving, setSaving] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    setNote("");
    setError("");
    setNext(transitions[ticket.status][0] || "processing");
  }, [ticket.ticket_id, ticket.status]);
  async function update(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const result = await api<{ ticket: Ticket }>(
        `/web/operator/tickets/${ticket.ticket_id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_status: ticket.status,
            status: next,
            note: note.trim(),
          }),
        },
      );
      onUpdated?.(result.ticket);
      setNote("");
    } catch (err) {
      setError((err as Error).message);
      onRefresh();
    } finally {
      setSaving(false);
    }
  }
  const stages: Status[] = ["open", "processing", "resolved", "closed"];
  return (
    <section className="ticket-detail" aria-label="工单详情">
      <div className="section-top">
        <span className="eyebrow">TICKET / 工单详情</span>
        <button
          className="icon-button"
          aria-label="刷新工单详情"
          onClick={onRefresh}
          disabled={refreshing || saving}
        >
          <RefreshCw size={16} className={refreshing ? "spin" : ""} />
        </button>
      </div>
      <div className="detail-title">
        <h2>{ticket.order_id}</h2>
        <StatusBadge status={ticket.status} />
      </div>
      <code className="ticket-number">{ticket.ticket_id}</code>
      <p className="ticket-summary">{ticket.summary}</p>
      <div className="progress-steps" aria-label="工单进度">
        {stages.map((stage, i) => (
          <div
            key={stage}
            className={i <= stages.indexOf(ticket.status) ? "reached" : ""}
          >
            <span>
              {i < stages.indexOf(ticket.status) ? <Check size={12} /> : i + 1}
            </span>
            <small>{labels[stage]}</small>
          </div>
        ))}
      </div>
      {ticket.resolution && (
        <div className="resolution">
          <FileCheck2 size={17} />
          <div>
            <strong>处理结果</strong>
            <p>{ticket.resolution}</p>
          </div>
        </div>
      )}
      <div className="section-top timeline-heading">
        <h3>处理时间线</h3>
        <span>{ticket.events?.length ?? 0} 条记录</span>
      </div>
      <ol className="timeline">
        {ticket.events?.map((event, i) => (
          <li key={`${event.occurred_at}-${i}`}>
            <span className="timeline-dot">
              {i === (ticket.events?.length ?? 0) - 1 ? (
                <Clock3 size={12} />
              ) : (
                <Check size={11} />
              )}
            </span>
            <div>
              <div className="event-title">
                <strong>{labels[event.to_status]}</strong>
                <time>{date(event.occurred_at)}</time>
              </div>
              <p>{event.note}</p>
              <small>
                {event.actor.startsWith("user:") ? "用户确认" : "操作员处理"}
              </small>
            </div>
          </li>
        ))}
      </ol>
      {operator && transitions[ticket.status].length > 0 && (
        <form onSubmit={update} className="handling-form">
          <h3>推进处理</h3>
          <p className="muted">提交后记录处理人、时间与备注。</p>
          <label htmlFor="next-status">下一状态</label>
          <select
            id="next-status"
            value={next}
            onChange={(e) => setNext(e.target.value as Status)}
            disabled={saving}
          >
            {transitions[ticket.status].map((status) => (
              <option key={status} value={status}>
                {status === "processing" && ticket.status === "resolved"
                  ? "退回处理中"
                  : labels[status]}
              </option>
            ))}
          </select>
          <label htmlFor="handling-note">
            处理备注 <span>至少 5 个字符</span>
          </label>
          <textarea
            id="handling-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            minLength={5}
            maxLength={2000}
            required
            placeholder="说明核实情况、处理动作或解决结果…"
            disabled={saving}
          />
          {error && (
            <p className="inline-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="primary-button"
            disabled={saving || note.trim().length < 5}
          >
            {next === "processing" && ticket.status === "resolved" ? (
              <CornerUpLeft size={16} />
            ) : (
              <ArrowRight size={16} />
            )}
            {saving ? "正在提交…" : `更新为${labels[next]}`}
          </button>
        </form>
      )}
      {operator && ticket.status === "closed" && (
        <div className="closed-note">
          <Check size={17} />
          工单已归档，处理记录保留。
        </div>
      )}
      <p className="last-sync">
        最后更新于 {date(ticket.updated_at)} · 自动刷新每 5 秒
      </p>
    </section>
  );
}
