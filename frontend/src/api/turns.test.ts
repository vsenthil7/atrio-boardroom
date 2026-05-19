import { describe, expect, it, vi } from "vitest";
import { streamTurn } from "@/api/turns";
import type { SSEEvent } from "@/types";

function makeResponse(body: string): Response {
  const enc = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(enc.encode(body));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
}

describe("streamTurn", () => {
  it("parses event blocks and dispatches them in order", async () => {
    const body =
      'event: turn_started\ndata: {"session_id":"s","seq_no":1,"user_text":"hi"}\n\n' +
      'event: agent_done\ndata: {"agent_id":"cfo","text":"x","model_used":"m","was_fallback":false,"tokens_in":1,"tokens_out":1,"latency_ms":1,"stance":"support","dissent_round":null}\n\n' +
      'event: consensus\ndata: {"text":"yes","kind":"unanimous","action_list":[]}\n\n' +
      'event: stream_complete\ndata: {"positions":[],"dissent_rounds":0}\n\n';

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(makeResponse(body)));

    const events: SSEEvent[] = [];
    await streamTurn({
      sessionId: "s",
      accessToken: "t",
      text: "hi",
      onEvent: (e) => events.push(e),
    });

    expect(events.map((e) => e.event)).toEqual([
      "turn_started",
      "agent_done",
      "consensus",
      "stream_complete",
    ]);
  });

  it("throws on non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("nope", { status: 500 })),
    );
    await expect(
      streamTurn({
        sessionId: "s",
        accessToken: "t",
        text: "hi",
        onEvent: () => undefined,
      }),
    ).rejects.toThrow(/stream failed: 500/);
  });

  it("ignores malformed SSE blocks", async () => {
    const body =
      "this is not a valid event\n\n" +
      'event: agent_done\ndata: {"agent_id":"cfo","text":"ok","model_used":"m","was_fallback":false,"tokens_in":1,"tokens_out":1,"latency_ms":1,"stance":"support","dissent_round":null}\n\n';
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(makeResponse(body)));
    const events: SSEEvent[] = [];
    await streamTurn({
      sessionId: "s",
      accessToken: "t",
      text: "hi",
      onEvent: (e) => events.push(e),
    });
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("agent_done");
  });
});
