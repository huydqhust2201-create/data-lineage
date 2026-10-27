import React, { useState, useEffect, useRef } from 'react';
import { motion, Variants } from 'framer-motion';
import logoImg from '../../assets/logo.png';
import { 
  Network, ChevronDown, ChevronLeft, ChevronRight, Database, Plus, LogOut, Table, GitBranch, FolderKanban,
  Settings, HelpCircle, MessageSquare, Sun, Moon, AlertTriangle, ShieldCheck,
  LayoutDashboard, Star, Search, X
} from 'lucide-react';
import { Workspace } from '../../types/workspace';
import { WorkspaceCard, CompactWorkspaceCard } from './WorkspaceCard';
import { NewWorkspaceModal } from './NewWorkspaceModal';
import { AccountSettingsModal } from './AccountSettingsModal';

interface WorkspaceManagerProps {
  workspaces: Workspace[];
  workspaceName?: string;
  gateOpened?: boolean;
  setGateOpened?: (val: boolean) => void;
  onOpenWorkspace: (ws: Workspace) => void;
  onCreateWorkspace: (ws: Workspace) => void;
  onUpdateWorkspace: (ws: Workspace) => void;
  onDeleteWorkspace: (id: string) => void;
  onLogout: () => void;
  darkMode: boolean;
  setDarkMode: (val: boolean) => void;
  loadStats?: () => Promise<void>;
}

const leftWingVariants: Variants = {
  initial: {
    x: '0%',
    scale: 1,
    opacity: 1,
  },
  animate: {
    x: '-100%',
    scale: 0.95,
    opacity: 0,
    transition: {
      duration: 0.55,
      ease: [0.7, 0, 0.3, 1] as const,
    }
  }
};

const rightWingVariants: Variants = {
  initial: {
    x: '0%',
    scale: 1,
    opacity: 1,
  },
  animate: {
    x: '100%',
    scale: 0.95,
    opacity: 0,
    transition: {
      duration: 0.55,
      ease: [0.7, 0, 0.3, 1] as const,
    }
  }
};

const containerVariants: Variants = {
  initial: {
    scale: 0.95,
    opacity: 0,
  },
  animate: {
    scale: 1,
    opacity: 1,
    transition: {
      duration: 0.5,
      ease: [0.16, 1, 0.3, 1] as const,
      staggerChildren: 0.04,
      delayChildren: 0.1,
    },
  },
};

const sidebarVariants: Variants = {
  initial: {
    x: -40,
    opacity: 0,
  },
  animate: {
    x: 0,
    opacity: 1,
    transition: {
      duration: 0.4,
      ease: [0.16, 1, 0.3, 1] as const,
    },
  },
};

const headerVariants: Variants = {
  initial: {
    y: -20,
    opacity: 0,
  },
  animate: {
    y: 0,
    opacity: 1,
    transition: {
      duration: 0.4,
      ease: [0.16, 1, 0.3, 1] as const,
    },
  },
};

const childVariants: Variants = {
  initial: {
    y: 15,
    opacity: 0,
  },
  animate: {
    y: 0,
    opacity: 1,
    transition: {
      duration: 0.45,
      ease: [0.16, 1, 0.3, 1] as const,
    },
  },
};

