import React, { useMemo } from 'react';
import { LineageNodeData, LineageEdgeData, HITLQueueItem } from '../types/lineage';
import { BreakingChangeAlertsPanel } from './BreakingChangeAlertsPanel';
import { 
  ResponsiveContainer, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip, 
  PieChart, 
  Pie, 
  Cell 
} from 'recharts';
import { 
  Database, 
  ArrowRight, 
  AlertTriangle, 
  Layers, 
  Cpu, 
  GitBranch, 
  Activity, 
  ExternalLink,
  Table,
  ShieldCheck,
  Flame,
  Check,
  Zap,
  BrainCircuit,
  Server
} from 'lucide-react';

interface OverviewDashboardProps {
  nodes: LineageNodeData[];
  edges: LineageEdgeData[];
  hitlQueue: HITLQueueItem[];
  projectName: string;
  onNavigateTab: (tab: any) => void;
  onSelectNodeInGraph: (nodeId: string) => void;
  onAnalyzeImpactForNode: (node: LineageNodeData) => void;
  onConfirmHITLEdge: (item: HITLQueueItem) => void;
  onRejectHITLEdge: (item: HITLQueueItem) => void;
  onAskCopilot?: (question: string) => void;
}

const LAYER_COLORS: Record<string, string> = {
  source: '#64748b',       // Slate (Bronze)
  staging: '#06b6d4',      // Cyan (Silver)
  intermediate: '#3b82f6', // Blue
  marts: '#f59e0b',        // Amber (Gold)
  bi_dashboard: '#8b5cf6', // Purple
  feature_store: '#10b981',// Emerald
  reverse_etl: '#ec4899',  // Pink
};

