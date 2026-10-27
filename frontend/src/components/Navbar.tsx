import React from 'react';
import logoImg from '../assets/logo.png';
import { 
  LayoutDashboard,
  Network, 
  Zap, 
  ShieldCheck, 
  FileCode, 
  Bot, 
  Database, 
  Download, 
  Moon, 
  Sun, 
  Layers, 
  Sparkles, 
  AlertCircle,
  FolderGit2
} from 'lucide-react';
import { ProjectData } from '../data/mockProjects';

export type TabType = 'overview' | 'explorer' | 'impact' | 'hitl' | 'ingest' | 'copilot' | 'catalog';

interface NavbarProps {
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
  darkMode: boolean;
  setDarkMode: (val: boolean) => void;
  projects: ProjectData[];
  selectedProjectId: string;
  onSelectProject: (id: string) => void;
  hitlPendingCount: number;
  onOpenExport: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  darkMode,
  setDarkMode,
  projects,
  selectedProjectId,
  onSelectProject,
  hitlPendingCount,
  onOpenExport
}) => {
  interface TabItem {
    id: TabType;
    label: string;
    icon: any;
    badge: string | null;
    badgeColor?: string;
  }

  const tabs: TabItem[] = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard, badge: 'Hub' },
    { id: 'explorer', label: 'Lineage DAG', icon: Network, badge: null },
    { id: 'impact', label: 'Impact & Risk', icon: Zap, badge: 'Blast Radius' },
    { 
      id: 'hitl', 
      label: 'HITL Queue', 
      icon: ShieldCheck, 
      badge: hitlPendingCount > 0 ? `${hitlPendingCount} Review` : null,
      badgeColor: hitlPendingCount > 0 ? 'bg-orange-500 text-white' : 'bg-slate-200 text-slate-700'
    },
    { id: 'ingest', label: 'SQL Scanner', icon: FileCode, badge: 'sqlglot' },
    { id: 'copilot', label: 'Lineage Copilot', icon: Bot, badge: 'AI' },
    { id: 'catalog', label: 'Catalog', icon: Database, badge: null },
  ];

  return (
    <header className="sticky top-0 z-40 bg-white/95 dark:bg-slate-900/95 backdrop-blur border-b border-slate-200 dark:border-slate-800">
      <div className="w-full px-4 sm:px-6">
        <div className="flex items-center justify-between h-16 gap-4">
          {/* Brand Logo & Info */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="w-10 h-10 flex items-center justify-center">
              <img src={logoImg} alt="Lineage AI Logo" className="w-10 h-10 object-contain" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base tracking-tight text-slate-900 dark:text-white font-mono">
                  DATA-04
                </span>
                <span className="text-xs px-2 py-0.5 rounded-md font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-slate-900 dark:text-white border border-indigo-200 dark:border-indigo-800 flex items-center gap-1">
                  Lineage<span className="text-cyan-650 dark:text-cyan-400">AI</span>
                </span>
                <span className="hidden lg:inline-flex items-center text-[10px] px-1.5 py-0.5 rounded font-mono bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">
                  Baby Sharks (P-116)
                </span>
              </div>
              <p className="text-[11px] text-slate-500 dark:text-slate-400 hidden sm:block">
                Parser-First (sqlglot) + LLM Fallback (Gemini) + HITL
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="hidden md:flex items-center gap-1 bg-slate-100 dark:bg-slate-800/80 p-1 rounded-xl border border-slate-200/80 dark:border-slate-700/80">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  id={`nav-tab-${tab.id}`}
                  onClick={() => setActiveTab(tab.id as TabType)}
                  className={`relative flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 cursor-pointer ${
                    isActive
                      ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm font-semibold'
                      : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-white/50 dark:hover:bg-slate-800/50'
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400'}`} />
                  <span>{tab.label}</span>
                  {tab.badge && (
                    <span
                      className={`text-[9px] px-1.5 py-0.2 rounded-full font-mono font-medium ${
                        tab.badgeColor || 'bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300'
                      }`}
                    >
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          {/* Right Action Controls */}
          <div className="flex items-center gap-2">
            {/* Project Switcher */}
            <div className="relative hidden xl:flex items-center">
              <FolderGit2 className="w-3.5 h-3.5 absolute left-2.5 text-slate-400 pointer-events-none" />
              <select
                id="project-switcher"
                value={selectedProjectId}
                onChange={(e) => onSelectProject(e.target.value)}
                className="pl-8 pr-7 py-1.5 bg-slate-100 hover:bg-slate-200/70 dark:bg-slate-800 dark:hover:bg-slate-700/80 text-slate-800 dark:text-slate-200 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 transition-colors cursor-pointer appearance-none"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Export Button */}
            <button
              id="export-action-btn"
              onClick={onOpenExport}
              className="flex items-center gap-1.5 px-2.5 py-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 transition-colors cursor-pointer"
              title="Export Lineage Data as CSV / JSON"
            >
              <Download className="w-3.5 h-3.5 text-indigo-500" />
              <span className="hidden sm:inline">Export</span>
            </button>

            {/* Dark Mode Toggle */}
            <button
              id="darkmode-toggle-btn"
              onClick={() => setDarkMode(!darkMode)}
              className="p-2 rounded-lg text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 transition-colors cursor-pointer"
              title="Toggle Dark Mode"
            >
              {darkMode ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-600" />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Row */}
        <div className="md:hidden flex items-center gap-1 overflow-x-auto py-2 border-t border-slate-100 dark:border-slate-800">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as TabType)}
                className={`whitespace-nowrap flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium shrink-0 ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
                }`}
              >
                <Icon className="w-3 h-3" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
};
