export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  if (!response.ok) {
    let message = "请求失败，请稍后重试。";
    try {
      const error = await response.json();
      if (typeof error.detail === "string") message = error.detail;
      else if (error.detail?.message) message = error.detail.message;
      else if (response.status === 422)
        message = "输入格式不正确，请检查后重试。";
    } catch {
      /* A proxy may return HTML on failure. */
    }
    throw new ApiError(response.status, message);
  }
  return response.json();
}

export type StreamEvent = {
  type: string;
  text?: string;
  conversation_id?: string;
  message?: string;
};

// Handle split UTF-8 characters, CRLF, multiple data lines, and a trailing frame.
export async function consumeSSE(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: StreamEvent) => void,
) {
  const reader = body.getReader(),
    decoder = new TextDecoder();
  let buffer = "",
    done = false;
  function frame(value: string) {
    const data = value
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) return;
    const event = JSON.parse(data) as StreamEvent;
    onEvent(event);
    if (event.type === "done") done = true;
    if (event.type === "error")
      throw new Error(event.message || "智能体执行失败。");
  }
  try {
    while (true) {
      const next = await reader.read();
      buffer = (
        buffer + decoder.decode(next.value, { stream: !next.done })
      ).replace(/\r\n/g, "\n");
      let index: number;
      while ((index = buffer.indexOf("\n\n")) >= 0) {
        frame(buffer.slice(0, index));
        buffer = buffer.slice(index + 2);
      }
      if (next.done) break;
    }
    if (buffer.trim()) frame(buffer);
    if (!done) throw new Error("回复连接中断，请刷新工单状态后再重试。");
  } finally {
    reader.releaseLock();
  }
}

export async function chat(
  query: string,
  conversation_id: string | null,
  onEvent: (event: StreamEvent) => void,
) {
  const response = await fetch("/web/chat", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, conversation_id }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      typeof error.detail === "string"
        ? error.detail
        : "发送失败，请稍后重试。",
    );
  }
  if (!response.body) throw new Error("浏览器不支持流式回复。");
  await consumeSSE(response.body, onEvent);
}
