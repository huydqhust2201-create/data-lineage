import { request, requestMultipart } from "./http";
import type { IngestResponse, IngestRun } from "../types/backend";

/** POST /api/v1/ingest — tab "Paste SQL" (path server) hoặc nội dung đã ghi tạm.
 */
export function ingest(
  input_path: string,
  database_id: number,
  dialect?: string | null,
): Promise<IngestResponse> {
  return request<IngestResponse>("/ingest", {
    method: "POST",
    body: JSON.stringify({ input_path, database_id, dialect: dialect ?? null }),
  });
}

/** POST /api/v1/ingest/upload — tab "Upload File", multipart trực tiếp từ máy user.
 * KHÔNG dùng request() vì multipart cần trình duyệt tự set Content-Type kèm
 * boundary — set thủ công "application/json" như request() sẽ làm hỏng body.
 */
export async function ingestUpload(files: File[], databaseId: number): Promise<IngestResponse> {
  const form = new FormData();
  const stamps: Record<string, number> = {};
  for (const f of files) {
    const relPath = (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
    form.append("files", f, relPath);
    stamps[relPath] = f.lastModified;
  }
  form.append("last_modified", JSON.stringify(stamps));
  form.append("database_id", String(databaseId));
  return requestMultipart<IngestResponse>("/ingest/upload", form);
}

/** GET /api/v1/ingest-runs — lịch sử ingest của 1 database, mới nhất trước —
 * để user xem lại đã ingest gì, từ path nào, khi nào (1 project có thể
 * ingest nhiều lần từ nhiều thư mục khác nhau). */
export function listIngestRuns(databaseId: number): Promise<IngestRun[]> {
  return request<IngestRun[]>(`/ingest-runs?database_id=${databaseId}`);
}
