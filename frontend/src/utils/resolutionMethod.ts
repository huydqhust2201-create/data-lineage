// Nhãn tiếng Việt cho `resolution_method` LLM trả về (tín hiệu độ tin cậy dạng
// phân loại, xem src/services/_llm_prompt_v3.txt mục 4). Dùng chung ở drawer
// cạnh (LineageExplorer) và trang HITL Queue (HITLDashboard).
export const RESOLUTION_METHOD_LABELS: Record<string, string> = {
  static: 'SQL tĩnh, tên bảng vật lý tường minh',
  ref_source: 'Qua ref()/source() chuẩn của dbt',
  branch: 'Suy ra từ nhánh Jinja if/else hoặc quy ước đặt tên',
  dynamic: 'Ghép chuỗi / SQL động, chỉ phân giải được một phần',
  macro: 'Qua macro parse được, chưa hoàn toàn tĩnh',
  speculative: 'Mơ hồ cao (loop phức tạp, macro lồng nhau), suy luận yếu',
};

export function resolutionMethodLabel(method: string | undefined | null): string {
  if (!method) return '';
  return RESOLUTION_METHOD_LABELS[method] ?? '';
}
