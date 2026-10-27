import React, { useState } from 'react';
import { X, Link } from 'lucide-react';
import { Workspace } from '../../types/workspace';

interface NewWorkspaceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreateWorkspace: (ws: Workspace) => void;
  editWorkspace?: Workspace | null;
}

const INPUT = "w-full px-3 py-2 bg-slate-50/50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800/50 rounded-xl text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-550 focus:outline-none focus:border-indigo-500 focus:bg-white dark:focus:bg-slate-900/70 focus:ring-1 focus:ring-indigo-500/20 transition-all font-semibold";
const LABEL = "block text-[9px] font-bold text-slate-450 dark:text-slate-500 uppercase tracking-wider mb-1";

export const NewWorkspaceModal: React.FC<NewWorkspaceModalProps> = ({ isOpen, onClose, onCreateWorkspace, editWorkspace }) => {
  const [name, setName] = useState(editWorkspace?.name || '');
  const [description, setDescription] = useState(editWorkspace?.description || '');

  if (!isOpen) return null;

  const handleCreate = () => {
    const ws: Workspace = {
      id: editWorkspace?.id || 'ws-' + Date.now(),
      name: name || 'New Workspace',
      description,
      tableCount: editWorkspace?.tableCount || 0,
      columnCount: editWorkspace?.columnCount || 0,
      edgeCount: editWorkspace?.edgeCount || 0,
      pendingCount: editWorkspace?.pendingCount || 0,
      createdAt: editWorkspace?.createdAt || new Date().toISOString(),
    };
    onCreateWorkspace(ws);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/50 dark:bg-black/60 backdrop-blur-md flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white/80 dark:bg-[#0F1420]/80 backdrop-blur-xl max-w-md w-full rounded-[24px] border border-slate-200/50 dark:border-slate-800/40 shadow-2xl overflow-hidden flex flex-col font-sans">
        <div className="p-4 border-b border-slate-200/50 dark:border-slate-800/40 flex items-center justify-between bg-slate-50/50 dark:bg-slate-900/20">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-indigo-500/10 dark:bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 flex items-center justify-center border border-indigo-500/20"><Link className="w-4 h-4" /></div>
            <div>
              <h2 className="text-sm font-extrabold text-slate-900 dark:text-white">{editWorkspace ? 'Edit Database' : 'Add Database'}</h2>
              <p className="text-[10px] text-slate-550 dark:text-slate-400 mt-0.5">Tạo 1 phiên làm việc mới để ingest SQL/dbt vào đó</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white hover:bg-slate-500/10 cursor-pointer transition-colors"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-4 space-y-2">
          <div><label className={LABEL}>Database Name</label><input value={name} onChange={e => setName(e.target.value)} placeholder="Ví dụ: analytics" className={INPUT} /></div>
          <div><label className={LABEL}>Description (optional)</label><input value={description} onChange={e => setDescription(e.target.value)} placeholder="Đường dẫn luồng dữ liệu phân tích..." className={INPUT} /></div>
        </div>

        <div className="p-4 border-t border-slate-200/50 dark:border-slate-800/40 flex items-center justify-end gap-2 bg-slate-50/50 dark:bg-slate-900/20">
          <button onClick={onClose} className="px-4 py-2 rounded-xl text-xs font-bold text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 border border-slate-200 dark:border-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-900/60 transition-all cursor-pointer font-sans">Cancel</button>
          <button onClick={handleCreate} className="px-4 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-650 text-white shadow-md shadow-indigo-600/20 transition-all cursor-pointer font-sans">
            {editWorkspace ? 'Save Changes' : 'Create Database'}
          </button>
        </div>
      </div>
    </div>
  );
};
