import React, { useState, useMemo } from 'react';
import { LineageNodeData, LineageEdgeData, ImpactAnalysisResult } from '../types/lineage';
import { computeImpactAnalysis, exportImpactReportToCSV } from '../services/lineageEngine';
import { useImpact } from '../hooks/useImpact';
import { ImpactBlastRadiusGraph } from './ImpactBlastRadiusGraph';
import type { ChangeKind } from '../types/backend';
import { 
  Zap, 
  AlertTriangle, 
  ShieldAlert, 
  LayoutDashboard, 
  Cpu,
  Layers,
  Download, 
  Eye, 
  CheckCircle2, 
  Sparkles,
  HelpCircle,
  FileCode2,
  Table2,
  ChevronDown
} from 'lucide-react';
import type { ImpactEdgeView } from '../types/backend';
import { ROLE_LABEL, roleRank, stripSchemaNote } from '../utils/impactGrouping';

interface ImpactAnalysisViewProps {
  nodes: LineageNodeData[];
  edges: LineageEdgeData[];
  initialNodeId?: string;
  onNavigateToGraphWithImpact: (targetId: string, downstreamIds: string[], upstreamIds: string[]) => void;
  onAskCopilot: (question: string) => void;
  onApproveProposedChange?: (
    nodeId: string, 
    operation: string, 
    columnName: string, 
    newColumnName?: string, 
    notes?: string
  ) => void;
}

// Map "thao tác thay đổi" (UI) -> change_kind thật của backend — đủ cả 8/8
// operation (xem _RISK_BY_TRANSFORM trong src/services/impact_service.py).
function operationToChangeKind(operation: ImpactAnalysisResult['operation']): ChangeKind | undefined {
  if (operation === 'modify_schema') return 'type';
  if (operation === 'change_logic') return 'value';
  if (operation === 'drop_column') return 'drop';
  if (operation === 'drop_table') return 'drop_table';
  if (operation === 'rename_column') return 'rename';
  if (operation === 'rename_table') return 'rename_table';
  if (operation === 'add_column') return 'add_column';
  if (operation === 'change_constraint') return 'constraint';
  return undefined;
}

// Thao tác nhắm vào CẢ BẢNG (không phải 1 cột cụ thể) — Target Column vô nghĩa
// với các operation này, và query impact phải bỏ column filter (không được
// ép về cột đầu tiên của bảng, nếu không sẽ hẹp sai blast radius: chỉ thấy
// downstream đi qua đúng 1 cột thay vì toàn bộ bảng). "add_column" cũng vào
// nhóm này — cột mới CHƯA TỒN TẠI nên không có gì để chọn trong Target
// Column, khác "change_constraint" (đổi constraint trên 1 cột ĐÃ CÓ, vẫn là
// column-level bình thường).
function isTableLevelOperation(operation: ImpactAnalysisResult['operation']): boolean {
  return operation === 'drop_table' || operation === 'rename_table' || operation === 'add_column';
}