export const OverviewDashboard: React.FC<OverviewDashboardProps> = ({
  nodes,
  edges,
  hitlQueue,
  projectName,
  onNavigateTab,
  onSelectNodeInGraph,
  onAnalyzeImpactForNode,
  onConfirmHITLEdge,
  onRejectHITLEdge,
  onAskCopilot
}) => {
  // Computed Telemetry Metrics
  const totalAssets = nodes.length;
  const totalCols = useMemo(() => nodes.reduce((acc, n) => acc + n.columns.length, 0), [nodes]);
  const totalEdges = edges.length;
  const parserEdgesCount = useMemo(() => edges.filter(e => e.inferredBy === 'sqlglot_parser' || e.inferredBy === 'human_verified').length, [edges]);
  const llmEdgesCount = useMemo(() => edges.filter(e => e.inferredBy === 'gemini_llm').length, [edges]);
  const astRate = totalEdges > 0 ? Math.round((parserEdgesCount / totalEdges) * 100) : 85;
  const totalRowsCount = useMemo(() => nodes.reduce((acc, n) => acc + (n.rowCount || 0), 0), [nodes]);
  const avgQualityScore = useMemo(() => {
    const sum = nodes.reduce((acc, n) => acc + (n.qualityScore || 99), 0);
    return (sum / (nodes.length || 1)).toFixed(1);
  }, [nodes]);
  const biConsumersCount = useMemo(() => nodes.filter(n => n.layer === 'bi_dashboard' || n.layer === 'feature_store' || n.layer === 'reverse_etl').length, [nodes]);
  const pendingHitlCount = useMemo(() => hitlQueue.filter(h => h.status === 'pending').length, [hitlQueue]);

  // Static Defined Metric Cards with English Titles & Vietnamese Descriptions
  const metricCards = [
    {
      id: 'card-assets',
      title: 'Total Data Assets',
      subtitle: 'Phân tầng qua 7 lớp kiến trúc',
      value: totalAssets,
      icon: Database,
      color: 'text-indigo-500 bg-indigo-50 dark:bg-indigo-950/60 hover:border-indigo-500',
      targetTab: 'catalog'
    },
    {
      id: 'card-columns',
      title: 'Schema Columns',
      subtitle: 'Theo dõi chi tiết cấp trường',
      value: totalCols,
      icon: Table,
      color: 'text-cyan-500 bg-cyan-50 dark:bg-cyan-950/60 hover:border-cyan-500',
      targetTab: 'catalog'
    },
    {
      id: 'card-rows',
      title: 'Total Data Rows',
      subtitle: 'Tổng số bản ghi trong hồ dữ liệu',
      value: totalRowsCount.toLocaleString(),
      icon: Server,
      color: 'text-amber-500 bg-amber-50 dark:bg-amber-950/60 hover:border-amber-500',
      targetTab: 'catalog'
    },
    {
      id: 'card-edges',
      title: 'Lineage Edges',
      subtitle: 'Mối quan hệ liên kết trong DAG',
      value: totalEdges,
      icon: GitBranch,
      color: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-950/60 hover:border-emerald-500',
      targetTab: 'explorer'
    },
    {
      id: 'card-hitl',
      title: 'HITL Review Queue',
      subtitle: 'Liên kết cần kỹ sư xác nhận',
      value: pendingHitlCount,
      icon: AlertTriangle,
      color: 'text-rose-500 bg-rose-50 dark:bg-rose-950/60 hover:border-rose-500',
      targetTab: 'hitl'
    }
  ];

  // 1. Data Layer Distribution Chart Data
  const layerDistribution = useMemo(() => {
    const counts: Record<string, number> = {};
    nodes.forEach(n => {
      counts[n.layer] = (counts[n.layer] || 0) + 1;
    });
    return Object.entries(counts).map(([layer, count]) => ({
      name: layer.replace('_', ' ').toUpperCase(),
      layerKey: layer,
      count,
      color: LAYER_COLORS[layer] || '#6366f1'
    }));
  }, [nodes]);

  // 2. Engine Breakdown Chart Data (Verified Flow, LLM Generated, HITL Queue)
  const verifiedFlowCount = useMemo(() => edges.filter(e => e.status !== 'pending_hitl' && (e.inferredBy === 'sqlglot_parser' || e.inferredBy === 'human_verified')).length, [edges]);
  const llmGeneratedCount = useMemo(() => edges.filter(e => e.status !== 'pending_hitl' && (e.inferredBy === 'gemini_llm' || e.inferredBy === 'gpt4o_mini')).length, [edges]);
  const hitlQueueCount = useMemo(() => edges.filter(e => e.status === 'pending_hitl').length, [edges]);

  const engineBreakdown = useMemo(() => {
    return [
      { name: 'Verified Flow', value: verifiedFlowCount, color: '#10b981' },
      { name: 'LLM Generated', value: llmGeneratedCount, color: '#6366f1' },
      { name: 'HITL Queue', value: hitlQueueCount, color: '#f59e0b' }
    ];
  }, [verifiedFlowCount, llmGeneratedCount, hitlQueueCount]);

  const verifiedRate = useMemo(() => {
    const totalInDAG = verifiedFlowCount + llmGeneratedCount + hitlQueueCount;
    return totalInDAG > 0 ? Math.round((verifiedFlowCount / totalInDAG) * 100) : 0;
  }, [verifiedFlowCount, llmGeneratedCount, hitlQueueCount]);

  // 3. Column Data Types Distribution
  const dataTypeDistribution = useMemo(() => {
    const counts: Record<string, number> = {
      'TIMESTAMP / DATE': 0,
      'DECIMAL / NUMERIC': 0,
      'VARCHAR / STRING': 0,
      'INTEGER / BIGINT': 0,
      'BOOLEAN / JSON': 0
    };
    nodes.forEach(n => {
      n.columns.forEach(col => {
        const t = col.type.toUpperCase();
        if (t.includes('TIME') || t.includes('DATE')) counts['TIMESTAMP / DATE']++;
        else if (t.includes('DECIMAL') || t.includes('FLOAT') || t.includes('DOUBLE') || t.includes('NUMERIC')) counts['DECIMAL / NUMERIC']++;
        else if (t.includes('INT')) counts['INTEGER / BIGINT']++;
        else if (t.includes('BOOL') || t.includes('JSON')) counts['BOOLEAN / JSON']++;
        else counts['VARCHAR / STRING']++;
      });
    });

    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [nodes]);

  // 4. Total Data Rows Table Data
  const totalRowsTableData = useMemo(() => {
    return [...nodes]
      .filter(n => n.type === 'table' || n.rowCount !== undefined)
      .sort((a, b) => (b.rowCount || 0) - (a.rowCount || 0));
  }, [nodes]);

  // 5. Quality SLA by Layer
  const qualityByLayer = useMemo(() => {
    const layerStats: Record<string, { totalScore: number; count: number }> = {};
    nodes.forEach(n => {
      if (!layerStats[n.layer]) {
        layerStats[n.layer] = { totalScore: 0, count: 0 };
      }
      layerStats[n.layer].totalScore += (n.qualityScore || 99);
      layerStats[n.layer].count += 1;
    });

    return Object.entries(layerStats).map(([layer, stats]) => ({
      layer: layer.replace('_', ' ').toUpperCase(),
      avgQuality: Number((stats.totalScore / stats.count).toFixed(1))
    }));
  }, [nodes]);

  return (
    <div className="w-full max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 space-y-8 animate-fadeIn text-slate-800 dark:text-slate-100">
      
      {/* 1. Header Banner (English Title with Vietnamese Subtitle) */}
      <div className="bg-gradient-to-r from-indigo-50 via-slate-50 to-indigo-50 dark:from-slate-900 dark:via-indigo-950 dark:to-slate-900 border border-indigo-100 dark:border-slate-800 rounded-[28px] p-6 sm:p-8 text-slate-900 dark:text-white shadow-xl flex flex-col lg:flex-row lg:items-center justify-between gap-6 transition-all duration-300">
        <div className="space-y-3.5 max-w-3xl">
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-3 py-1 rounded-full text-[11px] font-bold bg-indigo-100 dark:bg-indigo-500/20 text-indigo-850 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-500/30 flex items-center gap-1.5 shadow-sm">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              DATA-04 &bull; Governance Hub
            </span>
          </div>
          
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Data Architecture &amp; Lineage Intelligence
          </h1>
          
          <p className="text-xs sm:text-sm text-slate-650 dark:text-slate-300 leading-relaxed font-medium">
            Hệ thống quản trị luồng dữ liệu kết hợp phân tích cú pháp AST (sqlglot), suy luận AI Fallback và kiểm duyệt chuyên gia (HITL).
          </p>
        </div>

        {/* Action Shortcuts */}
        <div className="flex flex-wrap items-center gap-3 shrink-0">
          <button
            onClick={() => onNavigateTab('explorer')}
            className="px-5 py-3 bg-indigo-600 hover:bg-indigo-500 dark:bg-indigo-500 dark:hover:bg-indigo-600 text-white rounded-full text-xs font-bold flex items-center gap-2 shadow-sm transition-all hover:shadow duration-250 cursor-pointer"
          >
            <GitBranch className="w-4 h-4 text-white" />
            <span>Open Lineage DAG</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onNavigateTab('ingest')}
            className="px-5 py-3 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-white rounded-full text-xs font-bold flex items-center gap-2 border border-slate-200 dark:border-slate-600 transition-all duration-250 cursor-pointer shadow-sm"
          >
            <Database className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
            <span>SQL Ingest Scanner</span>
          </button>
        </div>
      </div>

      <BreakingChangeAlertsPanel onAskCopilot={onAskCopilot} />

      {/* 2. Key Metrics Telemetry Grid (English Title + Vietnamese Subtitle) */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest">
            Key Metrics &amp; Telemetry
          </h2>
          <span className="text-xs text-slate-400 font-semibold bg-white dark:bg-slate-900 px-3 py-1 rounded-full border border-slate-200/60 dark:border-slate-800/80 shadow-sm">
            Real-time Monitoring
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {metricCards.map((card) => {
            const Icon = card.icon;
            const colors = {
              'card-assets': { bg: 'bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 border border-indigo-100/50 dark:border-indigo-900/50' },
              'card-columns': { bg: 'bg-cyan-50 dark:bg-cyan-950/40 text-cyan-600 dark:text-cyan-400 border border-cyan-100/50 dark:border-cyan-900/50' },
              'card-rows': { bg: 'bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 border border-amber-100/50 dark:border-amber-900/50' },
              'card-edges': { bg: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-100/50 dark:border-emerald-900/50' },
              'card-hitl': { bg: 'bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 border border-rose-100/50 dark:border-rose-900/50' },
            }[card.id as 'card-assets' | 'card-columns' | 'card-rows' | 'card-edges' | 'card-hitl'] || { bg: 'bg-slate-100 dark:bg-slate-800 text-slate-500', border: 'border-slate-200' };

            return (
              <div
                key={card.id}
                onClick={() => card.targetTab && onNavigateTab(card.targetTab)}
                className="bg-white dark:bg-slate-900 p-5 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-sm transition-all duration-200 cursor-pointer group hover:shadow hover:border-indigo-300 dark:hover:border-indigo-900 hover:bg-slate-50/50 dark:hover:bg-slate-900/30 flex flex-col justify-between h-36"
              >
                <div>
                  <div className="flex items-center justify-between text-slate-400 gap-1.5">
                    <span className="text-[10.5px] font-bold tracking-wider uppercase truncate text-slate-500 dark:text-slate-400" title={card.title}>
                      {card.title}
                    </span>
                    <span className={`p-1.5 rounded-full shrink-0 flex items-center justify-center ${colors.bg}`}>
                      <Icon className="w-3.5 h-3.5" />
                    </span>
                  </div>

                  <div className="text-2xl font-extrabold text-slate-900 dark:text-white mt-2.5">
                    {card.value}
                  </div>
                </div>

                <div className="text-[10.5px] font-medium text-slate-500 dark:text-slate-400 mt-1 line-clamp-2 leading-tight">
                  {card.subtitle}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. Main Visual Charts Grid (3 Multi-Angle Perspectives) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Chart 1: Data Layer Distribution */}
        <div className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-sm space-y-4 transition-all hover:shadow duration-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="p-2 bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 rounded-full border border-indigo-100/50 dark:border-indigo-900/50 shrink-0">
                <Layers className="w-4 h-4" />
              </span>
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  Data Layer Distribution
                </h3>
                <p className="text-[10.5px] font-medium text-slate-500 dark:text-slate-400 leading-snug">
                  Số lượng tài sản qua từng tầng kiến trúc từ Bronze đến Gold &amp; BI
                </p>
              </div>
            </div>
          </div>

          <div className="h-60 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={layerDistribution} margin={{ top: 10, right: 10, left: -20, bottom: 25 }}>
                <XAxis 
                  dataKey="name" 
                  tick={{ fontSize: 9, fill: '#94a3b8' }} 
                  angle={-30} 
                  textAnchor="end"
                  interval={0}
                />
                <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} allowDecimals={false} />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#0f172a', 
                    borderRadius: '12px', 
                    border: '1px solid #334155',
                    color: '#f8fafc',
                    fontSize: '12px'
                  }} 
                />
                <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                  {layerDistribution.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 2: Inference Engine Split */}
        <div className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-sm space-y-4 transition-all hover:shadow duration-200">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-3">
              <span className="p-2 bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 rounded-full border border-emerald-100/50 dark:border-emerald-900/50 shrink-0">
                <Cpu className="w-4 h-4" />
              </span>
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  Inference Engine Split
                </h3>
                <p className="text-[10.5px] font-medium text-slate-500 dark:text-slate-400 leading-snug">
                  Tỷ lệ của Verified Flow, LLM Generated và HITL Queue
                </p>
              </div>
            </div>
            <button
              onClick={() => onNavigateTab('ingest')}
              className="px-3 py-1.5 bg-slate-50 hover:bg-slate-100 dark:bg-slate-800 dark:hover:bg-slate-700 text-[10.5px] font-bold text-indigo-600 dark:text-indigo-400 rounded-full border border-slate-200 dark:border-slate-700 transition-all cursor-pointer shadow-sm shrink-0"
            >
              Inspect
            </button>
          </div>

          <div className="h-60 w-full flex items-center justify-center relative">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={engineBreakdown}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {engineBreakdown.map((entry, index) => (
                    <Cell key={`cell-pie-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#0f172a', 
                    borderRadius: '12px', 
                    border: '1px solid #334155',
                    color: '#f8fafc',
                    fontSize: '12px'
                  }} 
                />
              </PieChart>
            </ResponsiveContainer>
            
            {/* Center Stat */}
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span className="text-xl font-bold font-mono text-slate-900 dark:text-white">
                {verifiedRate}%
              </span>
              <span className="text-[10px] font-mono text-slate-400">Verified Flow</span>
            </div>
          </div>

          <div className="flex items-center justify-around text-[10.5px] sm:text-[11px] pt-2 border-t border-slate-100 dark:border-slate-800/80 font-medium">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span>Verified ({verifiedFlowCount})</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-indigo-500" />
              <span>LLM ({llmGeneratedCount})</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              <span>HITL ({hitlQueueCount})</span>
            </div>
          </div>
        </div>

        {/* Chart 3: Column Feature Types */}
        <div className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-sm space-y-4 transition-all hover:shadow duration-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="p-2 bg-purple-50 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 rounded-full border border-purple-100/50 dark:border-purple-900/50 shrink-0">
                <BrainCircuit className="w-4 h-4" />
              </span>
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  Column Feature Types
                </h3>
                <p className="text-[10.5px] font-medium text-slate-500 dark:text-slate-400 leading-snug">
                  Cơ cấu kiểu dữ liệu trên toàn bộ {totalCols} trường
                </p>
              </div>
            </div>
          </div>

          <div className="h-60 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart 
                layout="vertical" 
                data={dataTypeDistribution} 
                margin={{ top: 5, right: 20, left: 30, bottom: 5 }}
              >
                <XAxis type="number" tick={{ fontSize: 10, fill: '#94a3b8' }} />
                <YAxis 
                  dataKey="name" 
                  type="category" 
                  tick={{ fontSize: 9, fill: '#94a3b8' }} 
                  width={110}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#0f172a', 
                    borderRadius: '12px', 
                    border: '1px solid #334155',
                    color: '#f8fafc',
                    fontSize: '12px'
                  }} 
                />
                <Bar dataKey="value" fill="#8b5cf6" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>

      {/* 4. Layer Quality & Density */}
      <div className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800/80 shadow-sm space-y-4 transition-all hover:shadow duration-200">
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-3">
              <span className="p-2 bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 rounded-full border border-emerald-100/50 dark:border-emerald-900/50 shrink-0">
                <ShieldCheck className="w-4 h-4 text-emerald-500" />
              </span>
              <span>Layer Quality &amp; Density</span>
            </h3>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 pl-11">
            Điểm chất lượng trung bình theo tầng dữ liệu.
          </p>

          <div className="h-52 w-full mt-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={qualityByLayer} margin={{ top: 10, right: 10, left: -25, bottom: 20 }}>
                <XAxis dataKey="layer" tick={{ fontSize: 9, fill: '#94a3b8' }} angle={-25} textAnchor="end" />
                <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} domain={[90, 100]} />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#0f172a', 
                    borderRadius: '12px', 
                    border: '1px solid #334155',
                    color: '#f8fafc',
                    fontSize: '12px'
                  }} 
                />
                <Bar dataKey="avgQuality" name="Quality Score" fill="#10b981" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* 5. Quick HITL Review Center (Actionable Queue) */}
      {pendingHitlCount > 0 && (
        <div className="bg-gradient-to-br from-orange-50/70 via-amber-50/40 to-orange-50/30 dark:from-orange-950/25 dark:via-slate-900/95 dark:to-slate-950 border border-orange-200/60 dark:border-orange-900/40 rounded-3xl p-6 shadow-sm text-slate-800 dark:text-slate-100 space-y-4 transition-all duration-300">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="p-2.5 rounded-full bg-orange-100/80 dark:bg-orange-950/60 text-orange-600 dark:text-orange-400 border border-orange-200/50 dark:border-orange-900/40 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </span>
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  HITL Review: {pendingHitlCount} Links
                </h3>
                <p className="text-xs text-slate-550 dark:text-slate-400 font-medium">
                  Liên kết AI đề xuất trong Dynamic SQL/Jinja cần kiểm duyệt.
                </p>
              </div>
            </div>

            <button
              onClick={() => onNavigateTab('hitl')}
              className="px-4 py-2 bg-orange-600 hover:bg-orange-500 dark:hover:bg-orange-500 text-white rounded-full text-xs font-bold flex items-center gap-1.5 shadow-sm cursor-pointer self-start sm:self-auto transition-all"
            >
              <span>Review Queue</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {hitlQueue.filter(h => h.status === 'pending').slice(0, 2).map((item) => (
              <div
                key={item.id}
                className="bg-white dark:bg-slate-900 p-4.5 rounded-3xl border border-slate-200 dark:border-slate-800/80 text-xs space-y-3 shadow-sm"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-mono font-bold text-slate-800 dark:text-slate-200 truncate">
                    `{item.sourceTable}` &rarr; `{item.targetTable}`
                  </div>
                  <span className="text-[10px] font-bold text-orange-700 dark:text-orange-400 bg-orange-50 dark:bg-orange-950/80 px-2.5 py-0.5 rounded-full border border-orange-200 dark:border-orange-900 shrink-0">
                    Confidence: {(item.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 dark:text-slate-400 line-clamp-2 leading-relaxed font-medium">
                  {item.reason}
                </p>
                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800/60">
                  <button
                    onClick={() => onRejectHITLEdge(item)}
                    className="px-3.5 py-1.5 border border-slate-250 dark:border-slate-700 text-slate-700 dark:text-slate-305 rounded-full text-[11px] font-bold hover:bg-slate-50 dark:hover:bg-slate-850 transition-colors cursor-pointer"
                  >
                    Reject
                  </button>
                  <button
                    onClick={() => onConfirmHITLEdge(item)}
                    className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-full text-[11px] font-bold transition-colors cursor-pointer flex items-center gap-1 shadow-sm"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Approve</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
};
