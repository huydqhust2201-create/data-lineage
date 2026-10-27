import { request } from "./http";
import type { GraphResponse } from "../types/backend";

/** GET /api/v1/graph — graph đã được cắt theo database đang chọn. */
export function getGraph(databaseId: number): Promise<GraphResponse> {
  return request<GraphResponse>(`/graph?database_id=${databaseId}`);
}

/** DELETE /api/v1/graph — xoá toàn bộ đồ thị tích luỹ + hàng đợi HITL (Danger Zone). */
export function clearGraph(databaseId: number): Promise<void> {
  return request<void>(`/graph?database_id=${databaseId}`, { method: "DELETE" });
}
