import React, { useState } from 'react';
import { HITLQueueItem, LineageEdgeData } from '../types/lineage';
import { RESOLUTION_METHOD_LABELS } from '../utils/resolutionMethod';
import confetti from 'canvas-confetti';
import { 
  ShieldCheck, 
  AlertCircle, 
  CheckCircle2, 
  XCircle, 
  Edit3, 
  FileCode2, 
  ArrowRight, 
  Bot, 
  HelpCircle, 
  Sparkles, 
  RefreshCw,
  Layers,
  Code,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

interface HITLDashboardProps {
  queue: HITLQueueItem[];
  onConfirmEdge: (item: HITLQueueItem) => void;
  onRejectEdge: (item: HITLQueueItem) => void;
  onEditAndConfirmEdge: (item: HITLQueueItem, updatedMappings: { sourceCol: string; targetCol: string }[]) => void;
  onBatchConfirmAll: () => void;
  canReview?: boolean;
}

export const HITLDashboard: React.FC<HITLDashboardProps> = ({
  queue,
  onConfirmEdge,
  onRejectEdge,
  onEditAndConfirmEdge,
  onBatchConfirmAll,
  canReview = true,
}) => {
  const [editingItem, setEditingItem] = useState<HITLQueueItem | null>(null);
  const [editedMappings, setEditedMappings] = useState<{ sourceCol: string; targetCol: string }[]>([]);
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({});

  const toggleExpandItem = (id: string) => {
    setExpandedItems(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const pendingItems = queue.filter(item => item.status === 'pending');
  const reviewedItems = queue.filter(item => item.status !== 'pending');

  const handleConfirm = (item: HITLQueueItem) => {
    onConfirmEdge(item);
    if (pendingItems.length === 1) {
      confetti({
        particleCount: 80,
        spread: 60,
        origin: { y: 0.6 }
      });
    }
  };

  const openEditModal = (item: HITLQueueItem) => {
    setEditingItem(item);
    setEditedMappings([...item.suggestedColumnMappings]);
  };

  return (
    <div className="w-full max-w-7xl mx-auto p-4 sm:p-6 space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-indigo-50 via-slate-50 to-indigo-50 dark:from-slate-900 dark:via-indigo-950 dark:to-slate-900 border border-indigo-100 dark:border-slate-800 rounded-3xl p-6 sm:p-8 text-slate-900 dark:text-white shadow-xl flex flex-col lg:flex-row lg:items-center justify-between gap-6 transition-all duration-300">
        <div className="space-y-2 max-w-3xl">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-orange-100 dark:bg-orange-500/20 text-orange-650 dark:text-orange-400 border border-orange-200 dark:border-orange-500/30">
              <ShieldCheck className="w-5 h-5" />
            </span>
            <span className="text-[11px] font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wider">
              Governance Hub &bull; HITL Queue
            </span>
          </div>
          
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Human-in-the-Loop Verification
          </h1>
          
          <p className="text-xs sm:text-sm text-slate-650 dark:text-slate-300 leading-relaxed font-medium">
            Phê duyệt liên kết dữ liệu do AI suy luận trước khi tích hợp vào sơ đồ chính.
          </p>
        </div>

        {canReview && pendingItems.length > 0 && (
          <button
            id="batch-confirm-all-btn"
            onClick={() => {
              onBatchConfirmAll();
              confetti({ particleCount: 100, spread: 70 });
            }}
            className="flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-755 text-white rounded-xl text-xs font-semibold shadow-lg shadow-indigo-900/20 transition-all cursor-pointer whitespace-nowrap"
          >
            <CheckCircle2 className="w-4 h-4" />
            <span>Approve All ({pendingItems.length})</span>
          </button>
        )}
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Card 1: Pending */}
        <div className="bg-slate-50 dark:bg-slate-900 p-5 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm transition-all hover:shadow-md hover:scale-[1.02] group">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-bold tracking-tight uppercase truncate">
              Pending Approval
            </span>
          </div>
          <div className="text-2xl font-extrabold text-orange-600 dark:text-orange-400">
            {pendingItems.length}
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 line-clamp-2 leading-tight">
            Liên kết đang chờ xử lý
          </div>
        </div>

        {/* Card 2: Confirmed */}
        <div className="bg-slate-50 dark:bg-slate-900 p-5 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm transition-all hover:shadow-md hover:scale-[1.02] group">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-bold tracking-tight uppercase truncate">
              Approved
            </span>
          </div>
          <div className="text-2xl font-extrabold text-indigo-600 dark:text-indigo-400">
            {queue.filter(q => q.status === 'confirmed' || q.status === 'edited').length}
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 line-clamp-2 leading-tight">
            Liên kết đã lưu vào sơ đồ
          </div>
        </div>

        {/* Card 3: Rejected */}
        <div className="bg-slate-50 dark:bg-slate-900 p-5 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm transition-all hover:shadow-md hover:scale-[1.02] group">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-[11px] font-bold tracking-tight uppercase truncate">
              Rejected
            </span>
          </div>
          <div className="text-2xl font-extrabold text-rose-600 dark:text-rose-400">
            {queue.filter(q => q.status === 'rejected').length}
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 line-clamp-2 leading-tight">
            Gợi ý bị từ chối
          </div>
        </div>
      </div>

      {/* Main Review Cards */}
      <div className="space-y-6">
        {pendingItems.length === 0 ? (
          <div className="bg-slate-50 dark:bg-slate-900 p-12 rounded-3xl border border-slate-200 dark:border-slate-800 text-center shadow-sm">
            <CheckCircle2 className="w-12 h-12 text-purple-500 mx-auto mb-3" />
            <h3 className="text-base font-bold text-slate-900 dark:text-white font-mono">
              Review Queue is Empty!
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-md mx-auto">
              Không còn liên kết nào cần phê duyệt.
            </p>
          </div>
        ) : (
          pendingItems.map((item) => (
            <div
              key={item.id}
              id={`hitl-item-${item.id}`}
              className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-md transition-all space-y-4"
            >
              {/* Item Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100 dark:border-slate-800">
                <div className="flex items-center gap-2.5">
                  <div className="flex items-center gap-1.5 font-mono text-sm font-bold text-slate-900 dark:text-white">
                    <span className="text-slate-500 dark:text-slate-400">[{item.sourceSchema}]</span>
                    <span>{item.sourceTable}</span>
                    <ArrowRight className="w-4 h-4 text-indigo-500" />
                    <span className="text-slate-500 dark:text-slate-400">[{item.targetSchema}]</span>
                    <span className="text-indigo-600 dark:text-indigo-400">{item.targetTable}</span>
                  </div>
                </div>

                {/* Confidence + Resolution Method Badges */}
                {canReview && <div className="flex items-center gap-2 flex-wrap">
                  {item.resolutionMethod && (
                    <div
                      className="flex items-center gap-1 px-2.5 py-1 rounded-full font-mono text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700"
                      title={RESOLUTION_METHOD_LABELS[item.resolutionMethod] ?? ''}
                    >
                      {item.resolutionMethod}
                    </div>
                  )}
                  <span className="text-[11px] font-mono text-slate-400">Confidence:</span>
                  <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full font-mono text-xs font-bold bg-orange-100 dark:bg-orange-950/80 text-orange-850 dark:text-orange-300 border border-orange-200 dark:border-orange-800">
                    <Bot className="w-3.5 h-3.5" />
                    {(item.confidence * 100).toFixed(0)}% (Chờ duyệt)
                  </div>
                </div>}
              </div>

              {/* Complex details hidden inside Xem chi tiết */}
              {expandedItems[item.id] && (
                <div className="space-y-4 animate-slideDown">
                  {/* Reason & Detected Root Issue */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                    <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800">
                      <span className="text-slate-400 block text-[10px] font-mono uppercase mb-0.5">
                        Detected Issue
                      </span>
                      <span className="font-semibold text-orange-600 dark:text-orange-400 uppercase font-mono">
                        {item.detectedIssue.replace('_', ' ')}
                      </span>
                    </div>
                    <div className="md:col-span-2 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 space-y-1.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-slate-400 text-[10px] font-mono uppercase">
                          AI Inference Reasoning
                        </span>
                        {item.resolutionMethod && (
                          <span
                            className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-[10px] font-mono text-slate-600 dark:text-slate-300"
                            title={RESOLUTION_METHOD_LABELS[item.resolutionMethod] ?? ''}
                          >
                            {item.resolutionMethod}
                          </span>
                        )}
                      </div>
                      <span className="text-slate-705 dark:text-slate-300 font-sans leading-relaxed block">
                        {item.reason}
                      </span>
                      {item.reasonDetail && (
                        <p className="text-[11px] text-slate-500 dark:text-slate-400 font-sans leading-relaxed bg-white dark:bg-slate-900/50 p-2 rounded-lg border border-slate-100 dark:border-slate-800">
                          {item.reasonDetail}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Suggested Column Mappings */}
                  {item.suggestedColumnMappings && item.suggestedColumnMappings.length > 0 && (
                    <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-150 dark:border-slate-800 space-y-1">
                      <span className="text-slate-400 block text-[10px] font-mono uppercase mb-0.5">
                        Suggested Column Mappings
                      </span>
                      <div className="flex flex-wrap gap-2 pt-1">
                        {item.suggestedColumnMappings.map((colMap, idx) => (
                          <span key={idx} className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-[11px] font-mono text-indigo-600 dark:text-indigo-400">
                            {colMap.sourceCol} &rarr; {colMap.targetCol}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Problematic SQL / Code Snippet */}
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
                      <span className="flex items-center gap-1">
                        <FileCode2 className="w-3.5 h-3.5 text-indigo-400" />
                        {item.filePath}
                      </span>
                    </div>
                    <pre className="p-3 bg-slate-900 text-slate-200 rounded-xl text-[11px] font-mono overflow-x-auto border border-slate-800 leading-relaxed">
                      {item.sqlSnippet}
                    </pre>
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                <div className="text-[11px] text-slate-400 font-mono">
                  Created at: {item.timestamp}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => toggleExpandItem(item.id)}
                    className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-semibold flex items-center gap-1.5 cursor-pointer transition-colors"
                  >
                    {expandedItems[item.id] ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    <span>{expandedItems[item.id] ? 'Collapse' : 'Details'}</span>
                  </button>

                  <button
                    id={`edit-edge-${item.id}`}
                    onClick={() => openEditModal(item)}
                    className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-semibold flex items-center gap-1.5 cursor-pointer transition-colors"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                    <span>Edit Mapping</span>
                  </button>

                  <button
                    id={`reject-edge-${item.id}`}
                    onClick={() => onRejectEdge(item)}
                    className="px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-rose-900/20 cursor-pointer transition-colors"
                  >
                    <XCircle className="w-3.5 h-3.5" />
                    <span>Reject</span>
                  </button>

                  <button
                    id={`confirm-edge-${item.id}`}
                    onClick={() => handleConfirm(item)}
                    className="px-4 py-1.5 rounded-xl bg-[#4338ca] hover:bg-[#3730a3] text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-indigo-900/20 cursor-pointer transition-colors"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Approve</span>
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Edit Mapping Modal */}
      {editingItem && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 max-w-lg w-full rounded-3xl border border-slate-200 dark:border-slate-800 shadow-2xl p-6 space-y-4">
            <h3 className="text-base font-bold font-mono text-slate-900 dark:text-white">
              Edit Column Mappings
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Chỉnh sửa liên kết giữa các trường của hai bảng.
            </p>

            <div className="space-y-2 max-h-56 overflow-y-auto">
              {editedMappings.map((map, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={map.sourceCol}
                    onChange={(e) => {
                      const updated = [...editedMappings];
                      updated[idx].sourceCol = e.target.value;
                      setEditedMappings(updated);
                    }}
                    placeholder="Source Column"
                    className="flex-1 px-3 py-1.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg font-mono text-slate-900 dark:text-white"
                  />
                  <ArrowRight className="w-4 h-4 text-slate-400 shrink-0" />
                  <input
                    type="text"
                    value={map.targetCol}
                    onChange={(e) => {
                      const updated = [...editedMappings];
                      updated[idx].targetCol = e.target.value;
                      setEditedMappings(updated);
                    }}
                    placeholder="Target Column"
                    className="flex-1 px-3 py-1.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg font-mono text-slate-900 dark:text-white"
                  />
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
              <button
                onClick={() => setEditingItem(null)}
                className="px-3.5 py-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 rounded-lg cursor-pointer transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  onEditAndConfirmEdge(editingItem, editedMappings);
                  setEditingItem(null);
                  confetti({ particleCount: 60 });
                }}
                className="px-4 py-1.5 text-xs font-semibold bg-[#4338ca] hover:bg-[#3730a3] text-white rounded-lg cursor-pointer shadow-md shadow-indigo-600/20"
              >
                Save &amp; Approve
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Lịch sử Duyệt & Audit Logs */}
      {reviewedItems.length > 0 && (
        <div className="bg-slate-50 dark:bg-slate-900 p-5 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
            <h3 className="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-orange-500" />
              <span>Verification History ({reviewedItems.length})</span>
            </h3>
          </div>
          
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {reviewedItems.map((item) => (
              <div 
                key={item.id} 
                className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-150 dark:border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono text-left"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                      item.status === 'confirmed' ? 'bg-purple-950 text-purple-300 border border-purple-800/40' :
                      item.status === 'edited' ? 'bg-indigo-950 text-indigo-300 border border-indigo-800/40' :
                      'bg-rose-955/60 text-rose-350 border border-rose-955/40'
                    }`}>
                      {item.status === 'confirmed' ? 'APPROVED' : item.status === 'edited' ? 'EDITED' : 'REJECTED'}
                    </span>
                    <span className="font-semibold text-slate-850 dark:text-slate-205">
                      {item.sourceTable} {item.targetTable !== 'N/A' && `→ ${item.targetTable}`}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 font-sans">
                    {item.reason}
                  </p>
                </div>
                <div className="text-[10px] text-slate-400 dark:text-slate-500 self-end sm:self-center shrink-0">
                  {item.timestamp}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
