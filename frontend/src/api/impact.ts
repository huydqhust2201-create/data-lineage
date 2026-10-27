import { request } from "./http";
import type { ChangeKind, Direction, ImpactQueryResult } from "../types/backend";

/** GET /api/v1/impact/{table} — confirmed/inferred_pending lấy thẳng từ BE, không tự suy luận ở FE.
 * change_kind (tuỳ chọn): "type" (đổi kiểu dữ liệu cột) hoặc "value" (đổi giá trị)
 * — khi có, mỗi cạnh trả về kèm `risk` (rủi ro thật tính theo transform_type). */
export function getImpact(
  table: string,
  direction: Direction,
  databaseId: number,
  column?: string | null,
  changeKind?: ChangeKind | null,
  targetType?: string | null,
): Promise<ImpactQueryResult> {
  const params = new URLSearchParams({ direction, database_id: String(databaseId) });
  if (column) params.set("column", column);
  if (changeKind) params.set("change_kind", changeKind);
  if (targetType) params.set("target_type", targetType);
  return request<ImpactQueryResult>(`/impact/${encodeURIComponent(table)}?${params.toString()}`);
}
