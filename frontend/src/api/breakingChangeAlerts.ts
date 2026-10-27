import { request } from "./http";

export interface BreakingChangeAlert {
  id: number;
  kind: "drop" | "rename";
  table_name: string;
  new_name: string | null;
  downstream_tables: string[];
  suggested_action: string;
  detected_at: string;
  acknowledged: boolean;
}

/** GET /api/v1/breaking-change-alerts — cảnh báo tự phát hiện khi ingest (bảng
 * bị DROP/RENAME nhưng vẫn còn bảng downstream tham chiếu). */
export function listBreakingChangeAlerts(databaseId: number): Promise<BreakingChangeAlert[]> {
  return request<BreakingChangeAlert[]>(`/breaking-change-alerts?database_id=${databaseId}`);
}

export function acknowledgeBreakingChangeAlert(databaseId: number, alertId: number): Promise<void> {
  return request<void>(`/breaking-change-alerts/${alertId}/acknowledge?database_id=${databaseId}`, { method: "POST" });
}
