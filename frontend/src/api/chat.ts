import { request } from "./http";
import type { ChatResponse } from "../types/backend";
import { feedSse } from "../utils/sseParser";

/** POST /api/v1/chat — Lineage Copilot. */
export function askChat(question: string, sessionId: string | null, databaseId: number): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ question, session_id: sessionId, database_id: databaseId }),
  });
}

export async function askChatStream(question: string, databaseId: number, handlers: {
  onStep: (step: ChatResponse["steps"][number]) => void; onThought: (text: string) => void;
  onToken: (text: string) => void; onDone: (data: ChatResponse) => void; onError: (detail: string) => void;
}): Promise<void> {
  const token = localStorage.getItem("data_lineage_token");
  const response = await fetch("/api/v1/chat/stream", { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify({ question, database_id: databaseId }) });
  if (!response.ok || !response.body) throw new Error(await response.text());
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      const parsed = feedSse(buffer, decoder.decode(value, { stream: true })); buffer = parsed.rest;
      for (const event of parsed.events) {
        if (event.event === "step") handlers.onStep(event.data as ChatResponse["steps"][number]);
        if (event.event === "thought") handlers.onThought((event.data as { text: string }).text);
        if (event.event === "token") handlers.onToken((event.data as { text: string }).text);
        if (event.event === "done") { handlers.onDone(event.data as ChatResponse); await reader.cancel(); return; }
        if (event.event === "error") { handlers.onError((event.data as { detail: string }).detail); await reader.cancel(); return; }
      }
    }
  } finally { reader.releaseLock(); }
}
