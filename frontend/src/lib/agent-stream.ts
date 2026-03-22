import type { AgentStreamEvent } from "./api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export function connectAgentStream(
  campaignId: string,
  onEvent: (event: AgentStreamEvent) => void,
  onError?: (error: Event) => void
): () => void {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : "";
  const url = `${API_BASE}/api/v1/campaigns/${campaignId}/stream?token=${token}`;

  const source = new EventSource(url);

  source.onmessage = (e) => {
    try {
      const event: AgentStreamEvent = JSON.parse(e.data);
      onEvent(event);

      if (event.type === "complete" || event.type === "error") {
        source.close();
      }
    } catch {
      // Ignore parse errors for heartbeats
    }
  };

  source.onerror = (e) => {
    onError?.(e);
    source.close();
  };

  return () => source.close();
}