export const ImpactAnalysisView: React.FC<ImpactAnalysisViewProps> = ({
  nodes,
  edges,
  initialNodeId,
  onNavigateToGraphWithImpact,
  onAskCopilot,
  onApproveProposedChange
}) => {
  const { result: realImpactResult, query: queryRealImpact, error: realImpactError } = useImpact();
  // Upstream Data Provenance: trước đây tính BFS client-side trên nodes/edges
  // (đúng vì topology thật, nhưng là 1 code path riêng không dùng GET /impact
  // như downstream) — giờ gọi cùng endpoint thật với direction=upstream, để
  // 1 nguồn sự thật duy nhất, có luôn hop/confidence/source_type/evidence.
  const { result: realUpstreamResult, query: queryRealUpstream } = useImpact();
  const [collapsedHops, setCollapsedHops] = useState<Set<number>>(new Set());
  const [selectedNodeId, setSelectedNodeId] = useState<string>(initialNodeId || (nodes[0]?.id || 'stg_orders'));
  const [operation, setOperation] = useState<ImpactAnalysisResult['operation']>('drop_column');
  const [selectedColumn, setSelectedColumn] = useState<string>('');
  // Kiểu dữ liệu đích — chỉ dùng khi operation = "modify_schema" (đổi kiểu).
  // Có + cột có schema thì backend phân loại chuyển kiểu (mở rộng/thu hẹp/đổi họ).
  const [targetType, setTargetType] = useState<string>('');

  // AI analysis flow states
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisStep, setAnalysisStep] = useState('');
  const [analyzedResult, setAnalyzedResult] = useState<ImpactAnalysisResult | null>(null);

  // Approval modal states
  const [isApproveModalOpen, setIsApproveModalOpen] = useState(false);
  const [newColumnName, setNewColumnName] = useState('');
  const [approveNotes, setApproveNotes] = useState('');
  const [isApprovalSuccess, setIsApprovalSuccess] = useState(false);

  const targetNode = useMemo(() => {
    return nodes.find(n => n.id === selectedNodeId) || nodes[0];
  }, [nodes, selectedNodeId]);

  // Nhóm kết quả impact THẬT (confirmed + inferred_pending) theo hops — mỗi
  // hop là 1 tầng phụ thuộc tính từ bảng gốc đang truy vấn (hop 1 = phụ
  // thuộc trực tiếp). Cho phép thu gọn từng tầng: bảng nào có 8-9 tầng phụ
  // thuộc thì không bị dồn thành 1 danh sách phẳng khó theo dõi.
  const hopTiers = useMemo<[number, ImpactEdgeView[]][]>(() => {
    if (!realImpactResult) return [];
    const all = [...(realImpactResult.confirmed || []), ...(realImpactResult.inferred_pending || [])];
    const byHop = new Map<number, ImpactEdgeView[]>();
    for (const edge of all) {
      const hop = edge.hops ?? 1;
      if (!byHop.has(hop)) byHop.set(hop, []);
      byHop.get(hop)!.push(edge);
    }
    return Array.from(byHop.entries()).sort((a, b) => a[0] - b[0]);
  }, [realImpactResult]);

  // Gom cạnh theo QUAN HỆ (bảng nguồn -> bảng đích) trong từng tầng — 1 cặp
  // bảng có thể có nhiều cạnh (cột chảy vào output + cùng cột đó làm khoá JOIN
  // + GROUP BY...). Trước đây mỗi cạnh 1 card -> nhìn như "lặp lại cùng 1 quan
  // hệ". Giờ 1 card / quan hệ, liệt kê từng vai trò + rủi ro riêng bên trong.
  const hopGroups = useMemo(() => {
    return hopTiers.map(([hop, items]) => {
      const byRel = new Map<string, ImpactEdgeView[]>();
      for (const e of items) {
        const key = `${e.source.table} ${e.target.table}`;
        const list = byRel.get(key) ?? [];
        list.push(e);
        byRel.set(key, list);
      }
      const groups = Array.from(byRel.values()).map((edges) => ({
        source: edges[0].source.table,
        target: edges[0].target.table,
        edges: [...edges].sort((a, b) => roleRank(a) - roleRank(b)),
        schemaNote: edges.find((e) => e.schema_note)?.schema_note ?? null,
        hasPending: edges.some((e) => e.hitl_status === 'pending'),
        maxConfidence: Math.max(...edges.map((e) => e.confidence)),
        sourceType: edges[0].source_type,
        filePath: edges.find((e) => e.evidence?.file_path)?.evidence?.file_path ?? null,
      }));
      return { hop, groups };
    });
  }, [hopTiers]);

  // Số liệu thật tổng hợp từ realImpactResult — thay cho riskScore/criticalDashboards/
  // mlFeaturesAffected bịa trước đây (backend không có khái niệm dashboard/feature store,
  // xem docs/impact_analysis_explainability_plan tương ứng đã bị bỏ). Chỉ đếm số thật.
  const downstreamSummary = useMemo(() => {
    if (!realImpactResult) return null;
    const confirmed = realImpactResult.confirmed || [];
    const pending = realImpactResult.inferred_pending || [];
    const all = [...confirmed, ...pending];
    const uniqueTables = new Set(all.map(e => e.target.table));
    const maxHop = all.reduce((m, e) => Math.max(m, e.hops ?? 1), 0);
    const riskedCount = all.filter(e => e.risk).length;
    return {
      uniqueTableCount: uniqueTables.size,
      confirmedCount: confirmed.length,
      pendingCount: pending.length,
      maxHop,
      riskedCount,
      totalCount: all.length,
    };
  }, [realImpactResult]);

  // Danh sách bảng nguồn duy nhất cho panel Upstream Data Provenance, lấy
  // thật từ GET /impact?direction=upstream thay vì BFS bịa client-side.
  const upstreamTables = useMemo(() => {
    if (!realUpstreamResult) return [];
    const all = [...(realUpstreamResult.confirmed || []), ...(realUpstreamResult.inferred_pending || [])];
    const seen = new Map<string, ImpactEdgeView>();
    for (const edge of all) {
      const key = edge.source.table;
      const existing = seen.get(key);
      if (!existing || (edge.hops ?? 1) < (existing.hops ?? 1)) seen.set(key, edge);
    }
    return Array.from(seen.values()).sort((a, b) => (a.hops ?? 1) - (b.hops ?? 1));
  }, [realUpstreamResult]);

  // Cạnh phẳng (không gộp theo tầng) để vẽ blast-radius graph — mỗi cạnh giữ
  // nguyên source/target/hops thật, tự đủ dữ liệu để layout nhiều tầng.
  const flatDownstreamEdges = useMemo(
    () => [...(realImpactResult?.confirmed || []), ...(realImpactResult?.inferred_pending || [])],
    [realImpactResult]
  );
  const flatUpstreamEdges = useMemo(
    () => [...(realUpstreamResult?.confirmed || []), ...(realUpstreamResult?.inferred_pending || [])],
    [realUpstreamResult]
  );

  const toggleHopCollapsed = (hop: number) => {
    setCollapsedHops(prev => {
      const next = new Set(prev);
      if (next.has(hop)) next.delete(hop);
      else next.add(hop);
      return next;
    });
  };

  const handleRunAnalysis = async () => {
    if (!targetNode) return;
    setIsAnalyzing(true);
    setAnalyzedResult(null);

    const activeColumn = isTableLevelOperation(operation)
      ? undefined
      : selectedColumn || (targetNode.columns[0]?.name || '');

    // Bước 1-2: BFS đồng bộ trên topology thật (nodes/edges đã có sẵn) — chỉ
    // dùng cho Upstream Provenance + tên bảng, KHÔNG dùng phần downstream/risk
    // của kết quả này (xem downstreamSummary/hopTiers, lấy thật từ backend).
    setAnalysisStep('1. Phân tích cấu trúc SQL AST...');
    setAnalysisStep('2. Tracing quan hệ phụ thuộc...');
    const res = computeImpactAnalysis(selectedNodeId, operation, activeColumn, nodes, edges);
    setAnalyzedResult(res);

    // Bước 3: gọi thật GET /impact/{table} (2 chiều song song) — không có LLM
    // nào được gọi ở đây, risk note (nếu có) là tra bảng rule-based theo
    // transform_type ở backend.
    setAnalysisStep('3. Truy vấn đồ thị lineage & rủi ro thật từ backend...');
    const changeKind = operationToChangeKind(operation);
    const activeTargetType = operation === 'modify_schema' ? targetType.trim() || undefined : undefined;
    await Promise.all([
      queryRealImpact(selectedNodeId, 'downstream', activeColumn, changeKind, activeTargetType),
      queryRealUpstream(selectedNodeId, 'upstream', activeColumn, changeKind, activeTargetType),
    ]);

    setAnalysisStep('4. Tổng hợp kết quả...');
    setIsAnalyzing(false);
  };

  const handleConfirmApproval = () => {
    if (!onApproveProposedChange) return;
    const activeColumn = selectedColumn || (targetNode?.columns[0]?.name || '');
    onApproveProposedChange(selectedNodeId, operation, activeColumn, newColumnName, approveNotes);
    setIsApprovalSuccess(true);
    setTimeout(() => {
      setIsApproveModalOpen(false);
      setIsApprovalSuccess(false);
      setApproveNotes('');
      setNewColumnName('');
      setAnalyzedResult(null); // Clear after approval as it has been applied
    }, 1500);
  };

  return (
    <div className="w-full max-w-7xl mx-auto p-4 sm:p-6 space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-indigo-50 via-slate-50 to-indigo-50 dark:from-slate-900 dark:via-indigo-950 dark:to-slate-900 border border-indigo-100 dark:border-slate-800 rounded-3xl p-6 sm:p-8 text-slate-900 dark:text-white shadow-xl flex flex-col lg:flex-row lg:items-center justify-between gap-6 transition-all duration-300">
        <div className="space-y-2 max-w-3xl">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-amber-100 dark:bg-amber-500/20 text-amber-650 dark:text-amber-400 border border-amber-200 dark:border-amber-500/30">
              <Zap className="w-5 h-5" />
            </span>
            <span className="text-[11px] font-semibold text-indigo-700 dark:text-indigo-300 uppercase tracking-wider">
              Governance Hub &bull; Blast Radius Engine
            </span>
          </div>
          
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Automated Impact Analysis &amp; Blast Radius Engine
          </h1>
          
          <p className="text-xs sm:text-sm text-slate-650 dark:text-slate-300 leading-relaxed font-medium">
            Mô phỏng bán kính ảnh hưởng lan truyền khi sửa đổi hoặc xoá bảng/cột dữ liệu trước khi tạo Pull Request. 
            Ngăn ngừa sự cố đứt gãy trên các báo cáo BI Dashboard, Feature Store ML và các bảng tổng hợp downstream.
          </p>
        </div>

        {analyzedResult && realImpactResult && (
          <div className="flex items-center gap-3">
            <button
              id="export-impact-csv-btn"
              onClick={() => exportImpactReportToCSV(realImpactResult, {
                targetNodeName: targetNode?.name || selectedNodeId,
                operation,
                impactedColumn: selectedColumn,
              })}
              className="flex items-center gap-1.5 px-3 py-2 bg-slate-100 hover:bg-slate-205 dark:bg-white/10 dark:hover:bg-white/20 text-slate-700 dark:text-white rounded-xl text-xs font-semibold backdrop-blur border border-slate-200 dark:border-white/20 transition-colors cursor-pointer"
            >
              <Download className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
              <span>Export Impact CSV</span>
            </button>
            <button
              id="highlight-graph-btn"
              onClick={() => {
                const downstreamIds = Array.from(new Set([
                  ...realImpactResult.confirmed,
                  ...realImpactResult.inferred_pending,
                ].map(e => e.target.table)));
                const upstreamIds = upstreamTables.map(edge => edge.source.table);
                onNavigateToGraphWithImpact(analyzedResult.targetNodeId, downstreamIds, upstreamIds);
              }}
              className="flex items-center gap-1.5 px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-xl text-xs font-semibold backdrop-blur border border-white/20 transition-all cursor-pointer"
            >
              <Eye className="w-4 h-4" />
              <span>Xem trên Lineage Graph</span>
            </button>
          </div>
        )}
      </div>

      {/* Control Panel: Select Target Model & Operation */}
      <div className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* 1. Target Model */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
              1. Target Table / Model
            </label>
            <select
              id="impact-target-node-select"
              value={selectedNodeId}
              onChange={(e) => {
                setSelectedNodeId(e.target.value);
                const node = nodes.find(n => n.id === e.target.value);
                if (node && node.columns.length > 0) {
                  setSelectedColumn(node.columns[0].name);
                }
                setAnalyzedResult(null);
              }}
              className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-900 dark:text-slate-100 font-mono focus:ring-2 focus:ring-indigo-500 focus:outline-none cursor-pointer"
            >
              {nodes.map(n => (
                <option key={n.id} value={n.id}>
                  [{n.schema}] {n.name} ({n.layer})
                </option>
              ))}
            </select>
          </div>

          {/* 2. Proposed Operation */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
              2. Proposed Change Operation
            </label>
            <select
              id="impact-operation-select"
              value={operation}
              onChange={(e) => {
                setOperation(e.target.value as any);
                setAnalyzedResult(null);
              }}
              className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500 focus:outline-none cursor-pointer"
            >
              <option value="drop_column">Xóa cột (Ảnh hưởng hạ nguồn)</option>
              <option value="rename_column">Đổi tên cột (Cần cập nhật SQL)</option>
              <option value="modify_schema">Sửa kiểu dữ liệu / cấu trúc</option>
              <option value="drop_table">Xóa toàn bộ bảng / model</option>
              <option value="rename_table">Đổi tên bảng / model (rename dbt model)</option>
              <option value="change_logic">Thay đổi logic JOIN / Bộ lọc</option>
              <option value="add_column">Thêm cột mới</option>
              <option value="change_constraint">Đổi constraint (NOT NULL / PK-FK / partition key)</option>
            </select>
          </div>

          {/* 3. Target Column (if column operation) */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
              3. Target Column
            </label>
            <select
              id="impact-column-select"
              value={selectedColumn}
              onChange={(e) => {
                setSelectedColumn(e.target.value);
                setAnalyzedResult(null);
              }}
              disabled={isTableLevelOperation(operation)}
              className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-900 dark:text-slate-100 font-mono focus:ring-2 focus:ring-indigo-500 focus:outline-none cursor-pointer disabled:opacity-50"
            >
              {targetNode?.columns.map(c => (
                <option key={c.name} value={c.name}>
                  {c.name} ({c.type}) {c.isPrimaryKey ? '[PK]' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* 4. Kiểu đích — chỉ khi đổi kiểu dữ liệu */}
          {operation === 'modify_schema' && (
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1.5">
                4. Kiểu dữ liệu đích <span className="font-normal text-slate-400">(tuỳ chọn)</span>
              </label>
              <input
                type="text"
                value={targetType}
                onChange={(e) => {
                  setTargetType(e.target.value);
                  setAnalyzedResult(null);
                }}
                placeholder="vd INTEGER, VARCHAR(50), TIMESTAMP..."
                className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-900 dark:text-slate-100 font-mono focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
              <p className="mt-1 text-[10px] text-slate-400">
                {(() => {
                  const cur = targetNode?.columns.find(c => c.name === selectedColumn)?.type;
                  return cur && cur !== 'unknown'
                    ? `Kiểu hiện tại: ${cur}. Nhập kiểu đích để đánh giá mở rộng / thu hẹp / đổi họ kiểu.`
                    : 'Cột này chưa có kiểu khai báo — chỉ bảng nguồn (raw) và cột truyền thẳng mới có.';
                })()}
              </p>
            </div>
          )}
        </div>

        {/* Action Button to trigger AI check */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
          <p className="text-[11px] text-slate-400 dark:text-slate-500 font-mono text-left">
            * Bấm nút bên cạnh để chạy phân tích rủi ro hạ nguồn qua AI Engine.
          </p>
          <button
            id="run-impact-analysis-btn"
            onClick={handleRunAnalysis}
            disabled={isAnalyzing}
            className="flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold shadow-md shadow-indigo-600/10 transition-all cursor-pointer w-full sm:w-auto shrink-0"
          >
            {isAnalyzing ? (
              <>
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Đang phân tích...</span>
              </>
            ) : (
              <>
                <Cpu className="w-4 h-4 text-amber-300" />
                <span>Analyze Impact & Risks</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Loading Panel */}
      {isAnalyzing && (
        <div className="bg-white dark:bg-slate-900 p-8 rounded-2xl border border-indigo-100 dark:border-indigo-950/60 shadow-sm text-center space-y-4 max-w-xl mx-auto my-8">
          <div className="relative w-16 h-16 mx-auto">
            <div className="absolute inset-0 rounded-full border-4 border-indigo-100 dark:border-indigo-900 animate-pulse"></div>
            <div className="absolute inset-0 rounded-full border-4 border-t-indigo-600 dark:border-t-indigo-400 animate-spin"></div>
            <Cpu className="absolute inset-0 m-auto w-6 h-6 text-indigo-500 animate-pulse" />
          </div>
          
          <div className="space-y-1.5">
            <h4 className="text-sm font-bold font-mono text-slate-800 dark:text-slate-200">
              AI Engine đang phân tích...
            </h4>
            <p className="text-xs text-slate-500 dark:text-slate-400 font-mono italic animate-pulse">
              {analysisStep}
            </p>
          </div>
        </div>
      )}

      {/* Prompt State Panel */}
      {!isAnalyzing && !analyzedResult && (
        <div className="bg-white dark:bg-slate-900 p-12 rounded-2xl border border-slate-200 dark:border-slate-800 text-center shadow-sm max-w-xl mx-auto my-8 space-y-4">
          <div className="w-12 h-12 bg-indigo-50 dark:bg-indigo-950/60 rounded-full flex items-center justify-center mx-auto text-indigo-500">
            <Sparkles className="w-6 h-6 animate-pulse" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white font-mono">
              Chưa chạy phân tích tác động
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed max-w-md mx-auto">
              Hãy chọn thông tin phía trên và nhấn nút <strong className="text-indigo-500 font-semibold">"Analyze Impact & Risks"</strong> để bắt đầu.
            </p>
          </div>
        </div>
      )}

      {analyzedResult && (
        <>
          {realImpactError && (
            <div className="bg-red-50 dark:bg-red-950/30 p-4 rounded-2xl border border-red-200 dark:border-red-900 text-xs text-red-700 dark:text-red-300 mb-6">
              Không lấy được dữ liệu impact thật từ backend: {realImpactError}
            </div>
          )}

          {/* Stat tiles — số liệu thật lấy từ downstreamSummary (tổng hợp confirmed +
              inferred_pending của GET /impact/{table}), không còn riskScore/criticalDashboards/
              mlFeaturesAffected bịa theo node.layer. */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Downstream Tables (số bảng target duy nhất, thật) */}
            <div className="bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm flex items-center gap-3.5">
              <div className="p-3 rounded-xl bg-indigo-100 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400">
                <ShieldAlert className="w-6 h-6" />
              </div>
              <div>
                <span className="text-[11px] font-mono text-slate-500 dark:text-slate-400 uppercase">
                  Downstream Tables
                </span>
                <div className="text-2xl font-black font-mono text-slate-900 dark:text-white">
                  {downstreamSummary?.uniqueTableCount ?? 0}
                </div>
              </div>
            </div>

            {/* Confirmed vs Chờ duyệt (tín hiệu HITL thật) */}
            <div className="bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm flex items-center gap-3.5">
              <div className="p-3 rounded-xl bg-emerald-100 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400">
                <Layers className="w-6 h-6" />
              </div>
              <div>
                <span className="text-[11px] font-mono text-slate-500 dark:text-slate-400 uppercase">
                  Confirmed / Chờ duyệt
                </span>
                <div className="text-2xl font-black font-mono text-slate-900 dark:text-white">
                  {downstreamSummary?.confirmedCount ?? 0} / {downstreamSummary?.pendingCount ?? 0}
                </div>
              </div>
            </div>

            {/* Max hop — độ sâu lan truyền thật, thay cho "BI Dashboards at Risk" (backend
                không có khái niệm dashboard, xem context trong plan) */}
            <div className="bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm flex items-center gap-3.5">
              <div className="p-3 rounded-xl bg-sky-100 text-sky-600 dark:bg-sky-950/60 dark:text-sky-400">
                <LayoutDashboard className="w-6 h-6" />
              </div>
              <div>
                <span className="text-[11px] font-mono text-slate-500 dark:text-slate-400 uppercase">
                  Độ sâu lan truyền (hop)
                </span>
                <div className="text-2xl font-black font-mono text-slate-900 dark:text-white">
                  {downstreamSummary?.maxHop ?? 0}
                </div>
              </div>
            </div>

            {/* Cạnh có chấm rủi ro thật (chỉ khi operation map được change_kind) — thay
                cho "ML Features Affected" bịa */}
            <div className="bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm flex items-center gap-3.5">
              <div className="p-3 rounded-xl bg-purple-100 text-purple-600 dark:bg-purple-950/60 dark:text-purple-400">
                <Cpu className="w-6 h-6" />
              </div>
              <div>
                <span className="text-[11px] font-mono text-slate-500 dark:text-slate-400 uppercase">
                  Cạnh có chấm rủi ro
                </span>
                <div className="text-2xl font-black font-mono text-slate-900 dark:text-white">
                  {operationToChangeKind(operation)
                    ? `${downstreamSummary?.riskedCount ?? 0}/${downstreamSummary?.totalCount ?? 0}`
                    : 'N/A'}
                </div>
              </div>
            </div>
          </div>

          {/* Detailed Impact Breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Downstream Impact List (2 Cols) */}
            <div className="lg:col-span-2 bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800 mb-4">
                <h3 className="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                  <span>Downstream Blast Radius</span>
                </h3>
                <span className="text-xs font-mono text-slate-400">
                  {downstreamSummary?.totalCount ?? 0} cạnh phụ thuộc (GET /impact/{targetNode?.id})
                </span>
              </div>

              {/* Blast-radius graph — chỉ vẽ các bảng có quan hệ thật với bảng đang
                  phân tích (root ở giữa, downstream lệch phải theo tầng hop,
                  upstream lệch trái), thay vì phải đọc hết danh sách text mới
                  hình dung được cấu trúc. Danh sách chi tiết bên dưới vẫn giữ
                  để xem risk note đầy đủ từng cạnh. */}
              {(flatDownstreamEdges.length > 0 || flatUpstreamEdges.length > 0) && (
                <div className="mb-4">
                  <ImpactBlastRadiusGraph
                    rootTable={selectedNodeId}
                    rootColumn={!isTableLevelOperation(operation) ? selectedColumn : undefined}
                    downstreamEdges={flatDownstreamEdges}
                    upstreamEdges={flatUpstreamEdges}
                  />
                </div>
              )}

              {hopTiers.length === 0 ? (
                <div className="py-8 text-center text-slate-400 dark:text-slate-500 font-mono text-xs">
                  <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                  Không phát hiện bảng phụ thuộc downstream nào (thật). An toàn để sửa đổi!
                </div>
              ) : (
                <div className="space-y-2.5">
                  {hopGroups.map(({ hop, groups }) => {
                    const collapsed = collapsedHops.has(hop);
                    return (
                      <div key={hop} className="rounded-xl border border-slate-200 dark:border-slate-700/80 overflow-hidden">
                        <button
                          type="button"
                          onClick={() => toggleHopCollapsed(hop)}
                          className="w-full flex items-center justify-between px-3 py-2 bg-slate-100 dark:bg-slate-800 text-left cursor-pointer"
                        >
                          <span className="text-xs font-bold text-slate-700 dark:text-slate-200">
                            Tầng {hop} &bull; {groups.length} bảng downstream
                          </span>
                          <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${collapsed ? '-rotate-90' : ''}`} />
                        </button>
                        {!collapsed && (
                          <div className="p-2.5 space-y-2 bg-white dark:bg-slate-900">
                            {groups.map((g, gi) => (
                              <div
                                key={gi}
                                className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80"
                              >
                                {/* 1 quan hệ = 1 card */}
                                <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                                  <div className="flex items-center gap-1.5 flex-wrap text-xs font-mono font-bold text-slate-900 dark:text-white">
                                    <span>{g.source}</span>
                                    <span className="text-slate-400">→</span>
                                    <span>{g.target}</span>
                                    {g.hasPending && (
                                      <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                                        CHỜ DUYỆT
                                      </span>
                                    )}
                                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-sky-100 dark:bg-sky-950/60 text-sky-700 dark:text-sky-300 border border-sky-200 dark:border-sky-800">
                                      {g.sourceType === 'parser' ? 'Parser' : 'LLM'}
                                    </span>
                                  </div>
                                  <span className="text-[10px] font-mono text-slate-400">
                                    confidence {(g.maxConfidence * 100).toFixed(0)}%
                                  </span>
                                </div>

                                {/* Câu dẫn schema — hiển thị 1 lần cho cả quan hệ */}
                                {g.schemaNote && (
                                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mb-2 pl-2 border-l-2 border-slate-300 dark:border-slate-600">
                                    {g.schemaNote}
                                  </p>
                                )}

                                {/* Từng vai trò của cột nguồn trong quan hệ này */}
                                <div className="space-y-2">
                                  {g.edges.map((e, ei) => {
                                    const isControl = e.dependency_kind !== 'output';
                                    const token = isControl
                                      ? (e.source.column ?? '(cả bảng)')
                                      : `${e.source.column ?? '(cả bảng)'} → ${e.target.column ?? '(cả bảng)'}`;
                                    return (
                                      <div key={ei} className="text-xs">
                                        <div className="flex items-center gap-1.5 flex-wrap mb-1">
                                          <span
                                            className={`inline-block text-[9px] font-bold px-1.5 py-0.5 rounded ${
                                              isControl
                                                ? 'bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800'
                                                : 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                                            }`}
                                            title={
                                              isControl
                                                ? `Cột "${e.source.column}" không mang dữ liệu vào bảng đích nhưng quyết định hàng nào xuất hiện`
                                                : 'Dữ liệu chảy trực tiếp vào cột đích'
                                            }
                                          >
                                            {isControl ? (ROLE_LABEL[e.dependency_kind] ?? 'CONTROL') : 'DỮ LIỆU'}
                                          </span>
                                          <code className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-800 dark:bg-slate-950 text-slate-100 dark:text-slate-200 border border-slate-700 dark:border-slate-800">
                                            {token}
                                          </code>
                                        </div>
                                        <p className="text-slate-600 dark:text-slate-300 leading-relaxed">
                                          {stripSchemaNote(e.risk, g.schemaNote) ??
                                            'Chưa có mô hình chấm rủi ro cho thao tác này — chọn "Sửa kiểu dữ liệu" hoặc "Thay đổi logic".'}
                                        </p>
                                      </div>
                                    );
                                  })}
                                </div>

                                {g.filePath && (
                                  <p className="text-[10px] font-mono text-slate-400 dark:text-slate-500 mt-2 truncate">
                                    {g.filePath}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Sidebar: Upstream Lineage & Automated Mitigation Advice */}
            <div className="space-y-6">
              {/* Automated Mitigation Plan */}
              <div className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
                <h3 className="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2 mb-3">
                  <Sparkles className="w-4 h-4 text-indigo-500" />
                  <span>Recommended Mitigation Actions</span>
                </h3>
                <div className="space-y-2.5 text-xs text-slate-700 dark:text-slate-300">
                  {analyzedResult.mitigationAdvice.map((advice, aIdx) => (
                    <div
                      key={aIdx}
                      className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 leading-relaxed font-sans"
                    >
                      {advice}
                    </div>
                  ))}
                </div>

                <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800">
                  <button
                    id="ask-copilot-mitigate-btn"
                    onClick={() => {
                      const realItems = [...(realImpactResult?.confirmed || []), ...(realImpactResult?.inferred_pending || [])];
                      const withRisk = realItems.filter(e => e.risk);
                      const evidenceLines = withRisk.length
                        ? withRisk
                            .map(e => `- ${e.target.table}${e.hitl_status === 'pending' ? ' (chờ duyệt)' : ''} [tầng ${e.hops ?? '?'}]: ${e.risk}`)
                            .join('\n')
                        : realItems.length
                          ? `- ${realItems.length} bảng downstream thật (chưa chấm risk cụ thể cho thao tác này).`
                          : '- Chưa truy vấn được dữ liệu impact thật từ backend cho bảng này.';
                      onAskCopilot(
                        `Tôi đang cân nhắc thao tác "${operation}" trên ${selectedNodeId}${selectedColumn ? `.${selectedColumn}` : ''}. ` +
                        `Dữ liệu impact thật từ backend (GET /impact/${selectedNodeId}):\n${evidenceLines}\n` +
                        `Hãy đề xuất cách refactor an toàn để giảm rủi ro này.`
                      );
                    }}
                    className="w-full py-2 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-950/40 dark:hover:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Hỏi Copilot tạo kịch bản Refactor an toàn</span>
                  </button>
                </div>
              </div>

              {/* Upstream Data Provenance (Where does it come from?) */}
              <div className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
                <h3 className="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2 mb-3">
                  <Layers className="w-4 h-4 text-sky-500" />
                  <span>Upstream Data Provenance</span>
                </h3>
                {upstreamTables.length === 0 ? (
                  <p className="text-xs text-slate-400 font-mono">
                    {realUpstreamResult ? 'Đây là nút nguồn gốc (Root Ingest Source Node).' : 'Chưa chạy phân tích.'}
                  </p>
                ) : (
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {upstreamTables.map((edge, uIdx) => (
                      <div
                        key={uIdx}
                        className="p-2 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 flex items-center justify-between font-mono text-[11px]"
                      >
                        <span className="font-semibold text-slate-800 dark:text-slate-200 truncate">
                          {edge.source.table}
                        </span>
                        <div className="flex items-center gap-1.5 shrink-0">
                          {edge.hitl_status === 'pending' && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300">
                              CHỜ DUYỆT
                            </span>
                          )}
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-100 dark:bg-sky-950 text-sky-700 dark:text-sky-300">
                            {edge.source_type === 'parser' ? 'Parser' : 'LLM'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
      {/* Approval Confirmation Modal */}
      {isApproveModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-2xl w-full max-w-lg p-6 overflow-hidden space-y-4 text-left">
            {isApprovalSuccess ? (
              <div className="text-center py-6 space-y-3">
                <div className="w-16 h-16 bg-emerald-100 dark:bg-emerald-950/80 rounded-full flex items-center justify-center mx-auto text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="w-8 h-8 animate-bounce" />
                </div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                  Phê Duyệt Thành Công!
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Thiết lập thay đổi schema đã được áp dụng trực tiếp và ghi nhật ký HITL thành công.
                </p>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
                  <h3 className="font-bold text-base text-slate-900 dark:text-white flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                    <span>Duyệt &amp; Áp dụng thay đổi Schema</span>
                  </h3>
                  <button
                    onClick={() => setIsApproveModalOpen(false)}
                    className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
                  >
                    ✕
                  </button>
                </div>

                <div className="space-y-3.5 text-xs">
                  <div className="p-3 bg-slate-50 dark:bg-slate-800/80 rounded-2xl border border-slate-100 dark:border-slate-700 space-y-1.5 text-slate-700 dark:text-slate-300">
                    <div>
                      <span className="font-semibold text-slate-500 text-[10px]">Bảng tác động:</span>{' '}
                      <span className="font-mono text-slate-900 dark:text-white font-bold">[{targetNode?.schema}] {targetNode?.name}</span>
                    </div>
                    <div>
                      <span className="font-semibold text-slate-500 text-[10px]">Thao tác đề xuất:</span>{' '}
                      <span className="px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 font-mono font-bold">
                        {operation.toUpperCase()}
                      </span>
                    </div>
                    {!isTableLevelOperation(operation) && (
                      <div>
                        <span className="font-semibold text-slate-500 text-[10px]">Cột tác động:</span>{' '}
                        <span className="font-mono text-slate-900 dark:text-white font-bold">{selectedColumn || (targetNode?.columns[0]?.name)}</span>
                      </div>
                    )}
                    {downstreamSummary && (
                      <div className="pt-1.5 border-t border-slate-200 dark:border-slate-700 flex items-center justify-between text-[10px]">
                        <span className="text-rose-500 font-medium">
                          ⚠️ {downstreamSummary.riskedCount}/{downstreamSummary.totalCount} cạnh có đánh giá rủi ro
                        </span>
                        <span className="text-slate-500 font-medium">
                          {downstreamSummary.uniqueTableCount} bảng hạ nguồn bị ảnh hưởng
                        </span>
                      </div>
                    )}
                  </div>

                  {(operation === 'rename_column' || operation === 'add_column') && (
                    <div className="space-y-1">
                      <label className="block font-semibold text-slate-700 dark:text-slate-300">
                        {operation === 'add_column' ? 'Tên cột mới cần thêm:' : 'Tên cột mới:'}
                      </label>
                      <input
                        type="text"
                        value={newColumnName}
                        onChange={(e) => setNewColumnName(e.target.value)}
                        placeholder={operation === 'add_column' ? 'Nhập tên cột sắp thêm...' : 'Nhập tên cột mới...'}
                        className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-900 dark:text-slate-100 font-mono focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                  )}

                  <div className="space-y-1">
                    <label className="block font-semibold text-slate-700 dark:text-slate-300">
                      Ghi chú / Lý do phê duyệt (Notes / Reason):
                    </label>
                    <textarea
                      value={approveNotes}
                      onChange={(e) => setApproveNotes(e.target.value)}
                      placeholder="Ví dụ: Đã kiểm tra code dbt và lấy ý kiến từ đội phân tích báo cáo..."
                      rows={3}
                      className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-805 border border-slate-250 dark:border-slate-750 rounded-xl text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-indigo-500 focus:outline-none resize-none"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                  <button
                    onClick={() => setIsApproveModalOpen(false)}
                    className="px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-xl text-xs font-semibold cursor-pointer"
                  >
                    Hủy bỏ
                  </button>
                  <button
                    onClick={handleConfirmApproval}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 cursor-pointer shadow-lg shadow-emerald-600/25"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Xác nhận &amp; Áp dụng</span>
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
