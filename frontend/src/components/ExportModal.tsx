import React from 'react';
import { LineageNodeData, LineageEdgeData, HITLQueueItem } from '../types/lineage';
import { 
  exportLineageToCSV, 
  exportLineageToJSON, 
  exportDatabaseToSQL, 
  exportCatalogToCSV 
} from '../services/lineageEngine';
import { 
  Download, 
  FileSpreadsheet, 
  FileJson, 
  X, 
  Code2, 
  Database, 
  Layers,
  BookOpen
} from 'lucide-react';

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  nodes: LineageNodeData[];
  edges: LineageEdgeData[];
  hitlQueue: HITLQueueItem[];
}

export const ExportModal: React.FC<ExportModalProps> = ({
  isOpen,
  onClose,
  nodes,
  edges,
  hitlQueue
}) => {
  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white dark:bg-slate-900 max-w-lg w-full rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl p-6 space-y-5 animate-fadeIn">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
              <Download className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-mono text-base font-bold text-slate-900 dark:text-white">
                Export Database &amp; Lineage Artifacts
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                DATA-04 Lineage AI (Baby Sharks - P-116)
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Export Options */}
        <div className="space-y-3">
          {/* SQL DDL Export */}
          <button
            id="modal-export-sql-btn"
            onClick={() => {
              exportDatabaseToSQL(nodes);
              onClose();
            }}
            className="w-full p-4 rounded-xl border border-slate-200 dark:border-slate-700/80 hover:border-indigo-500 dark:hover:border-indigo-500 bg-slate-50 dark:bg-slate-800/60 hover:bg-indigo-50/50 dark:hover:bg-indigo-950/30 flex items-center justify-between text-left transition-all cursor-pointer group"
          >
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-indigo-100 dark:bg-indigo-950/80 text-indigo-600 dark:text-indigo-400">
                <Code2 className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-xs font-bold font-mono text-slate-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400">
                  Export Database DDL Script (.sql)
                </h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  Câu lệnh CREATE TABLE chuẩn ANSI SQL cho {nodes.length} bảng và các cột.
                </p>
              </div>
            </div>
            <Download className="w-4 h-4 text-slate-400 group-hover:text-indigo-600" />
          </button>

          {/* Data Catalog CSV */}
          <button
            id="modal-export-catalog-csv-btn"
            onClick={() => {
              exportCatalogToCSV(nodes);
              onClose();
            }}
            className="w-full p-4 rounded-xl border border-slate-200 dark:border-slate-700/80 hover:border-indigo-500 dark:hover:border-indigo-500 bg-slate-50 dark:bg-slate-800/60 hover:bg-indigo-50/50 dark:hover:bg-indigo-950/30 flex items-center justify-between text-left transition-all cursor-pointer group"
          >
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400">
                <BookOpen className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-xs font-bold font-mono text-slate-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400">
                  Export Data Catalog Dictionary (.csv)
                </h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  Bảng từ điển toàn bộ danh mục cột, kiểu dữ liệu, primary key và chủ sở hữu.
                </p>
              </div>
            </div>
            <Download className="w-4 h-4 text-slate-400 group-hover:text-indigo-600" />
          </button>

          {/* Edge Lineage CSV */}
          <button
            id="modal-export-csv-btn"
            onClick={() => {
              exportLineageToCSV(nodes, edges);
              onClose();
            }}
            className="w-full p-4 rounded-xl border border-slate-200 dark:border-slate-700/80 hover:border-indigo-500 dark:hover:border-indigo-500 bg-slate-50 dark:bg-slate-800/60 hover:bg-indigo-50/50 dark:hover:bg-indigo-950/30 flex items-center justify-between text-left transition-all cursor-pointer group"
          >
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-cyan-100 dark:bg-cyan-950/80 text-cyan-600 dark:text-cyan-400">
                <FileSpreadsheet className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-xs font-bold font-mono text-slate-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400">
                  Export Lineage Edge Table (.csv)
                </h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  Bảng danh sách {edges.length} liên kết luồng dữ liệu, độ tin cậy và lý do AI.
                </p>
              </div>
            </div>
            <Download className="w-4 h-4 text-slate-400 group-hover:text-indigo-600" />
          </button>

          {/* JSON Export */}
          <button
            id="modal-export-json-btn"
            onClick={() => {
              exportLineageToJSON(nodes, edges, hitlQueue);
              onClose();
            }}
            className="w-full p-4 rounded-xl border border-slate-200 dark:border-slate-700/80 hover:border-indigo-500 dark:hover:border-indigo-500 bg-slate-50 dark:bg-slate-800/60 hover:bg-indigo-50/50 dark:hover:bg-indigo-950/30 flex items-center justify-between text-left transition-all cursor-pointer group"
          >
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-lg bg-amber-100 dark:bg-amber-950/80 text-amber-600 dark:text-amber-400">
                <FileJson className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-xs font-bold font-mono text-slate-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400">
                  Export Full DAG Manifest (.json)
                </h4>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  Đầy đủ thông tin {nodes.length} bảng, column lineage và quyết định HITL.
                </p>
              </div>
            </div>
            <Download className="w-4 h-4 text-slate-400 group-hover:text-indigo-600" />
          </button>
        </div>

        <div className="pt-2 text-center">
          <span className="text-[11px] text-slate-400 font-mono">
            Tương thích chuẩn dbt schema, OpenLineage &amp; DataHub
          </span>
        </div>
      </div>
    </div>
  );
};
