import type { SSEEvent } from "@/types";

export interface StreamTurnOptions {
  sessionId: string;
  accessToken: string;
  text: string;
  language?: string;
  mode?: "single" | "debate";
  onEvent: (e: SSEEvent) => void;
  signal?: AbortSignal;
}

/**
 * Stream a user turn against the backend SSE endpoint.
 *
 * Note: Browsers' EventSource doesn't support custom headers / POST, so we
 * use fetch + ReadableStream to consume `text/event-stream`.
 */
export async function streamTurn(opts: StreamTurnOptions): Promise<void> {
  const { sessionId, accessToken, text, language = "en", mode = "debate", onEvent, signal } = opts;

  const resp = await fetch(`/api/v1/sessions/${sessionId}/turns`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ text, language, mode }),
    signal,
  });

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`stream failed: ${resp.status} ${body}`);
  }
  if (!resp.body) {
    throw new Error("no response body");
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE messages are separated by blank lines (\n\n)
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const evt = parseSseBlock(block);
      if (evt) onEvent(evt);
    }
  }
}

function parseSseBlock(block: string): SSEEvent | null {
  let event = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice("event:".length).trim();
    else if (line.startsWith("data:")) data = line.slice("data:".length).trim();
  }
  if (!event || !data) return null;
  try {
    const parsed = JSON.parse(data);
    return { event, data: parsed } as SSEEvent;
  } catch {
    return null;
  }
}
