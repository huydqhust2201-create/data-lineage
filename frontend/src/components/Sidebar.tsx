import React from 'react';
import logoImg from '../assets/logo.png';
import { 
  LayoutDashboard,
  Network, 
  Zap, 
  ShieldCheck, 
  FileCode, 
  Database, 
  FolderGit2,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Settings,
  Download,
  ArrowLeft
} from 'lucide-react';
import { ProjectData } from '../data/mockProjects';
import type { Database as WorkspaceDatabase } from '../api/database';

export type TabType = 'overview' | 'explorer' | 'impact' | 'hitl' | 'ingest' | 'catalog';

interface SidebarProps {
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
  isCollapsed: boolean;
  setIsCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
  projects: ProjectData[];
  selectedProjectId: string;
  onSelectProject: (id: string) => void;
  hitlPendingCount: number;
  onOpenSettings: () => void;
  onOpenExport?: () => void;
  workspaceName?: string;
  onBackToWorkspaces?: () => void;
  onLogout?: () => void;
  databases?: WorkspaceDatabase[];
  selectedDatabaseId?: number;
  onSelectDatabase?: (database: WorkspaceDatabase) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  isCollapsed,
  setIsCollapsed,
  projects,
  selectedProjectId,
  onSelectProject,
  hitlPendingCount,
  onOpenSettings,
  onOpenExport,
  workspaceName,
  onBackToWorkspaces,
  onLogout,
  databases = [],
  selectedDatabaseId,
  onSelectDatabase,
}) => {
  const currentProj = projects.find(p => p.id === selectedProjectId) || projects[0];

  interface NavItem {
    id: TabType;
    label: string;
    icon: any;
    badge?: string | number | null;
    badgeColor?: string;
  }

  const navItems: NavItem[] = [
    { 
      id: 'overview', 
      label: 'Overview', 
      icon: LayoutDashboard
    },
    { 
      id: 'explorer', 
      label: 'Lineage DAG', 
      icon: Network 
    },
    { 
      id: 'impact', 
      label: 'Impact & Risk', 
      icon: Zap
    },
    { 
      id: 'hitl', 
      label: 'HITL Queue', 
      icon: ShieldCheck, 
      badge: hitlPendingCount > 0 ? hitlPendingCount : null,
      badgeColor: 'bg-[#C2410C] text-white'
    },
    { 
      id: 'ingest', 
      label: 'Database to Lineage', 
      icon: FileCode
    },
    { 
      id: 'catalog', 
      label: 'Database & Catalog', 
      icon: Database
    },
  ];

  return (
    <aside
      className={`h-screen sticky top-0 z-40 bg-white dark:bg-[#0B0F19] border-r border-slate-200 dark:border-[#1E293B] flex flex-col justify-between transition-all duration-300 select-none shrink-0 ${
        isCollapsed ? 'w-20' : 'w-60'
      }`}
    >
      {/* Top Header & Brand */}
      <div className={`p-4 ${isCollapsed ? 'flex flex-col items-center gap-4' : 'space-y-4'}`}>
        {isCollapsed ? (
          /* Collapsed Mode */
          <div
            id="sidebar-collapsed-logo-toggle"
            onClick={() => setIsCollapsed(false)}
            className="relative group cursor-pointer mt-2"
            title="Mở rộng thanh điều hướng"
          >
            <div className="w-12 h-12 flex items-center justify-center transition-all group-hover:scale-105">
              <img src={logoImg} alt="Lineage AI Logo" className="w-12 h-12 object-contain transition-all duration-200 group-hover:opacity-0 group-hover:scale-75" />
              <ChevronRight className="w-5 h-5 absolute inset-0 m-auto text-slate-800 dark:text-white opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all duration-200" />
            </div>
          </div>
        ) : (
          /* Expanded Mode */
          <div className="space-y-4">
            <div className="flex items-start justify-between">
              <div
                onClick={() => setActiveTab('overview')}
                className="flex items-center gap-3 cursor-pointer overflow-hidden group"
                title="Lineage AI"
              >
                <div className="w-12 h-12 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
                  <img src={logoImg} alt="Lineage AI Logo" className="w-12 h-12 object-contain" />
                </div>

                <div className="min-w-0 mt-3">
                  <span className="font-extrabold text-base text-slate-900 dark:text-white tracking-tight leading-none flex items-center gap-1">
                    Lineage<span className="text-cyan-500 dark:text-cyan-400">AI</span>
                  </span>
                </div>
              </div>

              {/* Collapse Button */}
              <button
                id="sidebar-toggle-collapse-btn"
                onClick={() => setIsCollapsed(true)}
                className="p-1.5 rounded-xl border border-slate-200 dark:border-[#1E293B] hover:border-slate-400 hover:bg-slate-100 dark:hover:bg-[#131A26] transition-all text-slate-400 hover:text-slate-900 dark:hover:text-white cursor-pointer shrink-0 mt-0.5 animate-pulse-slow"
                title="Thu gọn"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
            </div>

            {/* Workspace Navigation & Display */}
            <div className="space-y-2">
              {onBackToWorkspaces && (
                <button
                  id="sidebar-back-to-workspaces-btn"
                  onClick={onBackToWorkspaces}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2.5 bg-slate-50 hover:bg-slate-100 dark:bg-[#131A26] dark:hover:bg-slate-900 border border-slate-200 dark:border-[#1E293B] rounded-xl text-xs font-bold text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-all cursor-pointer"
                >
                  <ArrowLeft className="w-3.5 h-3.5 text-slate-450 dark:text-slate-400" />
                  <span>Back to Workspaces</span>
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Center Navigation List */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;

          return (
            <div key={item.id} className="relative group">
              <button
                id={`sidebar-nav-${item.id}`}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex transition-all cursor-pointer ${
                  isCollapsed
                    ? 'flex-col items-center justify-center py-3.5 rounded-xl'
                    : 'flex-row items-center gap-3.5 px-4 py-3 rounded-2xl text-left'
                } ${
                  isActive
                    ? 'bg-indigo-50 dark:bg-[#1E1B4B] text-indigo-700 dark:text-white font-semibold'
                    : 'text-slate-600 dark:text-slate-350 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-[#131A26]/50'
                }`}
                title={isCollapsed ? item.label : undefined}
              >
                {isCollapsed ? (
                  <div className="flex flex-col items-center gap-1.5 w-full relative">
                    <Icon className={`w-5.5 h-5.5 ${isActive ? 'text-indigo-600 dark:text-indigo-300' : 'text-slate-500 dark:text-slate-400 group-hover:text-slate-805 dark:group-hover:text-slate-200'}`} />
                    {item.badge && (
                      <span className="absolute -top-2 -right-1 text-[8px] px-1 py-0.2 rounded-full font-bold bg-[#C2410C] text-white min-w-[14px] text-center">
                        {item.badge}
                      </span>
                    )}
                  </div>
                ) : (
                  <>
                    <Icon className={`w-4.5 h-4.5 shrink-0 ${isActive ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-500 dark:text-slate-400'}`} />
                    <span className="flex-1 text-[13px] font-bold truncate leading-none">
                      {item.label}
                    </span>
                    {item.badge && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-[#C2410C] text-white shrink-0">
                        {item.badge}
                      </span>
                    )}
                  </>
                )}
              </button>

              {/* Floating Tooltip in Collapsed Mode */}
              {isCollapsed && (
                <div className="absolute left-full top-1/2 -translate-y-1/2 ml-4 px-3 py-1.5 bg-slate-900 text-white text-xs rounded-xl shadow-xl border border-slate-850 dark:bg-[#131A26] dark:border-[#1E293B] whitespace-nowrap pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-50">
                  <div className="font-bold flex items-center gap-1.5">
                    <span>{item.label}</span>
                    {item.badge && (
                      <span className="px-1.5 py-0.2 text-[9px] bg-[#C2410C] rounded font-bold">
                        {item.badge}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Bottom Footer Actions */}
      <div className="p-4 space-y-3 border-t border-slate-200 dark:border-[#1E293B]">
        <div className={`flex ${isCollapsed ? 'flex-col items-center gap-3' : 'flex-col gap-2'}`}>
          {/* Export Button */}
          {onOpenExport && (
            <button
              onClick={onOpenExport}
              className={`w-full transition-all cursor-pointer flex items-center justify-center ${
                isCollapsed 
                  ? 'w-12 h-12 bg-indigo-50 hover:bg-indigo-100 dark:bg-[#1E1B4B] dark:hover:bg-[#25235C] rounded-2xl text-indigo-700 dark:text-indigo-300' 
                  : 'px-4 py-3 gap-2 rounded-2xl text-xs font-bold bg-indigo-50 hover:bg-indigo-100 dark:bg-[#1E1B4B] dark:hover:bg-[#25235C] border border-indigo-100 dark:border-[#312E81]/50 text-indigo-700 dark:text-indigo-300'
              }`}
              title="Export DB & Lineage"
            >
              <Download className="w-4 h-4 text-indigo-600 dark:text-indigo-400 shrink-0" />
              {!isCollapsed && <span>Export DB & Lineage</span>}
            </button>
          )}

          {/* Settings Button */}
          <button
            onClick={onOpenSettings}
            className={`w-full transition-all cursor-pointer flex items-center justify-center ${
              isCollapsed 
                ? 'w-12 h-12 hover:bg-slate-100 dark:hover:bg-[#131A26] rounded-2xl text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white' 
                : 'px-4 py-3 gap-2 rounded-2xl text-xs font-bold bg-transparent hover:bg-slate-100 dark:hover:bg-[#131A26] border border-slate-200 dark:border-[#1E293B] text-slate-700 dark:text-slate-300 hover:text-slate-950 dark:hover:text-white'
            }`}
            title="System Settings"
          >
            <Settings className="w-4 h-4 text-slate-500 dark:text-slate-450 shrink-0" />
            {!isCollapsed && <span>System Settings</span>}
          </button>
        </div>
      </div>
    </aside>
  );
};
