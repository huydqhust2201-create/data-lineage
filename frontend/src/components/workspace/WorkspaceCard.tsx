import React, { useState } from 'react';
import {
  Database,
  Table, GitBranch, AlertTriangle,
  ArrowRight, MoreHorizontal, Pencil, Trash2,
  FolderKanban, Star
} from 'lucide-react';
import { Workspace } from '../../types/workspace';

interface WorkspaceCardProps {
  workspace: Workspace;
  onOpen: (ws: Workspace) => void;
  onEdit: (ws: Workspace) => void;
  onDelete: (ws: Workspace) => void;
  isStarred: boolean;
  onToggleStar: (e: React.MouseEvent) => void;
}

export const WorkspaceCard: React.FC<WorkspaceCardProps> = ({ 
  workspace, 
  onOpen, 
  onEdit, 
  onDelete,
  isStarred,
  onToggleStar
}) => {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="group relative bg-white/40 dark:bg-slate-900/35 backdrop-blur-xl border border-white/25 dark:border-slate-800/40 rounded-[28px] hover:border-indigo-500/30 dark:hover:border-indigo-500/30 transition-all duration-300 hover:shadow-2xl hover:shadow-indigo-500/5 hover:-translate-y-1 flex flex-col p-6 space-y-5 overflow-hidden shadow-sm">
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-indigo-500 to-indigo-700" />
      <div className="absolute right-0 top-0 -mt-10 -mr-10 w-24 h-24 bg-indigo-500/5 dark:bg-indigo-500/10 rounded-full blur-2xl pointer-events-none group-hover:scale-150 transition-transform duration-500" />
      {/* Top Header Section */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 flex items-center justify-center shadow-sm group-hover:scale-105 transition-transform duration-300">
            <Database className="w-4 h-4" />
          </div>
          <div>
            <span className="text-[9px] font-bold text-slate-450 dark:text-slate-555 uppercase tracking-wider block">Database</span>
            <span className="text-xs font-extrabold text-slate-705 dark:text-slate-300">{workspace.name}</span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 relative z-10">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleStar(e);
            }}
            className={`p-1.5 rounded-full hover:bg-slate-500/10 dark:hover:bg-slate-500/20 transition-all cursor-pointer ${
              isStarred ? 'text-amber-500 opacity-100' : 'text-slate-400 hover:text-amber-450 opacity-100 lg:opacity-0 group-hover:opacity-100'
            }`}
            title={isStarred ? "Hủy đánh dấu sao" : "Đánh dấu sao"}
          >
            <Star className={`w-4 h-4 ${isStarred ? 'fill-amber-500 text-amber-500' : ''}`} />
          </button>

          <div className="relative">
            <button
              onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
              className="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-500/10 dark:hover:bg-slate-500/10 border border-transparent hover:border-slate-200 dark:hover:border-slate-800 transition-all cursor-pointer opacity-100 lg:opacity-0 group-hover:opacity-100"
            >
              <MoreHorizontal className="w-4 h-4" />
            </button>

          {menuOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
              <div className="absolute right-0 top-full mt-2 w-52 bg-white/90 dark:bg-slate-900/90 backdrop-blur-md border border-slate-250 dark:border-slate-800 rounded-2xl shadow-2xl z-50 py-1.5 overflow-hidden">
                <button
                  onClick={() => { onEdit(workspace); setMenuOpen(false); }}
                  className="w-full px-4 py-2.5 text-left text-xs text-slate-705 dark:text-slate-300 hover:bg-slate-500/10 dark:hover:bg-slate-500/10 flex items-center gap-2.5 cursor-pointer font-medium transition-colors"
                >
                  <Pencil className="w-4 h-4 text-indigo-500 dark:text-indigo-400" />
                  <span>Edit Details</span>
                </button>
                <div className="h-px bg-slate-200/50 dark:bg-slate-800/50 my-1.5" />
                <button
                  onClick={() => { onDelete(workspace); setMenuOpen(false); }}
                  className="w-full px-4 py-2.5 text-left text-xs text-rose-500 dark:text-rose-450 hover:bg-rose-500/10 dark:hover:bg-rose-500/10 flex items-center gap-2.5 cursor-pointer font-semibold transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                  <span>Delete Database</span>
                </button>
              </div>
            </>
          )}
        </div>
        </div>
      </div>

      {/* Main Info */}
      <div className="space-y-1.5">
        <h3 className="text-base font-extrabold text-slate-900 dark:text-white group-hover:text-indigo-650 dark:group-hover:text-indigo-400 transition-colors leading-snug truncate">
          {workspace.name}
        </h3>
        <p className="text-xs text-slate-550 dark:text-slate-400 line-clamp-2 leading-relaxed font-medium">
          {workspace.description || 'No detailed description available for this database.'}
        </p>
      </div>

      {/* Stats Block (Glassmorphic modern grid) */}
      <div className="grid grid-cols-2 gap-3 pt-1">
        {[
          { icon: <Table className="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400" />, label: 'Total Data Assets', value: workspace.tableCount, desc: 'Bảng & View' },
          { icon: <FolderKanban className="w-3.5 h-3.5 text-cyan-500 dark:text-cyan-400" />, label: 'Schema Columns', value: workspace.columnCount, desc: 'Cột' },
          { icon: <GitBranch className="w-3.5 h-3.5 text-emerald-500 dark:text-emerald-400" />, label: 'Lineage Edges', value: workspace.edgeCount, desc: 'Liên kết' },
          { icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400" />, label: 'HITL Review Queue', value: workspace.pendingCount, desc: 'Chờ duyệt' },
        ].map((s) => (
          <div key={s.label} className="p-3 bg-white/20 dark:bg-slate-900/30 border border-white/10 dark:border-slate-800/30 rounded-2xl flex flex-col justify-between hover:bg-white/30 dark:hover:bg-slate-900/40 transition-colors">
            <div className="flex items-center gap-1.5">
              {s.icon}
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider truncate">{s.label}</span>
            </div>
            <div className="mt-1 flex items-baseline gap-1">
              <p className="text-sm font-extrabold text-slate-900 dark:text-white">{s.value}</p>
              <span className="text-[9px] text-slate-400 dark:text-slate-505 font-medium">({s.desc})</span>
            </div>
          </div>
        ))}
      </div>

      {/* Primary Action Button (Material Design 3 pill-shaped glassmorphic accent) */}
      <button
        onClick={() => onOpen(workspace)}
        className="w-full py-3 rounded-full text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/10 hover:shadow-indigo-650/20 hover:-translate-y-0.5 active:translate-y-0 transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer mt-auto"
      >
        <span>Open Database</span>
        <ArrowRight className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};

