import React, { memo, useState, useEffect } from 'react';
import { Handle, Position } from '@xyflow/react';
import { LineageNodeData, ColumnDef } from '../types/lineage';
import { 
  Database, 
  Layers, 
  Table2, 
  FileCode2, 
  LayoutDashboard, 
  Cpu, 
  ArrowRightLeft, 
  Key, 
  ChevronDown, 
  ChevronUp, 
  Zap, 
  ShieldCheck, 
  AlertTriangle,
  Clock,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  Hash,
  Sparkles,
  GitCommit,
  Flame,
  ArrowRight
} from 'lucide-react';

export type LineageViewMode = 'compact' | 'full';

export interface AffectedColumnInfo {
  colName: string;
  type?: string;
  transformType?: string;
  isStartNode?: boolean;
  isPrimaryKey?: boolean;
  isForeignKey?: boolean;
  sourceCol?: string;
}

interface CustomTableNodeProps {
  data: LineageNodeData & {
    viewMode?: LineageViewMode;
    layoutDirection?: 'LR' | 'TB';
    isHighlighted?: boolean;
    isImpacted?: boolean;
    isUpstream?: boolean;
    isFocused?: boolean;
    isDirectNeighbor?: boolean;
    isDimmed?: boolean;
    selectedColumnName?: string | null;
    isColumnMatched?: boolean;
    affectedColumns?: AffectedColumnInfo[];
    onInspect?: (node: LineageNodeData) => void;
    onAnalyzeImpact?: (node: LineageNodeData) => void;
    onSelectColumn?: (nodeId: string, colName: string) => void;
    isExpanded?: boolean;
    onToggleExpand?: () => void;
  };
  selected?: boolean;
}

