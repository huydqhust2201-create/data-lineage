import { request } from "./http";
import type { LineageEdge } from "../types/backend";

/** GET /api/v1/pending-review — Review Queue. */
export function listPendingReview(databaseId: number): Promise<LineageEdge[]> {
  return request<LineageEdge[]>(`/pending-review?database_id=${databaseId}`);
}

/** POST /api/v1/pending-review/{edge_id}/confirm — Approve. */
export function confirmPending(edgeId: string, databaseId: number): Promise<LineageEdge> {
  return request<LineageEdge>(`/pending-review/${encodeURIComponent(edgeId)}/confirm?database_id=${databaseId}`, { method: "POST" });
}

/** POST /api/v1/pending-review/{edge_id}/reject — Reject. */
export function rejectPending(edgeId: string, databaseId: number): Promise<void> {
  return request<void>(`/pending-review/${encodeURIComponent(edgeId)}/reject?database_id=${databaseId}`, { method: "POST" });
}
