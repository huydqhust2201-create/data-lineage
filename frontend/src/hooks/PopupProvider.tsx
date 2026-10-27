import { createContext, useContext, useState, type ReactNode } from "react";

/** Analyze Data và AI Assistant từng là trang riêng trong Sidebar — chuyển
 * tab liên tục khiến người dùng mất tập trung khỏi đồ thị lineage đang
 * xem. Chuyển 2 tính năng này thành popup mở từ icon (TopBar/Sidebar),
 * điều khiển tập trung ở đây để mở được từ bất kỳ trang nào. */
interface PopupContextValue {
  ingestOpen: boolean;
  openIngest: () => void;
  closeIngest: () => void;
  chatOpen: boolean;
  openChat: () => void;
  closeChat: () => void;
}

const PopupContext = createContext<PopupContextValue | null>(null);

export function PopupProvider({ children }: { children: ReactNode }) {
  const [ingestOpen, setIngestOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <PopupContext.Provider
      value={{
        ingestOpen,
        openIngest: () => setIngestOpen(true),
        closeIngest: () => setIngestOpen(false),
        chatOpen,
        openChat: () => setChatOpen(true),
        closeChat: () => setChatOpen(false),
      }}
    >
      {children}
    </PopupContext.Provider>
  );
}

export function usePopups() {
  const ctx = useContext(PopupContext);
  if (!ctx) throw new Error("usePopups() phải nằm trong <PopupProvider>");
  return ctx;
}