// Connector Logos & Badges (Atlan Style)
const connectorIcons: Record<string, { label: string; badgeColor: string; iconSymbol: string }> = {
  snowflake: { label: 'Snowflake', badgeColor: 'bg-sky-50 dark:bg-sky-950/60 text-sky-600 dark:text-sky-400 border-sky-200 dark:border-sky-800', iconSymbol: '❄️' },
  dbt: { label: 'dbt Core', badgeColor: 'bg-orange-50 dark:bg-orange-950/60 text-orange-600 dark:text-orange-400 border-orange-200 dark:border-orange-800', iconSymbol: '🟠' },
  postgres: { label: 'PostgreSQL', badgeColor: 'bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800', iconSymbol: '🐘' },
  bigquery: { label: 'BigQuery', badgeColor: 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800', iconSymbol: '🔷' },
  tableau: { label: 'Tableau', badgeColor: 'bg-purple-50 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 border-purple-200 dark:border-purple-800', iconSymbol: '📊' },
  powerbi: { label: 'Power BI', badgeColor: 'bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-800', iconSymbol: '🟡' },
  databricks: { label: 'Databricks', badgeColor: 'bg-red-50 dark:bg-red-950/60 text-red-600 dark:text-red-400 border-red-200 dark:border-red-800', iconSymbol: '🧱' },
  airflow: { label: 'Airflow', badgeColor: 'bg-teal-50 dark:bg-teal-950/60 text-teal-600 dark:text-teal-400 border-teal-200 dark:border-teal-800', iconSymbol: '🌪️' },
  kafka: { label: 'Kafka Stream', badgeColor: 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800', iconSymbol: '⚡' },
  s3: { label: 'AWS S3', badgeColor: 'bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-800', iconSymbol: '🪣' }
};

const layerBadgeStyles: Record<string, { bg: string; text: string; border: string; icon: any }> = {
  source: {
    bg: 'bg-cyan-50 dark:bg-cyan-950/40',
    text: 'text-cyan-700 dark:text-cyan-300',
    border: 'border-cyan-200 dark:border-cyan-800',
    icon: Database
  },
  staging: {
    bg: 'bg-emerald-50 dark:bg-emerald-950/40',
    text: 'text-emerald-700 dark:text-emerald-300',
    border: 'border-emerald-200 dark:border-emerald-800',
    icon: Layers
  },
  intermediate: {
    bg: 'bg-indigo-50 dark:bg-indigo-950/40',
    text: 'text-indigo-700 dark:text-indigo-300',
    border: 'border-indigo-200 dark:border-indigo-800',
    icon: FileCode2
  },
  marts: {
    bg: 'bg-amber-50 dark:bg-amber-950/40',
    text: 'text-amber-700 dark:text-amber-300',
    border: 'border-amber-200 dark:border-amber-800',
    icon: Table2
  },
  bi_dashboard: {
    bg: 'bg-rose-50 dark:bg-rose-950/40',
    text: 'text-rose-700 dark:text-rose-300',
    border: 'border-rose-200 dark:border-rose-800',
    icon: LayoutDashboard
  },
  feature_store: {
    bg: 'bg-purple-50 dark:bg-purple-950/40',
    text: 'text-purple-700 dark:text-purple-300',
    border: 'border-purple-200 dark:border-purple-800',
    icon: Cpu
  },
  reverse_etl: {
    bg: 'bg-blue-50 dark:bg-blue-950/40',
    text: 'text-blue-700 dark:text-blue-300',
    border: 'border-blue-200 dark:border-blue-800',
    icon: ArrowRightLeft
  }
};

export const CustomTableNode = memo(({ data, selected }: CustomTableNodeProps) => {
  const [localExpanded, setLocalExpanded] = useState(false);
  const isExpanded = data.isExpanded !== undefined ? data.isExpanded : localExpanded;
  const handleToggleExpand = data.onToggleExpand || (() => setLocalExpanded(prev => !prev));
  
  const viewMode = data.viewMode || 'compact';
  const isCompact = viewMode === 'compact';

  // Automatically collapse expanded columns when switching back to compact mode
  useEffect(() => {
    if (isCompact) {
      setLocalExpanded(false);
    }
  }, [isCompact]);

  // Determine connector
  const connectorKey = data.connector || (
    data.layer === 'source' ? 's3' : 
    data.layer === 'bi_dashboard' ? 'tableau' :
    data.layer === 'staging' || data.layer === 'intermediate' || data.layer === 'marts' ? 'dbt' : 'snowflake'
  );
  const connector = connectorIcons[connectorKey] || connectorIcons.dbt;

  // Layer style
  const style = layerBadgeStyles[data.layer] || layerBadgeStyles.marts;
  const LayerIcon = style.icon;

  // Atlan Certification & Tier defaults
  const certification = data.certification || (data.qualityScore && data.qualityScore > 98 ? 'VERIFIED' : 'DRAFT');
  const tier = data.tier || (data.layer === 'marts' || data.layer === 'bi_dashboard' ? 'Tier 1' : 'Tier 2');

  // Borders & Active Status
  let containerBorder = 'border-slate-200 dark:border-slate-800';
  let containerGlow = '';

  if (data.isImpacted) {
    containerBorder = 'border-rose-500 ring-2 ring-rose-400/40 animate-pulse';
    containerGlow = 'shadow-xl shadow-rose-500/10';
  } else if (data.isFocused) {
    containerBorder = 'border-indigo-600 ring-2 ring-indigo-500/60';
    containerGlow = 'shadow-xl shadow-indigo-500/30';
  } else if (data.selectedColumnName) {
    containerBorder = 'border-indigo-600 ring-2 ring-indigo-500/60';
    containerGlow = 'shadow-xl shadow-indigo-500/25';
  } else if (data.isColumnMatched || (data.affectedColumns && data.affectedColumns.length > 0)) {
    containerBorder = 'border-indigo-500 ring-2 ring-indigo-400/50';
    containerGlow = 'shadow-lg shadow-indigo-500/20';
  } else if (data.isDirectNeighbor) {
    containerBorder = 'border-indigo-400/80 ring-1 ring-indigo-400/30';
    containerGlow = 'shadow-md shadow-indigo-500/10';
  } else if (data.isUpstream) {
    containerBorder = 'border-sky-500 ring-2 ring-sky-400/40';
    containerGlow = 'shadow-md shadow-sky-500/10';
  } else if (selected) {
    containerBorder = 'border-indigo-600 ring-2 ring-indigo-500/40';
    containerGlow = 'shadow-lg shadow-indigo-500/15';
  }

  // Dimmed state for non-focused nodes during isolation
  const dimClass = data.isDimmed 
    ? 'opacity-20 hover:opacity-100 grayscale-[40%] hover:grayscale-0 transition-all duration-200 cursor-pointer' 
    : 'opacity-100';

  const widthClass = isCompact ? 'w-[260px]' : 'w-[300px]';

  return (
    <div
      id={`node-${data.id}`}
      onClick={() => data.onInspect?.(data)}
      className={`group ${widthClass} ${dimClass} rounded-2xl bg-white dark:bg-slate-900 border ${containerBorder} ${containerGlow} shadow-sm hover:shadow-xl transition-all duration-200 select-none text-left relative cursor-pointer`}
    >
      {/* Target input handle (Left or Top) */}
      <Handle
        type="target"
        position={data.layoutDirection === 'TB' ? Position.Top : Position.Left}
        id="in"
        className={`!w-3 !h-3 !bg-slate-400 dark:!bg-slate-600 group-hover:!bg-indigo-500 transition-colors border-2 border-white dark:border-slate-900 ${
          data.layoutDirection === 'TB' ? '!-top-1.5 !left-1/2 -translate-x-1/2' : '!-left-1.5 !top-1/2 -translate-y-1/2'
        }`}
      />

      {/* Top Atlan Asset Header Bar */}
      <div className={`p-3 border-b ${
        data.selectedColumnName || data.isFocused
          ? 'bg-indigo-50/70 dark:bg-indigo-950/40 border-indigo-100 dark:border-indigo-900/50'
          : 'border-slate-100 dark:border-slate-800/80'
      }`}>
        {/* Row 1: Connector & Certification & Tier */}
        <div className="flex items-center justify-between gap-1.5 mb-1.5">
          {/* Connector Badge with Icon */}
          <div className="flex items-center gap-1.5 min-w-0">
            <span 
              className={`px-1.5 py-0.5 rounded-md text-[10px] font-semibold flex items-center gap-1 border ${connector.badgeColor}`}
              title={`Ecosystem: ${connector.label}`}
            >
              <span className="text-[11px] leading-none">{connector.iconSymbol}</span>
              <span className="truncate max-w-[80px]">{connector.label}</span>
            </span>

            {/* Atlan Tier Badge */}
            <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
              tier === 'Tier 1' ? 'bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800' :
              'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700'
            }`}>
              {tier}
            </span>
          </div>

          {/* Atlan Certification Status Pill */}
          <div className="flex items-center gap-1 shrink-0">
            {certification === 'VERIFIED' ? (
              <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-semibold bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800" title="Verified Asset (Passed SLA & Governance)">
                <span>Verified</span>
              </span>
            ) : certification === 'DEPRECATED' ? (
              <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-semibold bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
                <span>Deprecated</span>
              </span>
            ) : (
              <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[9px] font-semibold bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
                <span>Draft</span>
              </span>
            )}
          </div>
        </div>

        {/* Row 2: Schema + Layer Tag */}
        <div className="flex items-center justify-between gap-1 mb-1">
          <div className="flex items-center gap-1 text-[10px] font-mono text-slate-400 dark:text-slate-500 truncate">
            <span className="truncate">{data.schema}</span>
          </div>
          <span className={`px-1.5 py-0.2 rounded text-[9px] font-medium ${style.bg} ${style.text}`}>
            {data.layer.replace('_', ' ')}
          </span>
        </div>

        {/* Row 3: Asset Table Name */}
        <div className="flex items-center justify-between">
          <h4 className="font-mono text-xs sm:text-sm font-bold text-slate-900 dark:text-slate-100 truncate group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors" title={data.name}>
            {data.name}
          </h4>
        </div>

        {/* Sub-meta (Rows & Quality Score) */}
        {!isCompact && (
          <div className="flex items-center justify-between mt-2 pt-1.5 border-t border-slate-100 dark:border-slate-800 text-[10px] text-slate-500 dark:text-slate-400">
            <div className="flex items-center gap-1">
              <span>{data.qualityScore || 99.5}% SLA</span>
            </div>
            {data.rowCount !== undefined && (
              <span>
                {data.rowCount >= 1000000 
                  ? `${(data.rowCount / 1000000).toFixed(1)}M rows` 
                  : `${(data.rowCount / 1000).toFixed(0)}k rows`}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Impact Alert Badge if flagged */}
      {data.isImpacted && (
        <div className="px-3 py-1 bg-rose-50 dark:bg-rose-950/60 border-b border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 text-[10px] flex items-center justify-between font-semibold">
          <div className="flex items-center gap-1">
            <span>Downstream Blast Risk</span>
          </div>
          <span className="text-[9px] font-medium">P0 Target</span>
        </div>
      )}

      {/* 1. COMPACT MODE (Action Bar & View columns toggle with direct CLL tracing) */}
      {isCompact && (
        <div className="p-2">
          {/* Action Row */}
          <div className="flex items-center justify-between gap-1.5">
            {/* View Columns dropdown button */}
            <button
              id={`compact-view-cols-${data.id}`}
              onClick={(e) => {
                e.stopPropagation();
                handleToggleExpand();
              }}
              className="flex-1 px-2 py-1 bg-slate-50 dark:bg-slate-800/80 text-slate-700 dark:text-slate-300 rounded-lg text-[10px] font-semibold flex items-center justify-center gap-1 border border-slate-200 dark:border-slate-700 cursor-pointer"
              title="Xem danh sách các trường trong bảng & truy vết CLL"
            >
              <Sparkles className="w-3 h-3 text-indigo-500" />
              <span>Columns ({data.columns.length})</span>
              {(isExpanded || Boolean(data.selectedColumnName)) ? (
                <ChevronUp className="w-3 h-3 text-slate-500" />
              ) : (
                <ChevronDown className="w-3 h-3 text-slate-500" />
              )}
            </button>

            {/* Impact Analysis Button */}
            <button
              id={`compact-impact-btn-${data.id}`}
              onClick={(e) => {
                e.stopPropagation();
                data.onAnalyzeImpact?.(data);
              }}
              className="px-2.5 py-1 bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 rounded-lg text-[10px] font-semibold flex items-center gap-1 border border-amber-200 dark:border-amber-800 cursor-pointer shrink-0"
              title="Phân tích tác động rủi ro hạ nguồn"
            >
              <Zap className="w-3 h-3 text-amber-500" />
              <span>Impact</span>
            </button>
          </div>

          {/* Expanded Column List in Compact Mode with CLL */}
          {(isExpanded || Boolean(data.selectedColumnName)) && (
            <div className="mt-2 pt-2 border-t border-slate-100 dark:border-slate-800 space-y-1 max-h-52 overflow-y-auto pr-0.5">
              <div className="text-[9px] text-slate-400 font-bold uppercase tracking-wider mb-1 flex items-center justify-between">
                <span className="flex items-center gap-1 text-indigo-600 dark:text-indigo-400">
                  <Sparkles className="w-2.5 h-2.5" />
                  <span>Chọn trường để truy vết CLL:</span>
                </span>
              </div>
              {data.columns.map((col, idx) => {
                const isSelectedCol = data.selectedColumnName === col.name;
                return (
                  <div
                    key={idx}
                    onClick={(e) => {
                      e.stopPropagation();
                      data.onSelectColumn?.(data.id, col.name);
                    }}
                    className={`relative flex items-center justify-between px-2 py-1.5 rounded-lg text-[10px] font-mono border cursor-pointer ${
                      isSelectedCol
                        ? 'bg-indigo-600 text-white border-indigo-600 font-bold shadow-sm ring-1 ring-indigo-400/50'
                        : 'bg-slate-50 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300 border-slate-200/80 dark:border-slate-800'
                    }`}
                  >
                    {/* Handles for Column-level wiring */}
                    <Handle
                      type="target"
                      position={Position.Left}
                      id={`in-col-${col.name}`}
                      className={`!w-2.5 !h-2.5 !-left-1.5 ${
                        isSelectedCol 
                          ? '!bg-amber-400 !border-2 !border-indigo-800 !opacity-100 shadow-sm' 
                          : '!bg-indigo-500 !opacity-0'
                      }`}
                    />

                    <div className="flex items-center gap-1.5 truncate">
                      {col.isPrimaryKey ? (
                        <Key className={`w-2.5 h-2.5 shrink-0 ${isSelectedCol ? 'text-amber-300' : 'text-amber-500'}`} />
                      ) : (
                        <GitCommit className={`w-2.5 h-2.5 shrink-0 ${isSelectedCol ? 'text-indigo-200' : 'text-slate-400'}`} />
                      )}
                      <span className="truncate">{col.name}</span>
                    </div>
                    
                    <div className="flex items-center gap-1 shrink-0">
                      {col.transformType && (
                        <span className={`text-[8px] px-1 py-0.2 rounded font-mono font-bold ${
                          isSelectedCol ? 'bg-indigo-800 text-indigo-100' : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
                        }`}>
                          {col.transformType}
                        </span>
                      )}
                      <span className={`text-[9px] uppercase ${isSelectedCol ? 'text-indigo-200' : 'text-slate-400'}`}>
                        {col.type}
                      </span>
                    </div>

                    <Handle
                      type="source"
                      position={Position.Right}
                      id={`out-col-${col.name}`}
                      className={`!w-2.5 !h-2.5 !-right-1.5 ${
                        isSelectedCol 
                          ? '!bg-amber-400 !border-2 !border-indigo-800 !opacity-100 shadow-sm' 
                          : '!bg-indigo-500 !opacity-0'
                      }`}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* 2. FULL MODE (Expanded Schema & Direct CLL Column Trace) */}
      {!isCompact && (
        <div className="p-2.5">
          <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400 mb-1.5 px-1">
            <span className="flex items-center gap-1 text-[10px] font-semibold text-slate-700 dark:text-slate-300">
              <Sparkles className="w-3 h-3 text-indigo-500" />
              <span>Columns ({data.columns.length})</span>
            </span>
            <button
              id={`toggle-cols-${data.id}`}
              onClick={(e) => {
                e.stopPropagation();
                handleToggleExpand();
              }}
              className="flex items-center gap-0.5 text-indigo-600 dark:text-indigo-400 hover:underline cursor-pointer text-[10px]"
            >
              {isExpanded ? 'Collapse' : 'Expand all'}
              {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          </div>

          <div className={`space-y-1 ${isExpanded ? 'max-h-none overflow-y-visible' : 'max-h-[170px] overflow-y-auto'} pr-0.5`}>
            {(isExpanded ? data.columns : data.columns.slice(0, 4)).map((col, idx) => {
              const isSelectedCol = data.selectedColumnName === col.name;
              return (
                <div
                  key={idx}
                  onClick={(e) => {
                    e.stopPropagation();
                    data.onSelectColumn?.(data.id, col.name);
                  }}
                  className={`relative flex items-center justify-between px-2 py-1.5 rounded-lg text-[10px] font-mono border cursor-pointer ${
                    isSelectedCol
                      ? 'bg-indigo-600 text-white border-indigo-600 font-bold shadow-sm ring-1 ring-indigo-400/50'
                      : 'bg-slate-50 dark:bg-slate-800/60 text-slate-800 dark:text-slate-200 border-slate-200/80 dark:border-slate-800'
                  }`}
                >
                  {/* Target handle on column */}
                  <Handle
                    type="target"
                    position={Position.Left}
                    id={`in-col-${col.name}`}
                    className={`!w-2.5 !h-2.5 !-left-1.5 ${
                      isSelectedCol 
                        ? '!bg-amber-400 !border-2 !border-indigo-800 !opacity-100 shadow-sm' 
                        : '!bg-indigo-500 !opacity-0'
                    }`}
                  />

                  <div className="flex items-center gap-1.5 truncate">
                    {col.isPrimaryKey ? (
                      <Key className={`w-3 h-3 shrink-0 ${isSelectedCol ? 'text-amber-300' : 'text-amber-500'}`} />
                    ) : (
                      <GitCommit className={`w-3 h-3 shrink-0 ${isSelectedCol ? 'text-indigo-200' : 'text-slate-400'}`} />
                    )}
                    <span className="truncate font-medium">
                      {col.name}
                    </span>
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    {col.transformType && (
                      <span className={`text-[8px] px-1 py-0.2 rounded font-mono font-bold ${
                        isSelectedCol ? 'bg-indigo-800 text-indigo-100' : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
                      }`}>
                        {col.transformType}
                      </span>
                    )}
                    <span className={`text-[9px] uppercase ${isSelectedCol ? 'text-indigo-200' : 'text-slate-400'}`}>
                      {col.type}
                    </span>
                  </div>

                  {/* Source handle on column */}
                  <Handle
                    type="source"
                    position={Position.Right}
                    id={`out-col-${col.name}`}
                    className={`!w-2.5 !h-2.5 !-right-1.5 ${
                      isSelectedCol 
                        ? '!bg-amber-400 !border-2 !border-indigo-800 !opacity-100 shadow-sm' 
                        : '!bg-indigo-500 !opacity-0'
                    }`}
                  />
                </div>
              );
            })}
            {!isExpanded && data.columns.length > 4 && (
              <div 
                onClick={(e) => {
                  e.stopPropagation();
                  handleToggleExpand();
                }}
                className="text-center text-[10px] text-indigo-600 dark:text-indigo-400 hover:underline pt-0.5 font-mono cursor-pointer"
              >
                +{data.columns.length - 4} more columns (click to expand)
              </div>
            )}
          </div>

          {/* Action Footer */}
          <div className="mt-2.5 pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center">
            <button
              id={`impact-btn-${data.id}`}
              onClick={(e) => {
                e.stopPropagation();
                data.onAnalyzeImpact?.(data);
              }}
              className="w-full px-2 py-1 bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800 rounded-lg text-[11px] font-medium flex items-center justify-center gap-1 cursor-pointer"
            >
              <Zap className="w-3 h-3 text-amber-500" />
              <span>Phân tích tác động (Impact Analysis)</span>
            </button>
          </div>
        </div>
      )}

      {/* AFFECTED FIELDS SECTION (Displayed on OTHER tables impacted by the clicked field) */}
      {data.affectedColumns && data.affectedColumns.length > 0 && !data.selectedColumnName && (
        <div className="mx-2.5 mb-2.5 p-2 bg-indigo-50/95 dark:bg-indigo-950/90 rounded-xl border border-indigo-200 dark:border-indigo-800 text-[10px] font-mono shadow-sm">
          <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-indigo-200/70 dark:border-indigo-800/70 font-bold text-indigo-800 dark:text-indigo-200 text-[10px]">
            <span className="flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-indigo-600 dark:text-indigo-400 shrink-0" />
              <span>Trường bị ảnh hưởng ({data.affectedColumns.length}):</span>
            </span>
            <span className="text-[8px] uppercase bg-indigo-200 dark:bg-indigo-900 text-indigo-800 dark:text-indigo-200 px-1.5 py-0.5 rounded font-bold">
              CLL Impact
            </span>
          </div>

          <div className="space-y-1.5">
            {data.affectedColumns.map((affCol, idx) => (
              <div
                key={idx}
                className="relative flex items-center justify-between px-2 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-indigo-300 dark:border-indigo-700 shadow-sm"
              >
                {/* Target Handle directly on this affected field row */}
                <Handle
                  type="target"
                  position={Position.Left}
                  id={`in-col-${affCol.colName}`}
                  className="!w-3 !h-3 !-left-1.5 !bg-emerald-500 border-2 border-white dark:border-slate-900 shadow-sm"
                />

                <div className="flex items-center gap-1.5 truncate">
                  {affCol.isPrimaryKey ? (
                    <Key className="w-3 h-3 text-amber-500 shrink-0" />
                  ) : (
                    <GitCommit className="w-3 h-3 text-indigo-500 shrink-0" />
                  )}
                  <span className="font-bold text-slate-800 dark:text-slate-100 truncate">{affCol.colName}</span>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  {affCol.transformType && (
                    <span className="text-[8px] font-semibold bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 px-1.5 py-0.5 rounded border border-indigo-200 dark:border-indigo-800">
                      {affCol.transformType}
                    </span>
                  )}
                  <span className="text-[9px] uppercase text-slate-500 dark:text-slate-400 font-bold">
                    {affCol.type || 'FIELD'}
                  </span>
                </div>

                {/* Source Handle directly on this affected field row for chaining to further downstream nodes */}
                <Handle
                  type="source"
                  position={Position.Right}
                  id={`out-col-${affCol.colName}`}
                  className="!w-3 !h-3 !-right-1.5 !bg-emerald-500 border-2 border-white dark:border-slate-900 shadow-sm"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Source output handle (Right or Bottom) */}
      <Handle
        type="source"
        position={data.layoutDirection === 'TB' ? Position.Bottom : Position.Right}
        id="out"
        className={`!w-3 !h-3 !bg-slate-400 dark:!bg-slate-600 group-hover:!bg-indigo-500 transition-colors border-2 border-white dark:border-slate-900 ${
          data.layoutDirection === 'TB' ? '!-bottom-1.5 !left-1/2 -translate-x-1/2' : '!-right-1.5 !top-1/2 -translate-y-1/2'
        }`}
      />
    </div>
  );
});

CustomTableNode.displayName = 'CustomTableNode';
