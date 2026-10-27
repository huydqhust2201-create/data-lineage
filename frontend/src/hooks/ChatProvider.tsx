import { createContext, useContext, type ReactNode } from "react";
import { useChat } from "./useChat";

// Chat dùng chung 1 instance toàn app (giống GraphProvider/ReviewProvider)
// — IngestModal cần đẩy 1 tin nhắn hệ thống vào lịch sử chat ngay sau khi
// ingest xong (xác nhận đã đọc file/folder gì), dù IngestModal và ChatPopup
// là 2 popup độc lập, không lồng nhau trong cây component.

type ChatContextValue = ReturnType<typeof useChat>;

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const value = useChat();
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChatContext(): ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatContext phải dùng bên trong <ChatProvider>");
  return ctx;
}
