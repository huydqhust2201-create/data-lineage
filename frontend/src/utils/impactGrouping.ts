import type { ImpactEdgeView } from '../types/backend';

// Nhãn vai trò cột cho control lineage — cột nguồn không mang dữ liệu vào bảng
// đích nhưng quyết định HÀNG NÀO xuất hiện.
export const ROLE_LABEL: Record<string, string> = {
  filter: 'CỘT LỌC (WHERE/HAVING)',
  join_key: 'KHOÁ JOIN (ON/USING)',
  group_key: 'GROUP BY',
  window_partition: 'PARTITION BY',
  window_order: 'ORDER BY',
};

// Thứ tự hiển thị trong 1 quan hệ: data lineage (output) trước, rồi control.
export function roleRank(e: Pick<ImpactEdgeView, 'dependency_kind'>): number {
  const order: Record<string, number> = {
    output: 0, join_key: 1, group_key: 2, filter: 3, window_partition: 4, window_order: 5,
  };
  return order[e.dependency_kind] ?? 9;
}

// Bỏ câu dẫn schema (giống nhau ở mọi dòng của 1 nhóm) khỏi `risk` để mỗi dòng
// chỉ còn phần riêng. BE nối bằng " — " (em dash). Không khớp -> trả nguyên
// `risk` (degrade an toàn, không mất chữ).
export function stripSchemaNote(risk: string | null, schemaNote: string | null | undefined): string | null {
  if (!risk) return risk;
  const sep = ' — ';
  if (schemaNote && risk.startsWith(schemaNote + sep)) return risk.slice(schemaNote.length + sep.length);
  return risk;
}
