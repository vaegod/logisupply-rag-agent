import { describe, expect, it } from "vitest";
import { consumeSSE, type StreamEvent } from "../src/api";

function stream(parts: Uint8Array[]) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      parts.forEach((p) => controller.enqueue(p));
      controller.close();
    },
  });
}
describe("chat streaming protocol", () => {
  it("preserves multibyte Chinese across network boundaries and a trailing frame", async () => {
    const bytes = new TextEncoder().encode(
      'data: {"type":"delta","text":"工单"}\r\n\r\ndata: {"type":"done"}',
    );
    const events: StreamEvent[] = [];
    await consumeSSE(stream(Array.from(bytes, (b) => Uint8Array.of(b))), (e) =>
      events.push(e),
    );
    expect(events).toEqual([{ type: "delta", text: "工单" }, { type: "done" }]);
  });
  it("rejects a clean network end without an application completion", async () => {
    await expect(
      consumeSSE(
        stream([
          new TextEncoder().encode(
            'data: {"type":"delta","text":"部分回复"}\n\n',
          ),
        ]),
        () => {},
      ),
    ).rejects.toThrow("连接中断");
  });
  it("surfaces application errors instead of treating them as successful replies", async () => {
    await expect(
      consumeSSE(
        stream([
          new TextEncoder().encode(
            'data: {"type":"error","message":"草稿已过期"}\n\n',
          ),
        ]),
        () => {},
      ),
    ).rejects.toThrow("草稿已过期");
  });
});
