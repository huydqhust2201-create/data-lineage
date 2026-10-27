import { useCallback, useEffect, useState } from "react";
import { getStatus } from "../api/status";
import { ApiError } from "../api/http";
import type { StatusResponse } from "../types/backend";

export function useStatus() {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getStatus());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không kết nối được backend.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, loading, error, reload };
}
