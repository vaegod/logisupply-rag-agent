export type Status = "open" | "processing" | "resolved" | "closed";
export type TicketEvent = {
  from_status: Status | null;
  to_status: Status;
  note: string;
  actor: string;
  occurred_at: string;
};
export type Ticket = {
  ticket_id: string;
  order_id: string;
  summary: string;
  status: Status;
  resolution: string;
  created_at: string;
  updated_at: string;
  events?: TicketEvent[];
};
export type Proposal = {
  proposal_id: string;
  order_id: string;
  summary: string;
  expires_at: string;
  confirmation_phrase: string;
  expired: boolean;
};
export type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  state?: string;
};
export type Conversation = { id: string; title: string; created_at: string };
export type ConversationDetail = {
  id: string;
  messages: Message[];
  proposal: Proposal | null;
  tickets: Ticket[];
};
export type Order = {
  order_id: string;
  status: string;
  current_node: string;
  expected_arrival: string;
  exception_type: string;
  product_type: string;
  last_update: string;
};
export type Bootstrap = {
  conversations: Conversation[];
  orders: Order[];
  operator: boolean;
  chat_available: boolean;
  deployment_mode?: "local" | "remote";
  dify_console_url?: string;
  identity_notice: string;
};
export type TicketList = {
  tickets: Ticket[];
  counts: Partial<Record<Status, number>>;
  total: number;
  page: number;
  page_size: number;
};
export const labels: Record<Status, string> = {
  open: "待受理",
  processing: "处理中",
  resolved: "已解决",
  closed: "已关闭",
};
export const transitions: Record<Status, Status[]> = {
  open: ["processing"],
  processing: ["resolved"],
  resolved: ["closed", "processing"],
  closed: [],
};
export function date(value: string) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(parsed);
}
