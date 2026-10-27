import { createContext, useContext, type ReactNode } from "react";
import { useGraph } from "./useGraph";

// Đồ thị confirmed (GET /graph) dùng chung 1 instance toàn app, giống
// ReviewProvider — lý do: IngestModal giờ là popup mở từ bất kỳ trang nào
// (kể cả đang đứng ở Lineage Explorer), ingest xong phải đẩy dữ liệu mới
// vào ngay chỗ đang xem chứ không đợi người dùng tự bấm "Tải lại" hay rời
// trang rồi quay lại (trước đây mỗi trang tự gọi useGraph() riêng nên
// không có ai báo cho ai biết vừa có dữ liệu mới).

type GraphContextValue = ReturnType<typeof useGraph>;

const GraphContext = createContext<GraphContextValue | null>(null);

export function GraphProvider({ children }: { children: ReactNode }) {
  const value = useGraph();
  return <GraphContext.Provider value={value}>{children}</GraphContext.Provider>;
}

export function useGraphContext(): GraphContextValue {
  const ctx = useContext(GraphContext);
  if (!ctx) throw new Error("useGraphContext phải dùng bên trong <GraphProvider>");
  return ctx;
}
