import { useCallback, useEffect, useState } from "react";
import { confirmPending, listPendingReview, rejectPending } from "../api/review";
import { ApiError, selectedDatabaseId } from "../api/http";
import type { LineageEdge } from "../types/backend";

/** Review Queue (HITL). `onSettled` chạy sau approve/reject — page dùng để
 * refetch Graph cùng lúc (item chuyển pending -> confirmed phải cập nhật cả 2 nơi). */
export function useReview(onSettled?: () => void) {
  const [pending, setPending] = useState<LineageEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyEdgeId, setBusyEdgeId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const databaseId = selectedDatabaseId();
      setPending(databaseId ? await listPendingReview(databaseId) : []);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không kết nối được backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    window.addEventListener("data-lineage-context-changed", reload);
    return () => window.removeEventListener("data-lineage-context-changed", reload);
  }, [reload]);

  const approve = useCallback(
    async (edgeId: string) => {
      setBusyEdgeId(edgeId);
      try {
        const databaseId = selectedDatabaseId();
        if (!databaseId) throw new Error("Hãy chọn database trước khi duyệt.");
        await confirmPending(edgeId, databaseId);
        await reload();
        onSettled?.();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Không kết nối được backend.");
      } finally {
        setBusyEdgeId(null);
      }
    },
    [reload, onSettled],
  );

  const reject = useCallback(
    async (edgeId: string) => {
      setBusyEdgeId(edgeId);
      try {
        const databaseId = selectedDatabaseId();
        if (!databaseId) throw new Error("Hãy chọn database trước khi duyệt.");
        await rejectPending(edgeId, databaseId);
        await reload();
        onSettled?.();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Không kết nối được backend.");
      } finally {
        setBusyEdgeId(null);
      }
    },
    [reload, onSettled],
  );

  return { pending, loading, error, reload, approve, reject, busyEdgeId };
}
