import { useCallback, useState } from "react";
import { getImpact } from "../api/impact";
import { ApiError, selectedDatabaseId } from "../api/http";
import type { ChangeKind, Direction, ImpactQueryResult } from "../types/backend";

export function useImpact() {
  const [result, setResult] = useState<ImpactQueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useCallback(
    async (
      table: string,
      direction: Direction,
      column?: string | null,
      changeKind?: ChangeKind | null,
      targetType?: string | null,
    ) => {
      setLoading(true);
      setError(null);
      try {
        const databaseId = selectedDatabaseId();
        if (!databaseId) throw new Error("Hãy chọn database trước khi phân tích.");
        setResult(await getImpact(table, direction, databaseId, column, changeKind, targetType));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Không kết nối được backend.");
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  return { result, loading, error, query };
}
