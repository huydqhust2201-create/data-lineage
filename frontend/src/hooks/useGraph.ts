import { useCallback, useEffect, useRef, useState } from "react";
import { clearGraph, getGraph } from "../api/graph";
import { ApiError, selectedDatabaseId } from "../api/http";
import type { GraphResponse } from "../types/backend";

export function useGraph() {
  const [data, setData] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestVersion = useRef(0);

  const reload = useCallback(async () => {
    const version = ++requestVersion.current;
    setLoading(true);
    setError(null);
    try {
      const databaseId = selectedDatabaseId();
      if (!databaseId) {
        if (version === requestVersion.current) setData(null);
        return;
      }
      const graph = await getGraph(databaseId);
      if (version === requestVersion.current) setData(graph);
    } catch (err) {
      if (version === requestVersion.current) setError(err instanceof ApiError ? err.message : "Không kết nối được backend.");
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    window.addEventListener("data-lineage-context-changed", reload);
    return () => window.removeEventListener("data-lineage-context-changed", reload);
  }, [reload]);

  const clear = useCallback(async () => {
    const databaseId = selectedDatabaseId();
    if (!databaseId) return;
    await clearGraph(databaseId);
    await reload();
  }, [reload]);

  return { data, loading, error, reload, clear };
}
