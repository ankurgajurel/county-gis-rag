const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ChatRequest {
  message: string;
  session_id?: string | null;
}

export interface StreamCallbacks {
  onSessionId: (sessionId: string) => void;
  onToken: (token: string) => void;
  onDone: () => void;
  onError: (error: Error) => void;
  onReasoningDelta?: (content: string) => void;
  onReasoningDone?: (blocks: { title: string; content: string }[]) => void;
  onToolStatus?: (tools: string[]) => void;
  onToolStatusEnd?: () => void;
  onMapData?: (geojson: GeoJSON.FeatureCollection) => void;
}

export async function streamChat(req: ChatRequest, callbacks: StreamCallbacks) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    callbacks.onError(new Error(`Chat request failed: ${res.status}`));
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks.onError(new Error("No response body"));
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.startsWith("data: ")) continue;

      const data = trimmed.slice(6);

      if (data === "[DONE]") {
        callbacks.onDone();
        return;
      }

      try {
        const parsed = JSON.parse(data);
        if (parsed.session_id) {
          callbacks.onSessionId(parsed.session_id);
        }
        if (parsed.token) {
          callbacks.onToken(parsed.token);
        }
        if (parsed.reasoning_delta !== undefined) {
          callbacks.onReasoningDelta?.(parsed.reasoning_delta);
        }
        if (parsed.reasoning_done) {
          callbacks.onReasoningDone?.(parsed.reasoning_done.blocks);
        }
        if (parsed.tool_status) {
          callbacks.onToolStatus?.(parsed.tool_status.tools);
        }
        if (parsed.tool_status_end) {
          callbacks.onToolStatusEnd?.();
        }
        if (parsed.map_data) {
          callbacks.onMapData?.(parsed.map_data);
        }
        if (parsed.error) {
          callbacks.onError(new Error(parsed.error));
        }
      } catch {
        // skip malformed chunks
      }
    }
  }

  callbacks.onDone();
}

export async function resetChat(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/chat/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: "", session_id: sessionId }),
  });
}
