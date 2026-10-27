import type { ChatStep } from "../types/backend";

function resultLabel(step: ChatStep): string {
  const match = /^(\d+) confirmed, (\d+) pending$/.exec(step.summary);
  if (!match) return step.summary || "đã hoàn tất";

  const confirmed = Number(match[1]);
  const pending = Number(match[2]);
  if (confirmed === 0 && pending === 0) {
    return step.tool === "breaking_changes" ? "không có cảnh báo nào" : "không thấy quan hệ nào";
  }

  const parts = [`${confirmed} quan hệ đã xác nhận`];
  if (pending > 0) parts.push(`${pending} chưa duyệt`);
  return parts.join(", ");
}

export function stepLabel(step: ChatStep): string {
  if (step.error) return `Không hoàn tất: ${step.error}`;
  const result = resultLabel(step);
  if (step.tool === "traverse") return `Truy ${step.args.direction} của ${step.args.table}${step.args.column ? `.${step.args.column}` : ""} → ${result}.`;
  if (step.tool === "assess_change") return `Đánh giá ảnh hưởng khi sửa ${step.args.table}${step.args.column ? `.${step.args.column}` : ""} → ${result}.`;
  if (step.tool === "breaking_changes") return `Kiểm cảnh báo đổi tên/xoá cho ${step.args.tables ?? step.args.table ?? "các bảng"} → ${result}.`;
  if (step.tool === "search_tables") return `Tìm bảng khớp "${step.args.query}" → ${result}.`;
  return `Chạy ${step.tool} → ${result}.`;
}
