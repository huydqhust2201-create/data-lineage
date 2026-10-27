import { useCallback, useState } from "react";
import { ingest, ingestUpload } from "../api/ingest";
import { ApiError, selectedDatabaseId } from "../api/http";
import type { IngestResponse } from "../types/backend";

export function useIngest() {
  const [result, setResult] = useState<IngestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Trả thẳng IngestResponse (thay vì chỉ boolean) — caller cần đọc kết quả
  // NGAY sau khi await, không thể chờ re-render rồi đọc `result` từ closure
  // cũ (React state không cập nhật đồng bộ trong cùng 1 lần gọi hàm).
  const runPath = useCallback(
    async (inputPath: string, dialect?: string | null): Promise<IngestResponse | null> => {
      setLoading(true);
      setError(null);
      try {
        const databaseId = selectedDatabaseId();
        if (!databaseId) throw new Error("Hãy chọn database trước khi ingest.");
        const response = await ingest(inputPath, databaseId, dialect);
        setResult(response);
        return response;
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Không kết nối được backend.");
        return null;
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const runUpload = useCallback(async (files: File[]): Promise<IngestResponse | null> => {
    setLoading(true);
    setError(null);
    try {
      const databaseId = selectedDatabaseId();
      if (!databaseId) throw new Error("Hãy chọn database trước khi ingest.");
      const response = await ingestUpload(files, databaseId);
      setResult(response);
      return response;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không kết nối được backend.");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return { result, loading, error, runPath, runUpload, reset };
}