export const WorkspaceManager: React.FC<WorkspaceManagerProps> = ({
  workspaces, workspaceName, gateOpened, setGateOpened, onOpenWorkspace, onCreateWorkspace, onUpdateWorkspace, onDeleteWorkspace, onLogout,
  darkMode, setDarkMode, loadStats
}) => {
  const [localTransitionComplete, setLocalTransitionComplete] = useState(gateOpened ?? false);
  const transitionComplete = gateOpened ?? localTransitionComplete;
  const [modalOpen, setModalOpen] = useState(false);
  const [editWs, setEditWs] = useState<Workspace | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // User Profile State
  const [accountModalOpen, setAccountModalOpen] = useState(false);
  const [userDisplayName, setUserDisplayName] = useState(() => localStorage.getItem('user_display_name') || 'Admin Account');
  const [userAvatarColor, setUserAvatarColor] = useState(() => localStorage.getItem('user_avatar_color') || 'indigo');
  const [userAvatarFile, setUserAvatarFile] = useState(() => localStorage.getItem('user_avatar_file'));

  const handleAccountSaveSuccess = () => {
    setUserDisplayName(localStorage.getItem('user_display_name') || 'Admin Account');
    setUserAvatarColor(localStorage.getItem('user_avatar_color') || 'indigo');
    setUserAvatarFile(localStorage.getItem('user_avatar_file'));
  };
  
  const [hubTab, setHubTab] = useState<'overview' | 'connections'>('overview');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'starred'>('all');
  const [starredIds, setStarredIds] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem('starred_database_ids') || '[]');
    } catch {
      return [];
    }
  });

  const toggleStar = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const newStarred = starredIds.includes(id)
      ? starredIds.filter(sid => sid !== id)
      : [...starredIds, id];
    setStarredIds(newStarred);
    localStorage.setItem('starred_database_ids', JSON.stringify(newStarred));
  };

  // Close user menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    if (userMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [userMenuOpen]);

  const totalDataAssets = workspaces.reduce((s, w) => s + w.tableCount, 0);
  const totalPending = workspaces.reduce((s, w) => s + w.pendingCount, 0);

  const handleEdit = (ws: Workspace) => { setEditWs(ws); setModalOpen(true); };
  const handleCreateOrUpdate = (ws: Workspace) => {
    if (editWs) onUpdateWorkspace(ws); else onCreateWorkspace(ws);
    setEditWs(null);
  };
  const handleDelete = (ws: Workspace) => setDeleteConfirm(ws.id);
  const confirmDelete = () => { if (deleteConfirm) { onDeleteWorkspace(deleteConfirm); setDeleteConfirm(null); } };

  // Filter and Search logic
  let filteredWorkspaces = [...workspaces];

  // Apply search filter first
  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase();
    filteredWorkspaces = filteredWorkspaces.filter(
      w => w.name.toLowerCase().includes(query) || (w.description && w.description.toLowerCase().includes(query))
    );
  }

  // Apply star filter
  if (filterType === 'starred') {
    filteredWorkspaces = filteredWorkspaces.filter(w => starredIds.includes(w.id));
  }

  return (
    <motion.div
      variants={containerVariants}
      initial="initial"
      animate="animate"
      style={{ willChange: 'transform, opacity' }}
      className="flex h-screen w-screen overflow-hidden bg-gradient-to-br from-slate-50 to-slate-100 dark:from-[#0B0F19] dark:to-[#060A13] text-slate-900 dark:text-white font-sans relative"
    >
      {/* Split Screen Reveal Overlay */}
      {!transitionComplete && (
        <div className="fixed inset-0 z-[9999] pointer-events-none overflow-hidden flex">
          {/* Left Wing */}
          <motion.div
            variants={leftWingVariants}
            initial="initial"
            animate="animate"
            onAnimationComplete={() => {
              setLocalTransitionComplete(true);
              if (setGateOpened) {
                setGateOpened(true);
              }
              if (loadStats) {
                loadStats();
              }
            }}
            className="absolute top-0 left-0 w-1/2 h-full bg-[#0B0F19] dark:bg-[#070A13] border-r border-[#1E293B] flex items-center justify-end pr-1.5 select-none pointer-events-none"
            style={{ willChange: 'transform, opacity' }}
          >
            <div className="flex items-center gap-3 select-none pointer-events-none">
              <img src={logoImg} alt="Lineage AI Logo" className="w-12 h-12 object-contain" />
              <span className="font-black text-white text-2xl tracking-tight">Lineage</span>
            </div>
          </motion.div>

          {/* Right Wing */}
          <motion.div
            variants={rightWingVariants}
            initial="initial"
            animate="animate"
            className="absolute top-0 right-0 w-1/2 h-full bg-[#0B0F19] dark:bg-[#070A13] border-l border-[#1E293B] flex items-center justify-start pl-1.5 select-none pointer-events-none"
            style={{ willChange: 'transform, opacity' }}
          >
            <div className="flex items-center select-none pointer-events-none">
              <span className="font-black text-indigo-400 text-2xl tracking-tight">AI</span>
            </div>
          </motion.div>
        </div>
      )}

      {/* Left Sidebar */}
      <motion.aside
        variants={sidebarVariants}
        style={{ willChange: 'transform, opacity' }}
        id="hub-sidebar-container"
        className={`h-screen bg-white/40 dark:bg-slate-900/35 backdrop-blur-xl border-r border-slate-200/50 dark:border-slate-800/40 flex flex-col justify-between transition-all duration-300 select-none shrink-0 ${
          isSidebarCollapsed ? 'w-20' : 'w-60'
        }`}
      >
        {/* Sidebar Top Section */}
        <div className={`p-4 flex flex-col ${isSidebarCollapsed ? 'items-center gap-4' : 'gap-4'}`}>
          {isSidebarCollapsed ? (
            <div
              onClick={() => setIsSidebarCollapsed(false)}
              className="relative group cursor-pointer mt-2"
              title="Expand Sidebar"
            >
              <div className="w-12 h-12 flex items-center justify-center transition-all group-hover:scale-105">
                <img src={logoImg} alt="Lineage AI Logo" className="w-12 h-12 object-contain transition-all duration-200 group-hover:opacity-0 group-hover:scale-75" />
                <ChevronRight className="w-5 h-5 absolute inset-0 m-auto text-slate-800 dark:text-white opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all duration-200" />
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 flex items-center justify-center">
                  <img src={logoImg} alt="Lineage AI Logo" className="w-10 h-10 object-contain" />
                </div>
                <div className="flex flex-col">
                  <span className="font-extrabold text-slate-900 dark:text-white text-sm tracking-tight leading-tight flex items-center gap-1">
                    Lineage<span className="text-cyan-500 dark:text-cyan-400">AI</span>
                  </span>
                  <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Workspace Hub</span>
                </div>
              </div>
              <button
                onClick={() => setIsSidebarCollapsed(true)}
                className="p-1.5 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-indigo-500/30 hover:bg-white/50 dark:hover:bg-slate-800/40 transition-all text-slate-400 dark:text-slate-450 hover:text-slate-900 dark:hover:text-white cursor-pointer"
                title="Collapse Sidebar"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Navigation Tab Menu Items */}
          <div className="space-y-1.5 pt-4 w-full">
            {/* Overview Tab Button */}
            <div className="relative group">
              <button
                onClick={() => setHubTab('overview')}
                className={`w-full transition-all duration-200 flex items-center cursor-pointer ${
                  isSidebarCollapsed 
                    ? 'w-12 h-12 justify-center rounded-2xl mx-auto' 
                    : 'px-4 py-3 gap-3 rounded-2xl text-left'
                } ${
                  hubTab === 'overview'
                    ? 'bg-indigo-500/10 dark:bg-indigo-500/15 text-indigo-650 dark:text-indigo-300 font-bold border border-indigo-500/20'
                    : 'text-slate-500 hover:text-slate-900 hover:bg-slate-500/5 dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-slate-500/5 font-medium border border-transparent'
                }`}
              >
                <LayoutDashboard className={`w-4.5 h-4.5 shrink-0 ${hubTab === 'overview' ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-450 dark:text-slate-400'}`} />
                {!isSidebarCollapsed && <span className="text-[13px]">Overview</span>}
              </button>
              {isSidebarCollapsed && (
                <div className="absolute left-full top-1/2 -translate-y-1/2 ml-4 px-3 py-1.5 bg-slate-900 text-white text-xs rounded-xl shadow-xl border border-slate-850 dark:bg-slate-900 dark:border-slate-800 whitespace-nowrap pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-50">
                  <span className="font-bold">Overview</span>
                </div>
              )}
            </div>

            {/* Connections Tab Button */}
            <div className="relative group">
              <button
                onClick={() => setHubTab('connections')}
                className={`w-full transition-all duration-200 flex items-center cursor-pointer ${
                  isSidebarCollapsed 
                    ? 'w-12 h-12 justify-center rounded-2xl mx-auto' 
                    : 'px-4 py-3 gap-3 rounded-2xl text-left'
                } ${
                  hubTab === 'connections'
                    ? 'bg-indigo-500/10 dark:bg-indigo-500/15 text-indigo-650 dark:text-indigo-300 font-bold border border-indigo-500/20'
                    : 'text-slate-500 hover:text-slate-900 hover:bg-slate-500/5 dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-slate-500/5 font-medium border border-transparent'
                }`}
              >
                <Database className={`w-4.5 h-4.5 shrink-0 ${hubTab === 'connections' ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-450 dark:text-slate-400'}`} />
                {!isSidebarCollapsed && <span className="text-[13px]">Databases</span>}
              </button>
              {isSidebarCollapsed && (
                <div className="absolute left-full top-1/2 -translate-y-1/2 ml-4 px-3 py-1.5 bg-slate-900 text-white text-xs rounded-xl shadow-xl border border-slate-850 dark:bg-slate-900 dark:border-slate-800 whitespace-nowrap pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-50">
                  <span className="font-bold">Databases</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar Footer Actions */}
        <div className="p-4 space-y-4 border-t border-slate-200/50 dark:border-slate-800/40">
          {/* Theme switcher */}
          <div className="relative group">
            <button
              onClick={() => setDarkMode(!darkMode)}
              className={`w-full transition-all duration-200 flex items-center cursor-pointer ${
                isSidebarCollapsed 
                  ? 'w-12 h-12 justify-center rounded-2xl bg-transparent hover:bg-slate-500/10 dark:hover:bg-slate-500/10 mx-auto' 
                  : 'px-4 py-2.5 gap-3 rounded-2xl hover:bg-slate-500/10 dark:hover:bg-slate-500/10 border border-transparent'
              } text-slate-500 hover:text-slate-950 dark:text-slate-400 dark:hover:text-slate-200 text-xs font-semibold`}
            >
              {darkMode ? <Moon className="w-4.5 h-4.5 shrink-0 text-amber-500" /> : <Sun className="w-4.5 h-4.5 shrink-0 text-yellow-500" />}
              {!isSidebarCollapsed && <span>{darkMode ? 'Dark Mode' : 'Light Mode'}</span>}
            </button>
            {isSidebarCollapsed && (
              <div className="absolute left-full top-1/2 -translate-y-1/2 ml-4 px-3 py-1.5 bg-slate-900 text-white text-xs rounded-xl shadow-xl border border-slate-850 dark:bg-slate-900 dark:border-slate-800 whitespace-nowrap pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-50">
                <span className="font-bold">{darkMode ? 'Dark Mode' : 'Light Mode'}</span>
              </div>
            )}
          </div>

          {/* Account Settings button */}
          <div className="relative group">
            <button
              onClick={() => setAccountModalOpen(true)}
              className={`w-full transition-all duration-200 flex items-center cursor-pointer ${
                isSidebarCollapsed 
                  ? 'w-12 h-12 justify-center rounded-2xl hover:bg-slate-500/10 dark:hover:bg-slate-500/10 mx-auto' 
                  : 'px-4 py-2.5 gap-3 rounded-2xl hover:bg-slate-500/10 dark:hover:bg-slate-500/10 border border-transparent'
              } text-slate-500 hover:text-slate-950 dark:text-slate-400 dark:hover:text-slate-200 text-xs font-semibold`}
            >
              <Settings className="w-4.5 h-4.5 shrink-0 text-slate-500 dark:text-slate-400" />
              {!isSidebarCollapsed && <span>Account Settings</span>}
            </button>
            {isSidebarCollapsed && (
              <div className="absolute left-full top-1/2 -translate-y-1/2 ml-4 px-3 py-1.5 bg-slate-900 text-white text-xs rounded-xl shadow-xl border border-slate-850 dark:bg-slate-900 dark:border-slate-800 whitespace-nowrap pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-50">
                <span className="font-bold">Settings</span>
              </div>
            )}
          </div>

          <div className="h-px bg-slate-200/50 dark:bg-slate-800/40 my-2" />

          {/* User info & Logout */}
          {isSidebarCollapsed ? (
            <div className="flex flex-col items-center gap-2.5 w-full">
              <div className="relative group flex justify-center w-full">
                <div className="relative cursor-pointer">
                  {userAvatarFile ? (
                    <img src={userAvatarFile} alt="Avatar" className="w-10 h-10 rounded-full object-cover border border-slate-300 dark:border-slate-800 shrink-0" />
                  ) : (
                    <div className={`w-10 h-10 rounded-2xl bg-gradient-to-br ${
                      userAvatarColor === 'emerald' ? 'from-emerald-500 to-teal-650' :
                      userAvatarColor === 'rose' ? 'from-rose-500 to-red-650' :
                      userAvatarColor === 'amber' ? 'from-amber-500 to-orange-655' :
                      userAvatarColor === 'sky' ? 'from-sky-500 to-sky-655' :
                      'from-indigo-500 to-purple-650'
                    } flex items-center justify-center text-white text-xs font-bold shrink-0 shadow-sm`}>
                      {userDisplayName.charAt(0).toUpperCase() || 'A'}
                    </div>
                  )}
                </div>
                <div className="absolute left-full top-1/2 -translate-y-1/2 ml-4 px-3 py-1.5 bg-slate-900 text-white text-xs rounded-xl shadow-xl border border-slate-850 dark:bg-slate-900 dark:border-slate-800 whitespace-nowrap pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-50">
                  <span className="font-bold">{userDisplayName}</span>
                </div>
              </div>

              <div className="relative group flex justify-center w-full">
                <button
                  onClick={() => onLogout()}
                  className="w-10 h-10 rounded-2xl hover:bg-rose-500/10 border border-transparent hover:border-rose-500/25 flex items-center justify-center text-rose-550 dark:text-rose-400 cursor-pointer transition-colors"
                  title="Log Out"
                >
                  <LogOut className="w-4 h-4 text-rose-550 dark:text-rose-400" />
                </button>
                <div className="absolute left-full top-1/2 -translate-y-1/2 ml-4 px-3 py-1.5 bg-slate-900 text-white text-xs rounded-xl shadow-xl border border-slate-850 dark:bg-slate-900 dark:border-slate-800 whitespace-nowrap pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-50">
                  <span className="font-bold text-rose-550 dark:text-rose-400">Log Out</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-2.5 mx-1">
              <div className="flex flex-col items-center justify-center p-2.5 bg-white/20 dark:bg-slate-900/20 backdrop-blur-md rounded-2xl border border-white/10 dark:border-slate-800/30 gap-2">
                {userAvatarFile ? (
                  <img src={userAvatarFile} alt="Avatar" className="w-11 h-11 rounded-full object-cover border border-slate-200 dark:border-slate-800 shadow-md shrink-0" />
                ) : (
                  <div className={`w-11 h-11 rounded-2xl bg-gradient-to-br ${
                    userAvatarColor === 'emerald' ? 'from-emerald-500 to-teal-650' :
                    userAvatarColor === 'rose' ? 'from-rose-500 to-red-650' :
                    userAvatarColor === 'amber' ? 'from-amber-500 to-orange-655' :
                    userAvatarColor === 'sky' ? 'from-sky-500 to-sky-655' :
                    'from-indigo-500 to-purple-650'
                  } flex items-center justify-center text-white text-xs font-bold shrink-0 shadow-lg shadow-indigo-500/10`}>
                    {userDisplayName.charAt(0).toUpperCase() || 'A'}
                  </div>
                )}
                <div className="text-center min-w-0">
                  <span className="text-[11px] text-slate-850 dark:text-slate-300 font-bold block truncate leading-none mb-0.5">{userDisplayName}</span>
                  <span className="text-[8px] text-slate-450 dark:text-slate-500 uppercase tracking-widest block leading-none font-bold">Administrator</span>
                </div>
              </div>

              <button
                onClick={() => onLogout()}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-rose-550/10 hover:bg-rose-550/20 border border-rose-500/10 hover:border-rose-500/20 rounded-2xl text-xs font-bold text-rose-600 dark:text-rose-400 hover:text-rose-700 dark:hover:text-rose-300 transition-all cursor-pointer shadow-sm hover:shadow-rose-500/5 active:scale-[0.98]"
                title="Log Out"
              >
                <LogOut className="w-3.5 h-3.5 shrink-0 text-rose-550 dark:text-rose-455" />
                <span>Log Out</span>
              </button>
            </div>
          )}
        </div>
      </motion.aside>

      {/* Main Content Area */}
      <main className="flex-1 h-screen flex flex-col overflow-hidden relative">
        {/* Compact Telemetry KPI Header Row */}
        <motion.header
          variants={headerVariants}
          style={{ willChange: 'transform, opacity' }}
          className="h-20 border-b border-slate-200 dark:border-[#1E293B] bg-white dark:bg-[#080C15] flex items-center justify-between px-8 shrink-0 z-10 select-none"
        >
          <div className="flex items-center gap-2">
            <h1 className="text-base sm:text-lg font-extrabold text-slate-900 dark:text-white tracking-wider uppercase font-sans">
              {hubTab === 'overview' ? 'Workspace Overview' : 'Databases'}
            </h1>
          </div>
          
          <div className="flex items-center gap-6 sm:gap-10">
            {/* Database count */}
            <div className="flex items-center gap-3 border-r border-slate-200 dark:border-[#1E293B]/80 pr-6 sm:pr-10">
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-450 animate-pulse" />
              <div className="text-left">
                <span className="text-[10px] sm:text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest block leading-tight">Databases</span>
                {transitionComplete ? (
                  <span className="text-sm sm:text-base font-black text-slate-800 dark:text-white leading-none mt-1 block">{workspaces.length}</span>
                ) : (
                  <div className="h-4 w-8 bg-slate-200 dark:bg-slate-800 rounded animate-pulse mt-1" />
                )}
              </div>
            </div>

            {/* Total Data Assets */}
            <div className="flex items-center gap-3 border-r border-slate-200 dark:border-[#1E293B]/80 pr-6 sm:pr-10">
              <Table className="w-5 h-5 text-cyan-600 dark:text-cyan-400" />
              <div className="text-left">
                <span className="text-[10px] sm:text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest block leading-tight">Total Assets</span>
                {transitionComplete ? (
                  <span className="text-sm sm:text-base font-black text-slate-800 dark:text-white leading-none mt-1 block">{totalDataAssets}</span>
                ) : (
                  <div className="h-4 w-12 bg-slate-200 dark:bg-slate-800 rounded animate-pulse mt-1" />
                )}
              </div>
            </div>

            {/* HITL Attention */}
            <div className="flex items-center gap-3 border-r border-slate-200 dark:border-[#1E293B]/80 pr-6 sm:pr-10">
              <AlertTriangle className={`w-5 h-5 ${totalPending > 0 && transitionComplete ? 'text-amber-500 animate-bounce' : 'text-slate-400 dark:text-slate-500'}`} />
              <div className="text-left">
                <span className="text-[10px] sm:text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest block leading-tight">Attention</span>
                {transitionComplete ? (
                  <span className={`text-sm sm:text-base font-black leading-none mt-1 block ${totalPending > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-800 dark:text-white'}`}>{totalPending}</span>
                ) : (
                  <div className="h-4 w-8 bg-slate-200 dark:bg-slate-800 rounded animate-pulse mt-1" />
                )}
              </div>
            </div>
          </div>
        </motion.header>

        {/* Content Area with smooth transitions */}
        <div className="flex-1 overflow-y-auto p-6 pb-24 relative custom-scrollbar">
          {hubTab === 'overview' ? (
            <div className="space-y-6">
              {/* Header Banner - single workspace and its databases */}
              <motion.div
                variants={childVariants}
                style={{ willChange: 'transform, opacity' }}
                className="bg-white/80 dark:bg-[#0B0F19]/85 backdrop-blur-md border border-slate-200 dark:border-[#1E293B] rounded-[24px] p-6 sm:p-8 text-slate-900 dark:text-white shadow-lg flex flex-col justify-between gap-6 transition-all duration-300 relative overflow-hidden"
              >
                <div className="absolute right-0 top-0 -mt-10 -mr-10 w-40 h-40 bg-indigo-500/5 dark:bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
                <div className="space-y-2 max-w-3xl relative pl-5 before:absolute before:left-0 before:top-1 before:bottom-1 before:w-1 bg-gradient-to-b before:from-indigo-500 before:to-indigo-700 before:rounded-full">
                  <h1 className="text-xl sm:text-2xl font-black tracking-tight text-slate-900 dark:text-white font-sans">
                    Workspace: {workspaceName || 'Default'}
                  </h1>
                  
                  <p className="text-xs text-slate-550 dark:text-slate-400 leading-relaxed font-medium">
                    Chào mừng bạn đến với trung tâm quản lý Lineage AI. Vui lòng chọn một cơ sở dữ liệu bên dưới để bắt đầu phân tích sơ đồ luồng dữ liệu (Lineage DAG), import schema mới (Ingest), kiểm duyệt các thay đổi (HITL Queue) hoặc đánh giá mức độ ảnh hưởng của schema.
                  </p>
                </div>
              </motion.div>

              {/* Search & Filter Controls */}
              {workspaces.length > 0 && (
                <motion.div
                  variants={childVariants}
                  style={{ willChange: 'transform, opacity' }}
                  className="flex flex-col sm:flex-row gap-4 items-center justify-between mt-6"
                >
                  {/* Filter buttons: All / Starred */}
                  <div className="flex items-center gap-1.5 bg-slate-100 dark:bg-slate-900/60 p-1 rounded-full border border-slate-200 dark:border-slate-800/80 w-full sm:w-auto">
                    <button
                      onClick={() => setFilterType('all')}
                      className={`px-4 py-2 rounded-full text-xs font-bold transition-all cursor-pointer ${
                        filterType === 'all'
                          ? 'bg-white dark:bg-slate-800 text-indigo-655 dark:text-indigo-400 shadow-sm border border-slate-200 dark:border-slate-800'
                          : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                      }`}
                    >
                      All Databases
                    </button>
                    <button
                      onClick={() => setFilterType('starred')}
                      className={`px-4 py-2 rounded-full text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                        filterType === 'starred'
                          ? 'bg-white dark:bg-slate-800 text-amber-500 dark:text-amber-400 shadow-sm border border-slate-200 dark:border-slate-800'
                          : 'text-slate-500 dark:text-slate-400 hover:text-amber-500 dark:hover:text-amber-400'
                      }`}
                    >
                      <Star className={`w-3.5 h-3.5 ${filterType === 'starred' ? 'fill-amber-500' : ''}`} />
                      <span>Starred ({starredIds.length})</span>
                    </button>
                  </div>

                  {/* Search input */}
                  <div className="relative w-full sm:w-80">
                    <input
                      type="text"
                      placeholder="Search database name or description..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full pl-10 pr-10 py-2.5 bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800 rounded-full text-xs font-semibold text-slate-800 dark:text-slate-250 placeholder-slate-400 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/30 transition-all font-sans"
                    />
                    <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
                    {searchQuery && (
                      <button
                        onClick={() => setSearchQuery('')}
                        className="p-1 rounded-full text-slate-400 hover:text-slate-600 dark:hover:text-white absolute right-3.5 top-2 hover:bg-slate-200/50 dark:hover:bg-slate-800/50 transition-colors"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </motion.div>
              )}

              {!transitionComplete ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="bg-white/40 dark:bg-slate-900/35 backdrop-blur-xl border border-slate-200/50 dark:border-slate-800/40 rounded-[28px] p-6 h-36 animate-pulse flex flex-col justify-between">
                      <div className="space-y-3">
                        <div className="h-4 bg-slate-200 dark:bg-slate-800 rounded w-1/3" />
                        <div className="h-3 bg-slate-200 dark:bg-slate-800 rounded w-2/3" />
                      </div>
                      <div className="flex gap-4">
                        <div className="h-3.5 bg-slate-200 dark:bg-slate-800 rounded w-1/4" />
                        <div className="h-3.5 bg-slate-200 dark:bg-slate-800 rounded w-1/4" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : workspaces.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 border border-dashed border-slate-200 dark:border-[#1E293B] rounded-[32px] bg-slate-100/30 dark:bg-[#0B0F19]/40 text-center px-4">
                  <div className="p-4 rounded-full bg-slate-100 border border-slate-200 dark:bg-slate-900 dark:border-slate-800 text-slate-400 dark:text-slate-500 mb-4 shadow-inner">
                    <Database className="w-8 h-8" />
                  </div>
                  <h3 className="text-base font-bold text-slate-800 dark:text-slate-300">Chưa có database</h3>
                  <p className="text-xs text-slate-500 mt-2 max-w-md leading-relaxed font-medium">
                    Thêm database đầu tiên vào workspace này.
                  </p>
                  <button onClick={() => { setHubTab('connections'); setModalOpen(true); }} className="px-5 py-3 rounded-full text-xs font-bold bg-white border border-slate-250 hover:border-slate-400 dark:bg-[#131A26] dark:border-[#1E293B] dark:hover:border-slate-500 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-900 dark:hover:text-white transition-all shadow-md font-sans">
                    Thêm database
                  </button>
                </div>
              ) : filteredWorkspaces.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 border border-dashed border-slate-200 dark:border-[#1E293B] rounded-[32px] bg-slate-100/30 dark:bg-[#0B0F19]/40 text-center px-4">
                  <div className="p-4 rounded-full bg-slate-100 border border-slate-200 dark:bg-slate-900 dark:border-slate-800 text-slate-400 dark:text-slate-500 mb-4 shadow-inner">
                    <Database className="w-8 h-8" />
                  </div>
                  <h3 className="text-base font-bold text-slate-800 dark:text-slate-300">No databases match your filter</h3>
                  <p className="text-xs text-slate-500 mt-2 max-w-md leading-relaxed font-medium">
                    Try adjusting your search query or switching from Starred to All databases.
                  </p>
                  <button 
                    onClick={() => { setSearchQuery(''); setFilterType('all'); }} 
                    className="px-5 py-3 rounded-full text-xs font-bold bg-white border border-slate-250 hover:border-slate-400 dark:bg-[#131A26] dark:border-[#1E293B] dark:hover:border-slate-500 text-slate-705 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-900 dark:hover:text-white transition-all shadow-md font-sans mt-4 cursor-pointer"
                  >
                    Clear Search & Filters
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {filteredWorkspaces.map(w => (
                    <motion.div key={w.id} variants={childVariants} style={{ willChange: 'transform, opacity' }}>
                      <CompactWorkspaceCard
                        workspace={w}
                        onOpen={onOpenWorkspace}
                        isStarred={starredIds.includes(w.id)}
                        onToggleStar={(e) => toggleStar(w.id, e)}
                      />
                    </motion.div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-6">
              {/* Header Banner - database list */}
              <motion.div
                variants={childVariants}
                style={{ willChange: 'transform, opacity' }}
                className="bg-white/80 dark:bg-[#0B0F19]/85 backdrop-blur-md border border-slate-200 dark:border-[#1E293B] rounded-[24px] p-6 sm:p-8 text-slate-900 dark:text-white shadow-lg flex flex-col lg:flex-row lg:items-center justify-between gap-6 transition-all duration-300 relative overflow-hidden"
              >
                <div className="absolute right-0 top-0 -mt-10 -mr-10 w-40 h-40 bg-emerald-500/5 dark:bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />
                <div className="space-y-2 max-w-3xl relative pl-5 before:absolute before:left-0 before:top-1 before:bottom-1 before:w-1 bg-gradient-to-b before:from-emerald-500 before:to-emerald-700 before:rounded-full">
                  <h1 className="text-xl sm:text-2xl font-black tracking-tight text-slate-900 dark:text-white font-sans">
                    Database Connections
                  </h1>
                  
                  <p className="text-xs text-slate-550 dark:text-slate-400 leading-relaxed font-medium">
                    Quản lý danh sách các cơ sở dữ liệu đã liên kết với Workspace của bạn. Chọn một database để khám phá dữ liệu hoặc thêm kết nối database mới để phân tích luồng dữ liệu lineage tương ứng.
                  </p>
                </div>

                <button 
                  onClick={() => { setEditWs(null); setModalOpen(true); }} 
                  className="px-5 py-3 rounded-full text-xs font-bold bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-650 text-white shadow-md shadow-indigo-600/20 hover:-translate-y-0.5 hover:shadow-indigo-500/30 transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer shrink-0 font-sans border border-indigo-500/25"
                >
                  <Plus className="w-4 h-4" />
                  <span>Add Database</span>
                </button>
              </motion.div>

              {/* Search & Filter Controls */}
              {workspaces.length > 0 && (
                <motion.div
                  variants={childVariants}
                  style={{ willChange: 'transform, opacity' }}
                  className="flex flex-col sm:flex-row gap-4 items-center justify-between mt-6"
                >
                  {/* Filter buttons: All / Starred */}
                  <div className="flex items-center gap-1.5 bg-slate-100 dark:bg-slate-900/60 p-1 rounded-full border border-slate-200 dark:border-slate-800/80 w-full sm:w-auto">
                    <button
                      onClick={() => setFilterType('all')}
                      className={`px-4 py-2 rounded-full text-xs font-bold transition-all cursor-pointer ${
                        filterType === 'all'
                          ? 'bg-white dark:bg-slate-800 text-indigo-655 dark:text-indigo-400 shadow-sm border border-slate-200 dark:border-slate-800'
                          : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                      }`}
                    >
                      All Databases
                    </button>
                    <button
                      onClick={() => setFilterType('starred')}
                      className={`px-4 py-2 rounded-full text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                        filterType === 'starred'
                          ? 'bg-white dark:bg-slate-800 text-amber-500 dark:text-amber-400 shadow-sm border border-slate-200 dark:border-slate-800'
                          : 'text-slate-500 dark:text-slate-400 hover:text-amber-500 dark:hover:text-amber-400'
                      }`}
                    >
                      <Star className={`w-3.5 h-3.5 ${filterType === 'starred' ? 'fill-amber-500' : ''}`} />
                      <span>Starred ({starredIds.length})</span>
                    </button>
                  </div>

                  {/* Search input */}
                  <div className="relative w-full sm:w-80">
                    <input
                      type="text"
                      placeholder="Search database name or description..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full pl-10 pr-10 py-2.5 bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800 rounded-full text-xs font-semibold text-slate-800 dark:text-slate-250 placeholder-slate-400 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/30 transition-all font-sans"
                    />
                    <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
                    {searchQuery && (
                      <button
                        onClick={() => setSearchQuery('')}
                        className="p-1 rounded-full text-slate-400 hover:text-slate-600 dark:hover:text-white absolute right-3.5 top-2 hover:bg-slate-200/50 dark:hover:bg-slate-800/50 transition-colors"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </motion.div>
              )}


              {!transitionComplete ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 font-sans">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="bg-white/40 dark:bg-slate-900/35 backdrop-blur-xl border border-slate-200/50 dark:border-slate-800/40 rounded-[28px] p-6 h-36 animate-pulse flex flex-col justify-between">
                      <div className="space-y-3">
                        <div className="h-4 bg-slate-200 dark:bg-slate-800 rounded w-1/3" />
                        <div className="h-3 bg-slate-200 dark:bg-slate-800 rounded w-2/3" />
                      </div>
                      <div className="flex gap-4">
                        <div className="h-3.5 bg-slate-200 dark:bg-slate-800 rounded w-1/4" />
                        <div className="h-3.5 bg-slate-200 dark:bg-slate-800 rounded w-1/4" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : workspaces.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 border border-dashed border-slate-200 dark:border-[#1E293B] rounded-[32px] bg-slate-100/30 dark:bg-[#0B0F19]/40 text-center px-4">
                  <div className="p-4 rounded-full bg-slate-100 border border-slate-200 dark:bg-slate-900 dark:border-slate-800 text-slate-400 dark:text-slate-500 mb-4 shadow-inner">
                    <Database className="w-8 h-8" />
                  </div>
                  <h3 className="text-base font-bold text-slate-800 dark:text-slate-300">No databases found</h3>
                  <p className="text-xs text-slate-500 mt-2 max-w-md leading-relaxed font-medium">
                    Create the first database in this workspace.
                  </p>
                  <button onClick={() => setModalOpen(true)} className="px-5 py-3 rounded-full text-xs font-bold bg-white border border-slate-250 hover:border-slate-400 dark:bg-[#131A26] dark:border-[#1E293B] dark:hover:border-slate-500 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-900 dark:hover:text-white transition-all shadow-md font-sans">
                    Add Database
                  </button>
                </div>
              ) : filteredWorkspaces.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 border border-dashed border-slate-200 dark:border-[#1E293B] rounded-[32px] bg-slate-100/30 dark:bg-[#0B0F19]/40 text-center px-4">
                  <div className="p-4 rounded-full bg-slate-100 border border-slate-200 dark:bg-slate-900 dark:border-slate-800 text-slate-400 dark:text-slate-500 mb-4 shadow-inner">
                    <Database className="w-8 h-8" />
                  </div>
                  <h3 className="text-base font-bold text-slate-800 dark:text-slate-300">No databases match your filter</h3>
                  <p className="text-xs text-slate-500 mt-2 max-w-md leading-relaxed font-medium">
                    Try adjusting your search query or switching from Starred to All databases.
                  </p>
                  <button 
                    onClick={() => { setSearchQuery(''); setFilterType('all'); }} 
                    className="px-5 py-3 rounded-full text-xs font-bold bg-white border border-slate-250 hover:border-slate-400 dark:bg-[#131A26] dark:border-[#1E293B] dark:hover:border-slate-500 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-900 dark:hover:text-white transition-all shadow-md font-sans mt-4 cursor-pointer"
                  >
                    Clear Search & Filters
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 font-sans">
                  {filteredWorkspaces.map(w => (
                    <motion.div key={w.id} variants={childVariants} style={{ willChange: 'transform, opacity' }}>
                      <WorkspaceCard
                        workspace={w}
                        onOpen={onOpenWorkspace}
                        onEdit={handleEdit}
                        onDelete={handleDelete}
                        isStarred={starredIds.includes(w.id)}
                        onToggleStar={(e) => toggleStar(w.id, e)}
                      />
                    </motion.div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Absolute bottom fading scroll hint banner */}
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-t from-slate-50 dark:from-[#060A13] to-transparent z-10 flex items-end justify-center pb-2 select-none">
          <span className="text-[10px] text-slate-450 dark:text-slate-500 font-bold tracking-widest uppercase opacity-40">Scroll to see more databases</span>
        </div>
      </main>

      <NewWorkspaceModal isOpen={modalOpen} onClose={() => { setModalOpen(false); setEditWs(null); }} onCreateWorkspace={handleCreateOrUpdate} editWorkspace={editWs} />

      <AccountSettingsModal isOpen={accountModalOpen} onClose={() => setAccountModalOpen(false)} onSaveSuccess={handleAccountSaveSuccess} />

      {deleteConfirm && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white dark:bg-[#0F1420] max-w-sm w-full rounded-[24px] border border-slate-200 dark:border-[#1E293B] shadow-2xl p-6 space-y-4 font-sans">
            <h3 className="text-base font-extrabold text-slate-900 dark:text-white">Delete Database?</h3>
            <p className="text-xs text-slate-655 dark:text-slate-400 leading-relaxed font-medium">Are you sure you want to delete this database? This action cannot be undone.</p>
            <div className="flex justify-end gap-3 pt-2">
              <button onClick={() => setDeleteConfirm(null)} className="px-4.5 py-2.5 rounded-full text-xs font-bold text-slate-700 border border-slate-250 hover:bg-slate-100 dark:text-slate-300 dark:border-[#1E293B] dark:hover:bg-[#131A26] transition-all cursor-pointer font-sans">Cancel</button>
              <button onClick={confirmDelete} className="px-5 py-2.5 rounded-full text-xs font-bold bg-red-600 hover:bg-red-505 text-white shadow-lg shadow-red-650/15 transition-all cursor-pointer font-sans">Confirm Delete</button>
            </div>
          </div>
        </div>
      )}
    </motion.div>
  );
};