interface CompactWorkspaceCardProps {
  workspace: Workspace;
  onOpen: (ws: Workspace) => void;
  isStarred: boolean;
  onToggleStar: (e: React.MouseEvent) => void;
}

export const CompactWorkspaceCard: React.FC<CompactWorkspaceCardProps> = ({
  workspace,
  onOpen,
  isStarred,
  onToggleStar,
}) => {
  return (
    <div
      onClick={() => onOpen(workspace)}
      className="group relative bg-white/40 dark:bg-slate-900/35 backdrop-blur-xl border border-white/25 dark:border-slate-800/40 rounded-[28px] p-5 hover:border-indigo-500/30 dark:hover:border-indigo-500/30 hover:shadow-2xl hover:shadow-indigo-500/5 transition-all duration-300 flex flex-col justify-between cursor-pointer h-[190px] shadow-sm overflow-hidden"
    >
      <div className="absolute right-0 top-0 -mt-10 -mr-10 w-20 h-20 bg-indigo-500/5 dark:bg-indigo-500/10 rounded-full blur-2xl pointer-events-none group-hover:scale-150 transition-transform duration-500" />

      {/* Top section: Database icon and Star button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 text-[10px] font-extrabold">
          <Database className="w-3.5 h-3.5" />
          <span>Database</span>
        </div>

        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleStar(e);
          }}
          className={`p-1.5 rounded-full hover:bg-slate-500/10 dark:hover:bg-slate-500/20 transition-all cursor-pointer relative z-10 ${
            isStarred ? 'text-amber-500 opacity-100' : 'text-slate-400 hover:text-amber-450 opacity-100 lg:opacity-0 group-hover:opacity-100'
          }`}
          title={isStarred ? "Hủy đánh dấu sao" : "Đánh dấu sao"}
        >
          <Star className={`w-4 h-4 ${isStarred ? 'fill-amber-500 text-amber-500' : ''}`} />
        </button>
      </div>

      {/* Title & Description */}
      <div className="mt-3 flex-1 flex flex-col justify-center">
        <h3 className="text-base font-extrabold text-slate-900 dark:text-white group-hover:text-indigo-650 dark:group-hover:text-indigo-400 transition-colors leading-snug truncate">
          {workspace.name}
        </h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 leading-relaxed mt-1 font-medium">
          {workspace.description || 'No detailed description available.'}
        </p>
      </div>

      {/* Bottom stats: Tables and columns */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-250/50 dark:border-slate-800/40 text-[10px] text-slate-500 dark:text-slate-400 font-bold mt-3">
        <div className="flex items-center gap-1">
          <Table className="w-3.5 h-3.5 text-indigo-500 dark:text-indigo-400" />
          <span>{workspace.tableCount} Assets</span>
        </div>
        <div className="flex items-center gap-1">
          <FolderKanban className="w-3.5 h-3.5 text-cyan-500 dark:text-cyan-400" />
          <span>{workspace.columnCount} Columns</span>
        </div>
      </div>
    </div>
  );
};
