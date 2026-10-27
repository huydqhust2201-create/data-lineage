import React from 'react';
import { AlertOctagon, Check, ChevronRight } from 'lucide-react';
import { useBreakingChangeAlerts } from '../hooks/useBreakingChangeAlerts';

interface BreakingChangeAlertsPanelProps {
  onAskCopilot?: (question: string) => void;
}

// Cảnh báo breaking change tự phát hiện lúc ingest (bảng bị DROP/RENAME
// nhưng vẫn còn bảng downstream tham chiếu) — không cần user tự paste DDL
// vào DDL Preview mới biết, xem graph_build_node ở backend.
export const BreakingChangeAlertsPanel: React.FC<BreakingChangeAlertsPanelProps> = ({ onAskCopilot }) => {
  const { alerts, loading, busyId, acknowledge } = useBreakingChangeAlerts();

  if (loading || alerts.length === 0) return null;

  return (
    <div className="bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900 rounded-2xl p-5 shadow-sm">
      <h3 className="font-bold text-sm text-rose-800 dark:text-rose-300 flex items-center gap-2 mb-3">
        <AlertOctagon className="w-4 h-4" />
        <span>Breaking Change tự phát hiện ({alerts.length})</span>
      </h3>
      <div className="space-y-2.5">
        {alerts.map(alert => (
          <div
            key={alert.id}
            className="p-3 rounded-xl bg-white dark:bg-slate-900 border border-rose-100 dark:border-rose-900/60"
          >
            <div className="flex items-center justify-between gap-2 flex-wrap mb-1.5">
              <span className="text-xs font-mono font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                {alert.kind === 'drop' ? (
                  <>Xoá <code className="text-rose-600 dark:text-rose-400">{alert.table_name}</code></>
                ) : (
                  <>
                    Đổi tên <code className="text-rose-600 dark:text-rose-400">{alert.table_name}</code>
                    <ChevronRight className="w-3 h-3" />
                    <code className="text-emerald-600 dark:text-emerald-400">{alert.new_name}</code>
                  </>
                )}
              </span>
              <span className="text-[10px] font-mono text-slate-400">
                {new Date(alert.detected_at).toLocaleString()}
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">{alert.suggested_action}</p>
            <div className="flex items-center gap-2 mt-2.5">
              {onAskCopilot && (
                <button
                  onClick={() =>
                    onAskCopilot(
                      `Bảng '${alert.table_name}' ${alert.kind === 'drop' ? 'đã bị xoá' : `đã đổi tên thành '${alert.new_name}'`} ` +
                      `nhưng vẫn còn ${alert.downstream_tables.length} bảng downstream tham chiếu (${alert.downstream_tables.join(', ')}). ` +
                      `Hãy đề xuất cách xử lý an toàn.`
                    )
                  }
                  className="text-[11px] font-semibold px-2.5 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-950/40 dark:hover:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 cursor-pointer"
                >
                  Hỏi Copilot
                </button>
              )}
              <button
                onClick={() => acknowledge(alert.id)}
                disabled={busyId === alert.id}
                className="text-[11px] font-semibold px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 flex items-center gap-1 cursor-pointer disabled:opacity-50"
              >
                <Check className="w-3 h-3" />
                <span>Đã xử lý</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
