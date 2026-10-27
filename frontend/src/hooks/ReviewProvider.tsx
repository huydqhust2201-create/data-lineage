import { createContext, useContext, type ReactNode } from "react";
import { useReview } from "./useReview";

// Sidebar (badge số lượng pending trên "Lineage Explorer") và
// LineageExplorerPage/EdgeReviewModal (danh sách cạnh + approve/reject khi
// bấm cạnh nét đứt trên đồ thị) phải dùng CHUNG 1 instance useReview() —
// nếu mỗi nơi tự gọi hook riêng, approve/reject sẽ không cập nhật badge
// trên Sidebar (2 state độc lập, không đồng bộ) cho tới khi cả 2 tự refetch.

type ReviewContextValue = ReturnType<typeof useReview>;

const ReviewContext = createContext<ReviewContextValue | null>(null);

export function ReviewProvider({ children }: { children: ReactNode }) {
  const value = useReview();
  return <ReviewContext.Provider value={value}>{children}</ReviewContext.Provider>;
}

export function useReviewContext(): ReviewContextValue {
  const ctx = useContext(ReviewContext);
  if (!ctx) throw new Error("useReviewContext phải dùng bên trong <ReviewProvider>");
  return ctx;
}
