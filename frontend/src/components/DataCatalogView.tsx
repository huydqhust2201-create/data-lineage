import React, { useState } from 'react';
import { LineageNodeData, LineageEdgeData } from '../types/lineage';
import { Search, Database, Layers, Key, Clock, ShieldCheck, Zap, ExternalLink, ChevronDown, ChevronRight } from 'lucide-react';

interface DataCatalogViewProps {
  nodes: LineageNodeData[];
  onSelectNodeInGraph: (nodeId: string) => void;
  onAnalyzeImpactForNode: (node: LineageNodeData) => void;
}

export const DataCatalogView: React.FC<DataCatalogViewProps> = ({
  nodes,
  onSelectNodeInGraph,
  onAnalyzeImpactForNode
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [layerFilter, setLayerFilter] = useState<string>('all');
  const [expandedNodeId, setExpandedNodeId] = useState<string | null>(null);

  const filteredNodes = nodes.filter(n => {
    const matchSearch = !searchTerm || 
      n.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      n.schema.toLowerCase().includes(searchTerm.toLowerCase()) ||
      n.columns.some(c => c.name.toLowerCase().includes(searchTerm.toLowerCase())) ||
      n.owner.toLowerCase().includes(searchTerm.toLowerCase());

    const matchLayer = layerFilter === 'all' || n.layer === layerFilter;
    return matchSearch && matchLayer;
  });

  return (
    <div className="w-full max-w-7xl mx-auto p-4 sm:p-6 space-y-6">
      {/* Header (styled like Database to Lineage header) */}
      <div className="bg-gradient-to-r from-indigo-50 via-slate-50 to-indigo-50 dark:from-slate-900 dark:via-indigo-950 dark:to-slate-900 border border-indigo-100 dark:border-slate-800 rounded-3xl p-6 sm:p-8 text-slate-900 dark:text-white shadow-xl flex flex-col lg:flex-row lg:items-center justify-between gap-6 transition-all duration-300">
        <div className="space-y-2 max-w-3xl">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-indigo-100 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-500/30">
              <Database className="w-5 h-5" />
            </span>
            <span className="text-[11px] font-semibold text-indigo-700 dark:text-indigo-300 uppercase tracking-wider">
              Governance Hub &bull; Data Dictionary
            </span>
          </div>
          
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Data Catalog &amp; Column Metadata
          </h1>
          
          <p className="text-xs sm:text-sm text-slate-650 dark:text-slate-350 leading-relaxed font-medium">
            Từ điển dữ liệu tập trung gồm {nodes.length} bảng và tài sản dữ liệu trải dài từ nguồn (Sources), Staging, Marts đến các báo cáo BI.
          </p>
        </div>

        {/* Search & Filter styled for light/dark banner */}
        <div className="flex items-center gap-2 lg:ml-auto">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-400" />
            <input
              type="text"
              placeholder="Search tables, columns..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-9 pr-3 py-1.5 w-64 text-xs bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl font-mono text-slate-800 dark:text-white placeholder-slate-400 dark:placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <select
            value={layerFilter}
            onChange={(e) => setLayerFilter(e.target.value)}
            className="px-3 py-1.5 text-xs bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl font-mono text-slate-800 dark:text-white cursor-pointer focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="all">All Layers</option>
            <option value="source">Sources</option>
            <option value="staging">Staging</option>
            <option value="intermediate">Intermediate</option>
            <option value="marts">Gold Marts</option>
            <option value="bi_dashboard">BI Dashboards</option>
            <option value="feature_store">Feature Store</option>
            <option value="reverse_etl">Reverse ETL</option>
          </select>
        </div>
      </div>

      {/* Catalog Table */}
      <div className="bg-slate-50 dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-100 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800 font-mono text-slate-500 dark:text-slate-400">
                <th className="py-3 px-4">Asset Name</th>
                <th className="py-3 px-4">Schema &amp; Layer</th>
                <th className="py-3 px-4">Quality &amp; Freshness</th>
                <th className="py-3 px-4">Owner</th>
                <th className="py-3 px-4">Columns</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-sans">
              {filteredNodes.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-400 font-mono text-xs">
                    No data assets match your search criteria.
                  </td>
                </tr>
              ) : (
                filteredNodes.map((node) => {
                  const isExpanded = expandedNodeId === node.id;
                  return (
                    <React.Fragment key={node.id}>
                      <tr className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors">
                        <td className="py-3.5 px-4">
                          <button
                            onClick={() => setExpandedNodeId(isExpanded ? null : node.id)}
                            className="flex items-center gap-2 text-left font-mono font-bold text-slate-900 dark:text-slate-100 hover:text-indigo-600 dark:hover:text-indigo-400 cursor-pointer"
                          >
                            {isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-slate-400" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-400" />}
                            <span>{node.name}</span>
                          </button>
                          <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-1">
                            {node.description || 'Chưa có mô tả'}
                          </p>
                          {node.description && (node.descriptionLabel || node.descriptionSource || node.descriptionIsStale) && (
                            <div className="mt-1 flex flex-wrap gap-1 text-[10px]">
                              {node.descriptionLabel && <span className="rounded bg-slate-200/70 px-1.5 py-0.5 text-slate-600 dark:bg-slate-700 dark:text-slate-300">{node.descriptionLabel}</span>}
                              {node.descriptionSource && <span className="rounded bg-slate-200/70 px-1.5 py-0.5 text-slate-600 dark:bg-slate-700 dark:text-slate-300">{node.descriptionSource}</span>}
                              {node.descriptionIsStale && <span className="rounded bg-amber-100 px-1.5 py-0.5 font-semibold text-amber-700 dark:bg-amber-950 dark:text-amber-300">Mô tả đã cũ</span>}
                            </div>
                          )}
                        </td>

                        <td className="py-3.5 px-4 font-mono">
                          <div className="text-[11px] font-semibold text-slate-700 dark:text-slate-300">
                            {node.schema}
                          </div>
                          <span className="inline-block mt-0.5 px-2 py-0.5 rounded text-[10px] uppercase font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                            {node.layer.replace('_', ' ')}
                          </span>
                        </td>

                        <td className="py-3.5 px-4 font-mono text-[11px]">
                          <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-bold">
                            <ShieldCheck className="w-3.5 h-3.5" />
                            <span>{node.qualityScore}%</span>
                          </div>
                          <div className="text-[10px] text-slate-400 flex items-center gap-1 mt-0.5">
                            <Clock className="w-3 h-3" />
                            <span>{node.freshness}</span>
                          </div>
                        </td>

                        <td className="py-3.5 px-4 text-slate-600 dark:text-slate-300 text-[11px]">
                          {node.owner}
                        </td>

                        <td className="py-3.5 px-4 font-mono text-slate-700 dark:text-slate-300">
                          {node.columns.length} cột
                        </td>

                        <td className="py-3.5 px-4 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => onAnalyzeImpactForNode(node)}
                              className="p-1.5 rounded-lg bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/40 dark:hover:bg-amber-900/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800 cursor-pointer"
                              title="Phân tích bán kính ảnh hưởng"
                            >
                              <Zap className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => onSelectNodeInGraph(node.id)}
                              className="p-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-950/40 dark:hover:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 cursor-pointer"
                              title="Xem trên biểu đồ Lineage DAG"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>

                      {/* Expanded Columns Sub-Row */}
                      {isExpanded && (
                        <tr className="bg-slate-50/50 dark:bg-slate-800/30">
                          <td colSpan={6} className="p-4 border-t border-slate-100 dark:border-slate-800">
                            <div className="space-y-3">
                              <h4 className="font-mono font-bold text-xs text-slate-800 dark:text-slate-200">
                                Columns &amp; Types for `{node.name}`:
                              </h4>
                              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                                {node.columns.map((c, i) => (
                                  <div
                                    key={i}
                                    className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-mono text-[11px] flex items-center justify-between"
                                  >
                                    <div className="flex items-center gap-1.5 truncate">
                                      {c.isPrimaryKey && (
                                        <span title="Primary Key">
                                          <Key className="w-3 h-3 text-amber-500 shrink-0" />
                                        </span>
                                      )}
                                      {!c.isPrimaryKey && c.isForeignKey && (
                                        <span
                                          title={c.referencesTable ? `Foreign Key → ${c.referencesTable}` : 'Foreign Key'}
                                          className="text-[9px] font-bold text-indigo-500 shrink-0"
                                        >
                                          FK
                                        </span>
                                      )}
                                      <span className="text-slate-900 dark:text-white font-semibold truncate">{c.name}</span>
                                      {c.isNullable === false && (
                                        <span title="NOT NULL" className="text-[9px] text-rose-400 shrink-0">
                                          NN
                                        </span>
                                      )}
                                    </div>
                                    <span
                                      className="text-[10px] text-slate-400 shrink-0"
                                      title={c.schemaOrigin === 'propagated' ? 'Kiểu suy ra qua cạnh direct (chưa khai báo tường minh)' : undefined}
                                    >
                                      {c.schemaOrigin === 'propagated' ? `~${c.type}` : c.type}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
