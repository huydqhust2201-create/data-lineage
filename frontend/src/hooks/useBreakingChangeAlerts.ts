import { useCallback, useEffect, useState } from "react";
import { acknowledgeBreakingChangeAlert, listBreakingChangeAlerts, type BreakingChangeAlert } from "../api/breakingChangeAlerts";
import { ApiError, selectedDatabaseId } from "../api/http";

export function useBreakingChangeAlerts() {
  const [alerts, setAlerts] = useState<BreakingChangeAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const reload = useCallback(async () => {
    const databaseId = selectedDatabaseId();
    if (!databaseId) {
      setAlerts([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setAlerts(await listBreakingChangeAlerts(databaseId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không kết nối được backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const acknowledge = useCallback(async (alertId: number) => {
    const databaseId = selectedDatabaseId();
    if (!databaseId) return;
    setBusyId(alertId);
    try {
      await acknowledgeBreakingChangeAlert(databaseId, alertId);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không kết nối được backend.");
    } finally {
      setBusyId(null);
    }
  }, [reload]);

  return { alerts, loading, error, busyId, reload, acknowledge };
}
