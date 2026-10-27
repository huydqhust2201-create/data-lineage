import { useCallback, useState } from "react";
import { askChat } from "../api/chat";
import { ApiError, selectedDatabaseId } from "../api/http";
import type { ChatResponse } from "../types/backend";

export interface ChatTurn {
  role: "user" | "assistant" | "system";
  text: string;
  response?: ChatResponse;
  error?: string;
}

export function useChat() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const sendMessage = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed) return;
      setTurns((prev) => [...prev, { role: "user", text: trimmed }]);
      setLoading(true);
      try {
        const databaseId = selectedDatabaseId();
        if (!databaseId) throw new Error("Hãy chọn database trước khi chat.");
        const response = await askChat(trimmed, sessionId, databaseId);
        setSessionId(response.session_id);
        setTurns((prev) => [...prev, { role: "assistant", text: response.answer, response }]);
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Không kết nối được backend.";
        setTurns((prev) => [...prev, { role: "assistant", text: message, error: message }]);
      } finally {
        setLoading(false);
      }
    },
    [sessionId],
  );

  // Tin nhắn hệ thống (vd xác nhận vừa ingest xong gì) — không gọi API, chỉ
  // ghi vào lịch sử hội thoại để người dùng thấy ngay khi mở lại chat.
  const addSystemMessage = useCallback((text: string) => {
    setTurns((prev) => [...prev, { role: "system", text }]);
  }, []);

  return { turns, loading, sendMessage, addSystemMessage };
}
