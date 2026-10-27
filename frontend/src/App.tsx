import React, { useState, useEffect, useMemo, useRef } from 'react';
import { flushSync } from 'react-dom';
import { TabType, Sidebar } from './components/Sidebar';
import { OverviewDashboard } from './components/OverviewDashboard';
import { LineageExplorer } from './components/LineageExplorer';
import { ImpactAnalysisView } from './components/ImpactAnalysisView';
import { HITLDashboard } from './components/HITLDashboard';
import { SqlIngestScanner } from './components/SqlIngestScanner';
import { DataCatalogView } from './components/DataCatalogView';
import { ExportModal } from './components/ExportModal';
import { SettingsModal } from './components/SettingsModal';
import { FloatingChatbot } from './components/FloatingChatbot';
import { mockProjectsList, ProjectData } from './data/mockProjects';
import { LineageNodeData, LineageEdgeData, HITLQueueItem } from './types/lineage';
import { LandingPage } from './components/landing/LandingPage';
import { IntroductionPage } from './components/intro/IntroductionPage';
import { WorkspaceManager } from './components/workspace/WorkspaceManager';
import { Workspace } from './types/workspace';
import { getCurrentUser, TokenResponse, User } from './api/auth';
import { Database, createDatabase, listDatabases } from './api/database';
import { getGraph } from './api/graph';
import { listPendingReview } from './api/review';
import { AnimatePresence } from 'framer-motion';

// Real Providers
import { GraphProvider, useGraphContext } from './hooks/GraphProvider';
import { ReviewProvider, useReviewContext } from './hooks/ReviewProvider';
import { ChatProvider } from './hooks/ChatProvider';
import { PopupProvider } from './hooks/PopupProvider';
import { graphResponseToLineageData, pendingEdgesToLineageData } from './adapters/backendToLineage';

// Bật lại true khi cần demo (workspace fintech/healthcare chưa có dữ liệu
// thật, hoặc muốn đồ thị luôn có sẵn nội dung để trình bày) — để false khi
// tinh chỉnh giao diện để không bị lẫn dữ liệu demo cứng với dữ liệu thật.
const SHOW_MOCK_DEMO_DATA = false;

function workspaceShell(_database: Database | null, user: User): Workspace {
  return {
    id: `workspace-${user.id}`,
    name: user.display_name ?? user.email,
    description: '',
    tableCount: 0,
    columnCount: 0,
    edgeCount: 0,
    pendingCount: 0,
    createdAt: new Date().toISOString(),
  };
}

function MainAppLayout({
  activeWorkspace, 
  onLogout,
  darkMode,
  setDarkMode
  ,databases
  ,selectedDatabaseId
  ,onSelectDatabase
  ,onCreateDatabase
  ,onBackToWorkspace
  ,role
}: {
  activeWorkspace: Workspace;
  onLogout?: () => void;
  darkMode: boolean;
  setDarkMode: (val: boolean, clickCoords?: { x: number; y: number }) => void;
  databases: Database[];
  selectedDatabaseId: number | null;
  onSelectDatabase: (database: Database) => void;
  onCreateDatabase: (name: string) => Promise<void>;
  onBackToWorkspace: () => void;
  role: 'engineer' | 'viewer';
}) {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [selectedProjectId, setSelectedProjectId] = useState<string>('ecommerce-lakehouse');
  
  // Real hooks
  const realGraphCtx = useGraphContext();
  const realReviewCtx = useReviewContext();
  const realNodes = useMemo(
    () => graphResponseToLineageData(realGraphCtx.data).nodes,
    [realGraphCtx.data],
  );
  const realTables = useMemo(() => realNodes.map((node) => node.id), [realNodes]);

  // Project Data State
  const [currentProject, setCurrentProject] = useState<ProjectData>(mockProjectsList[0]);
  const [nodes, setNodes] = useState<LineageNodeData[]>(mockProjectsList[0].nodes);
  const [edges, setEdges] = useState<LineageEdgeData[]>(mockProjectsList[0].edges);

  // Seed/refresh nodes/edges từ đồ thị THẬT (GET /api/v1/graph qua
  // GraphProvider) mỗi khi nó tải xong/reload — dữ liệu thật luôn ưu tiên,
  // dữ liệu mock của project hiện tại chỉ lấp chỗ trống cho các bảng/cạnh
  // demo chưa từng ingest thật (vd workspace fintech/healthcare chưa có dữ
  // liệu thật). Giữ nodes/edges là state thường (không derive thẳng) để các
  // hàm xử lý HITL mock phía dưới (isMockItem) vẫn mutate được như cũ.
  useEffect(() => {
    const real = graphResponseToLineageData(realGraphCtx.data);
    // Cạnh pending (HITL queue / LLM suy luận) không nằm trong GET /graph —
    // phải gộp riêng để đồ thị hiện được cả cạnh nét đứt "LLM Generated"/
    // "HITL Queue" mà legend đã quảng cáo, không chỉ cạnh đã confirmed.
    const pendingData = pendingEdgesToLineageData(
      realReviewCtx.pending,
      real.nodes.map(n => n.id),
    );
    const realNodes = [...real.nodes, ...pendingData.nodes];
    const realEdges = [...real.edges, ...pendingData.edges];
    if (!SHOW_MOCK_DEMO_DATA) {
      setNodes(realNodes);
      setEdges(realEdges);
      return;
    }
    setNodes([
      ...realNodes,
      ...currentProject.nodes.filter(n => !realNodes.some(rn => rn.id === n.id)),
    ]);
    setEdges([
      ...realEdges,
      ...currentProject.edges.filter(e => !realEdges.some(re => re.id === e.id)),
    ]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [realGraphCtx.data, realReviewCtx.pending, currentProject]);

  // We keep a local reviewed items history to display in the historical logs
  const [reviewedHistory, setReviewedHistory] = useState<HITLQueueItem[]>([]);

  // Map real review queue from backend:
  const hitlQueueMapped = realReviewCtx.pending.map((edge) => ({
    id: edge.edge_id,
    edgeId: edge.edge_id,
    sourceTable: edge.source_table,
    targetTable: edge.target_table,
    sourceSchema: 'source_raw',
    targetSchema: 'staging',
    confidence: edge.confidence,
    inferredBy: edge.source_type === 'llm' ? 'gemini_llm' as const : 'gpt4o_mini' as const,
    reason: edge.evidence?.reasoning || 'Cạnh do AI suy luận tự động.',
    reasonDetail: edge.evidence?.reasoning_detail || undefined,
    resolutionMethod: edge.evidence?.resolution_method || undefined,
    sqlSnippet: edge.evidence?.raw_sql || '',
    filePath: edge.evidence?.file_path || '',
    suggestedColumnMappings: edge.source_column && edge.target_column ? [{ sourceCol: edge.source_column, targetCol: edge.target_column }] : [],
    status: 'pending' as const,
    timestamp: edge.evidence?.confirmed_at || new Date().toLocaleString(),
    detectedIssue: 'dynamic_sql' as const
  }));

  // Combine real pending queue with local reviewed history and current project's mock pending queue
  const currentProjectPendingHitl = SHOW_MOCK_DEMO_DATA
    ? currentProject.hitlQueue.filter(item => !reviewedHistory.some(h => h.id === item.id))
    : [];
  const fullHitlQueue = [...currentProjectPendingHitl, ...hitlQueueMapped, ...reviewedHistory];

  // Cross-tab interaction states
  const [targetImpactNodeId, setTargetImpactNodeId] = useState<string>('');
  const [impactedNodeIds, setImpactedNodeIds] = useState<string[]>([]);
  const [upstreamNodeIds, setUpstreamNodeIds] = useState<string[]>([]);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [layoutDirection, setLayoutDirection] = useState<'LR' | 'TB'>('LR');
  const [pendingCopilotQuestion, setPendingCopilotQuestion] = useState<{ text: string; token: number } | null>(null);

  // Sync project change
  useEffect(() => {
    let projId = 'ecommerce-lakehouse';
    if (activeWorkspace.id === 'ws-fintech') {
      projId = 'fintech-fraud-ledger';
    } else if (activeWorkspace.id === 'ws-healthcare') {
      projId = mockProjectsList[1]?.id || 'ecommerce-lakehouse';
    } else if (activeWorkspace.id === 'ws-retail-omni') {
      projId = 'retail-omni-channel';
    }
    const proj = mockProjectsList.find(p => p.id === projId) || mockProjectsList[0];
    setCurrentProject(proj);
    // nodes/edges được effect seed-từ-dữ-liệu-thật (bên trên) tự merge lại
    // ngay khi currentProject đổi — không tự gán proj.nodes/edges ở đây nữa
    // để tránh 1 nhịp render hiện mock thuần trước khi merge dữ liệu thật.
    setImpactedNodeIds([]);
    setUpstreamNodeIds([]);
    setReviewedHistory([]);
  }, [activeWorkspace]);

  // Navigation handlers
  const handleAnalyzeImpact = (node: LineageNodeData) => {
    setTargetImpactNodeId(node.id);
    setActiveTab('impact');
  };

  const handleNavigateToGraphWithImpact = (targetId: string, downstreamIds: string[], upstreamIds: string[]) => {
    setTargetImpactNodeId(targetId);
    setImpactedNodeIds([targetId, ...downstreamIds]);
    setUpstreamNodeIds(upstreamIds);
    setActiveTab('explorer');
  };

  const handleSelectNodeInGraph = (nodeId: string) => {
    setTargetImpactNodeId(nodeId);
    setActiveTab('explorer');
  };

  const handleTabChange = (tab: TabType) => {
    if (tab === 'explorer') {
      setTargetImpactNodeId('');
      setImpactedNodeIds([]);
      setUpstreamNodeIds([]);
    }
    setActiveTab(tab);
  };

  // Real HITL Decision Handlers
  // Real/Mock HITL Decision Handlers
  const handleConfirmHITLEdge = async (item: HITLQueueItem) => {
    const isMockItem = !hitlQueueMapped.some(q => q.id === item.id);
    try {
      if (!isMockItem) {
        await realReviewCtx.approve(item.edgeId);
      }
      setReviewedHistory(prev => [
        { ...item, status: 'confirmed', timestamp: new Date().toLocaleString() },
        ...prev
      ]);
      if (isMockItem) {
        const mockEdge = currentProject.edges.find(e => e.id === item.edgeId);
        if (mockEdge) {
          setEdges(prev => {
            if (prev.some(e => e.id === mockEdge.id)) {
              return prev.map(e => e.id === mockEdge.id ? { ...e, status: 'active', confidence: 1.0 } : e);
            }
            return [...prev, { ...mockEdge, status: 'active', confidence: 1.0 }];
          });
        }
      } else {
        realGraphCtx.reload();
        realReviewCtx.reload();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleRejectHITLEdge = async (item: HITLQueueItem) => {
    const isMockItem = !hitlQueueMapped.some(q => q.id === item.id);
    try {
      if (!isMockItem) {
        await realReviewCtx.reject(item.edgeId);
      }
      setReviewedHistory(prev => [
        { ...item, status: 'rejected', timestamp: new Date().toLocaleString() },
        ...prev
      ]);
      if (isMockItem) {
        setEdges(prev => prev.filter(e => e.id !== item.edgeId));
      } else {
        realGraphCtx.reload();
        realReviewCtx.reload();
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Duyệt/Từ chối trực tiếp từ drawer cạnh trên Lineage DAG — không cần dựng
  // lại HITLQueueItem như handleConfirmHITLEdge (không có mock-branching ở
  // đây vì edge trong LineageExplorer luôn đến từ realReviewCtx.pending thật).
  const handleConfirmEdgeInline = async (edgeId: string) => {
    await realReviewCtx.approve(edgeId);
    realGraphCtx.reload();
  };

  const handleRejectEdgeInline = async (edgeId: string) => {
    await realReviewCtx.reject(edgeId);
    realGraphCtx.reload();
  };

  const handleEditAndConfirmHITLEdge = async (item: HITLQueueItem, updatedMappings: any) => {
    const isMockItem = !hitlQueueMapped.some(q => q.id === item.id);
    try {
      if (!isMockItem) {
        await realReviewCtx.approve(item.edgeId);
      }
      setReviewedHistory(prev => [
        { ...item, status: 'edited', suggestedColumnMappings: updatedMappings, timestamp: new Date().toLocaleString() },
        ...prev
      ]);
      if (isMockItem) {
        const mockEdge = currentProject.edges.find(e => e.id === item.edgeId);
        if (mockEdge) {
          setEdges(prev => {
            if (prev.some(e => e.id === mockEdge.id)) {
              return prev.map(e => e.id === mockEdge.id ? { ...e, status: 'active', confidence: 1.0, columnMappings: updatedMappings } : e);
            }
            return [...prev, { ...mockEdge, status: 'active', confidence: 1.0, columnMappings: updatedMappings }];
          });
        }
      } else {
        realGraphCtx.reload();
        realReviewCtx.reload();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleBatchConfirmAll = async () => {
    try {
      // Approve all real items in backend
      for (const item of hitlQueueMapped) {
        await realReviewCtx.approve(item.edgeId);
      }
      
      // Also approve all mock items from the current project that haven't been reviewed
      const mockItemsToConfirm = currentProjectPendingHitl;
      
      setReviewedHistory(prev => [
        ...hitlQueueMapped.map(item => ({ ...item, status: 'confirmed' as const, timestamp: new Date().toLocaleString() })),
        ...mockItemsToConfirm.map(item => ({ ...item, status: 'confirmed' as const, timestamp: new Date().toLocaleString() })),
        ...prev
      ]);

      // Activate all mock edges
      if (mockItemsToConfirm.length > 0) {
        setEdges(prev => {
          let updated = [...prev];
          mockItemsToConfirm.forEach(item => {
            const mockEdge = currentProject.edges.find(e => e.id === item.edgeId);
            if (mockEdge) {
              if (updated.some(e => e.id === mockEdge.id)) {
                updated = updated.map(e => e.id === mockEdge.id ? { ...e, status: 'active', confidence: 1.0 } : e);
              } else {
                updated.push({ ...mockEdge, status: 'active', confidence: 1.0 });
              }
            }
          });
          return updated;
        });
      }

      realGraphCtx.reload();
      realReviewCtx.reload();
    } catch (err) {
      console.error(err);
    }
  };

  const handleIngestSuccess = () => {
    // nodes/edges được effect seed-từ-dữ-liệu-thật (phía trên) tự cập nhật
    // ngay khi realGraphCtx.data đổi sau reload() — không cần tự vá state
    // cục bộ bằng dữ liệu do SqlIngestScanner suy ra nữa.
    realGraphCtx.reload();
    realReviewCtx.reload();
  };

  const handleClearGraph = async () => {
    try {
      await realGraphCtx.clear();
      await realReviewCtx.reload();
      setReviewedHistory([]);
      setTargetImpactNodeId('');
      setImpactedNodeIds([]);
      setUpstreamNodeIds([]);
    } catch (err) {
      console.error("Error clearing graph:", err);
    }
  };

  const handleApproveProposedChange = (
    nodeId: string, 
    operation: string, 
    columnName: string, 
    newColumnName?: string, 
    notes?: string
  ) => {
    if (operation === 'rename_column' && newColumnName) {
      setNodes(prev => prev.map(node => {
        if (node.id === nodeId) {
          return {
            ...node,
            columns: node.columns.map(c => c.name === columnName ? { ...c, name: newColumnName } : c)
          };
        }
        return node;
      }));
    }
    if (operation === 'add_column' && newColumnName) {
      setNodes(prev => prev.map(node => {
        if (node.id === nodeId && !node.columns.some(c => c.name === newColumnName)) {
          return {
            ...node,
            columns: [...node.columns, { name: newColumnName, type: 'unknown', transformType: 'DIRECT' as const }]
          };
        }
        return node;
      }));
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 transition-colors duration-200">
      {/* Sidebar navigation */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        isCollapsed={isSidebarCollapsed}
        setIsCollapsed={setIsSidebarCollapsed}
        projects={mockProjectsList}
        selectedProjectId={selectedProjectId}
        onSelectProject={setSelectedProjectId}
        hitlPendingCount={currentProjectPendingHitl.length + hitlQueueMapped.length}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenExport={() => setIsExportOpen(true)}
        workspaceName={activeWorkspace.name}
        onBackToWorkspaces={onBackToWorkspace}
        onLogout={onLogout}
        databases={databases}
        selectedDatabaseId={selectedDatabaseId ?? undefined}
        onSelectDatabase={onSelectDatabase}
      />

      {/* Main Panel */}
      <main className={`flex-1 h-screen relative flex flex-col ${activeTab === 'explorer' ? 'overflow-hidden' : 'overflow-y-auto'}`}>
        <div className={`flex-1 ${activeTab === 'explorer' ? 'h-full pb-0' : 'pb-16'}`}>
          {activeTab === 'overview' && (
            <OverviewDashboard
              nodes={nodes}
              edges={edges}
              hitlQueue={fullHitlQueue}
              projectName={currentProject.name}
              onNavigateTab={handleTabChange}
              onSelectNodeInGraph={handleSelectNodeInGraph}
              onAnalyzeImpactForNode={handleAnalyzeImpact}
              onConfirmHITLEdge={handleConfirmHITLEdge}
              onRejectHITLEdge={handleRejectHITLEdge}
              onAskCopilot={(q) => setPendingCopilotQuestion({ text: q, token: Date.now() })}
            />
          )}

          {activeTab === 'explorer' && (
            <LineageExplorer
              nodes={nodes}
              edges={edges}
              darkMode={darkMode}
              onAnalyzeImpact={handleAnalyzeImpact}
              onOpenHITL={() => handleTabChange('hitl')}
              selectedNodeId={targetImpactNodeId}
              impactedNodeIds={impactedNodeIds}
              upstreamNodeIds={upstreamNodeIds}
              layoutDirection={layoutDirection}
              onClearGraph={handleClearGraph}
              canClearGraph={role === 'engineer'}
              onConfirmPendingEdge={handleConfirmEdgeInline}
              onRejectPendingEdge={handleRejectEdgeInline}
              onAskCopilotAboutEdge={(q) => setPendingCopilotQuestion({ text: q, token: Date.now() })}
              canReview={role === 'engineer'}
            />
          )}

          {activeTab === 'impact' && (
            <ImpactAnalysisView
              nodes={nodes}
              edges={edges}
              initialNodeId={targetImpactNodeId}
              onNavigateToGraphWithImpact={handleNavigateToGraphWithImpact}
              onAskCopilot={(q) => setPendingCopilotQuestion({ text: q, token: Date.now() })}
              onApproveProposedChange={handleApproveProposedChange}
            />
          )}

          {activeTab === 'hitl' && (
            <HITLDashboard
              queue={fullHitlQueue}
              onConfirmEdge={handleConfirmHITLEdge}
              onRejectEdge={handleRejectHITLEdge}
              onEditAndConfirmEdge={handleEditAndConfirmHITLEdge}
              onBatchConfirmAll={handleBatchConfirmAll}
              canReview={role === 'engineer'}
            />
          )}

          {activeTab === 'ingest' && (
            <SqlIngestScanner
              onIngestSuccess={handleIngestSuccess}
              onNavigateToGraph={() => handleTabChange('explorer')}
              canIngest={role === 'engineer'}
              databases={databases}
              selectedDatabaseId={selectedDatabaseId}
              onSelectDatabase={onSelectDatabase}
              onCreateDatabase={onCreateDatabase}
            />
          )}

          {activeTab === 'catalog' && (
            <DataCatalogView
              nodes={nodes}
              onSelectNodeInGraph={handleSelectNodeInGraph}
              onAnalyzeImpactForNode={handleAnalyzeImpact}
            />
          )}
        </div>
      </main>

      {/* Export Modal */}
      <ExportModal
        isOpen={isExportOpen}
        onClose={() => setIsExportOpen(false)}
        nodes={nodes}
        edges={edges}
        hitlQueue={fullHitlQueue}
      />

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        darkMode={darkMode}
        setDarkMode={setDarkMode}
        layoutDirection={layoutDirection}
        setLayoutDirection={setLayoutDirection}
      />

      {/* Floating Chatbot Assistant (Bottom-Right) */}
      <FloatingChatbot
        nodes={nodes}
        realNodes={realNodes}
        realTables={realTables}
        edges={edges}
        hitlQueue={fullHitlQueue}
        projectName={currentProject.name}
        onNavigateToNode={handleSelectNodeInGraph}
        onOpenImpactForNode={(id) => {
          setTargetImpactNodeId(id);
          setActiveTab('impact');
        }}
        onNavigateTab={(tab) => handleTabChange(tab as TabType)}
        pendingQuestion={pendingCopilotQuestion}
      />
    </div>
  );
}

function AppContent() {
  const realGraphCtx = useGraphContext();
  const realReviewCtx = useReviewContext();

  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => Boolean(localStorage.getItem('data_lineage_token')));
  const [showLogin, setShowLogin] = useState<boolean>(false);
  const [activeWorkspace, setActiveWorkspace] = useState<Workspace | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [databases, setDatabases] = useState<Database[]>([]);
  const [selectedDatabaseId, setSelectedDatabaseId] = useState<number | null>(() => {
    const value = Number(localStorage.getItem('data_lineage_database_id'));
    return Number.isInteger(value) && value > 0 ? value : null;
  });
  const [isWorkspaceHome, setIsWorkspaceHome] = useState(false);
  const [gateOpened, setGateOpened] = useState<boolean>(false);
  const justLoggedInRef = useRef(false);

  const [databaseStats, setDatabaseStats] = useState<Record<number, {
    tableCount: number;
    columnCount: number;
    edgeCount: number;
    pendingCount: number;
  }>>({});

  const loadDatabaseStats = async (dbs: Database[]) => {
    const statsMap: Record<number, {
      tableCount: number;
      columnCount: number;
      edgeCount: number;
      pendingCount: number;
    }> = {};
    
    await Promise.all(
      dbs.map(async (db) => {
        try {
          const [graph, pending] = await Promise.all([
            getGraph(db.id),
            listPendingReview(db.id)
          ]);
          
          const mapped = graphResponseToLineageData(graph);
          const tableCount = mapped.nodes.length;
          const columnCount = mapped.nodes.reduce((sum, n) => sum + n.columns.length, 0);
          const edgeCount = graph.edges.length;
          const pendingCount = pending.length;
          
          statsMap[db.id] = {
            tableCount,
            columnCount,
            edgeCount,
            pendingCount
          };
        } catch (err) {
          console.error(`Error loading stats for database ${db.id}:`, err);
          statsMap[db.id] = {
            tableCount: 0,
            columnCount: 0,
            edgeCount: 0,
            pendingCount: 0
          };
        }
      })
    );
    setDatabaseStats(statsMap);
  };

  const databaseCardShell = (database: Database): Workspace => {
    const stats = databaseStats[database.id] || {
      tableCount: 0,
      columnCount: 0,
      edgeCount: 0,
      pendingCount: 0,
    };
    return {
      id: `database-${database.id}`,
      name: database.name,
      description: 'Database được quản lý trong workspace hiện tại.',
      tableCount: stats.tableCount,
      columnCount: stats.columnCount,
      edgeCount: stats.edgeCount,
      pendingCount: stats.pendingCount,
      createdAt: database.created_at,
    };
  };

  const [darkMode, setDarkModeState] = useState<boolean>(() => {
    const saved = localStorage.getItem('theme');
    return saved ? saved === 'dark' : true;
  });

  // Track coordinates of global clicks to trigger radial clip-path wave reveal on theme toggle
  useEffect(() => {
    const handleGlobalClick = (e: MouseEvent) => {
      (window as any).lastClickCoords = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener('click', handleGlobalClick, { capture: true });
    return () => {
      window.removeEventListener('click', handleGlobalClick, { capture: true });
    };
  }, []);

  const setDarkMode = (val: boolean, clickCoords?: { x: number; y: number }) => {
    if (typeof document !== 'undefined' && 'startViewTransition' in document) {
      const lastClick = clickCoords || (window as any).lastClickCoords || { x: window.innerWidth / 2, y: window.innerHeight / 2 };
      const { x, y } = lastClick;
      
      const maxRadius = Math.hypot(
        Math.max(x, window.innerWidth - x),
        Math.max(y, window.innerHeight - y)
      );

      const transition = (document as any).startViewTransition(() => {
        flushSync(() => {
          setDarkModeState(val);
        });
      });

      transition.ready.then(() => {
        document.documentElement.animate(
          {
            clipPath: [
              `circle(0px at ${x}px ${y}px)`,
              `circle(${maxRadius}px at ${x}px ${y}px)`
            ],
          },
          {
            duration: 550,
            easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
            pseudoElement: '::view-transition-new(root)',
          }
        );
      });
    } else {
      setDarkModeState(val);
    }
  };

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [darkMode]);

  useEffect(() => {
    if (!isAuthenticated) return;
    Promise.all([listDatabases(), getCurrentUser()]).then(([available, user]) => {
      setDatabases(available);
      setCurrentUser(user);
      const selected = available.find((database) => database.id === selectedDatabaseId) ?? available[0];
      if (!selected) {
        setSelectedDatabaseId(null);
        localStorage.removeItem('data_lineage_database_id');
        setActiveWorkspace(workspaceShell(null, user));
        setIsWorkspaceHome(true);
        window.dispatchEvent(new Event('data-lineage-context-changed'));
        return;
      }
      if (selected.id !== selectedDatabaseId) {
        localStorage.setItem('data_lineage_database_id', String(selected.id));
        setSelectedDatabaseId(selected.id);
      }
      setActiveWorkspace(workspaceShell(selected, user));
      
      if (justLoggedInRef.current) {
        setIsWorkspaceHome(selected.role === 'engineer');
        justLoggedInRef.current = false;
      } else {
        setIsWorkspaceHome(false);
      }
      
      window.dispatchEvent(new Event('data-lineage-context-changed'));
    }).catch(() => handleLogout());
  // Loading the selected database only changes when the identity changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  useEffect(() => {
    if (!selectedDatabaseId) return;
    const realGraph = realGraphCtx.data;
    const realPending = realReviewCtx.pending;
    if (realGraph) {
      const mapped = graphResponseToLineageData(realGraph);
      const tableCount = mapped.nodes.length;
      const columnCount = mapped.nodes.reduce((sum, n) => sum + n.columns.length, 0);
      const edgeCount = realGraph.edges.length;
      const pendingCount = realPending?.length ?? 0;
      
      setDatabaseStats(prev => ({
        ...prev,
        [selectedDatabaseId]: {
          tableCount,
          columnCount,
          edgeCount,
          pendingCount
        }
      }));
    }
  }, [realGraphCtx.data, realReviewCtx.pending, selectedDatabaseId]);

  const handleLogin = async (result: TokenResponse) => {
    localStorage.setItem('data_lineage_token', result.access_token);
    const user = result.user;
    justLoggedInRef.current = true;
    try {
      const available = await listDatabases();
      setDatabases(available);
      setCurrentUser(user);
      const selected = available[0];
      if (selected) {
        localStorage.setItem('data_lineage_database_id', String(selected.id));
        setSelectedDatabaseId(selected.id);
        setActiveWorkspace(workspaceShell(selected, user));
      } else {
        setSelectedDatabaseId(null);
        localStorage.removeItem('data_lineage_database_id');
        setActiveWorkspace(workspaceShell(null, user));
      }
      setIsWorkspaceHome(true);
      setIsAuthenticated(true);
      window.dispatchEvent(new Event('data-lineage-context-changed'));
    } catch (error) {
      localStorage.removeItem('data_lineage_token');
      justLoggedInRef.current = false;
      alert(error instanceof Error ? error.message : 'Không tải được database.');
    }
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    setActiveWorkspace(null);
    setCurrentUser(null);
    setIsWorkspaceHome(false);
    setShowLogin(false);
    setGateOpened(false);
    justLoggedInRef.current = false;
    localStorage.removeItem('data_lineage_token');
    localStorage.removeItem('data_lineage_database_id');
    window.dispatchEvent(new Event('data-lineage-context-changed'));
  };

  const selectDatabase = (database: Database) => {
    localStorage.setItem('data_lineage_database_id', String(database.id));
    setSelectedDatabaseId(database.id);
    if (currentUser) setActiveWorkspace(workspaceShell(database, currentUser));
    window.dispatchEvent(new Event('data-lineage-context-changed'));
  };

  const openDatabase = (database: Database) => {
    selectDatabase(database);
    setIsWorkspaceHome(false);
  };

  // Dùng chung cho Hub và nút tạo nhanh dự án.
  const createDatabaseByName = async (name: string): Promise<Database | null> => {
    try {
      const database = await createDatabase(name);
      setDatabases((current) => {
        const next = [...current, database];
        loadDatabaseStats(next);
        return next;
      });
      return database;
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Không tạo được database.');
      return null;
    }
  };

  const createDatabaseInWorkspace = async (card: Workspace) => {
    const created = await createDatabaseByName(card.name);
    if (created) openDatabase(created);
  };

  const databaseFromCard = (card: Workspace) => databases.find((database) => card.id === `database-${database.id}`);

  if (!activeWorkspace && isAuthenticated) return <div className="min-h-screen bg-slate-950" />;

  return (
    <AnimatePresence>
      {!isAuthenticated ? (
        showLogin ? (
          <LandingPage key="landing" onLogin={handleLogin} onBackToIntro={() => setShowLogin(false)} />
        ) : (
          <IntroductionPage key="intro" onLoginClick={() => setShowLogin(true)} />
        )
      ) : isWorkspaceHome ? (
        <WorkspaceManager
          key="workspace-home"
          workspaces={databases.map(databaseCardShell)}
          workspaceName={activeWorkspace!.name}
          gateOpened={gateOpened}
          setGateOpened={setGateOpened}
          onOpenWorkspace={(card) => {
            const database = databaseFromCard(card);
            if (database) openDatabase(database);
          }}
          onCreateWorkspace={createDatabaseInWorkspace}
          onUpdateWorkspace={() => alert('Backend chưa hỗ trợ sửa cấu hình database.')}
          onDeleteWorkspace={() => alert('Backend chưa hỗ trợ xoá database.')}
          onLogout={handleLogout}
          darkMode={darkMode}
          setDarkMode={setDarkMode}
          loadStats={() => loadDatabaseStats(databases)}
        />
      ) : (
        <MainAppLayout
          key="main-app"
          activeWorkspace={activeWorkspace!}
          onLogout={handleLogout}
          darkMode={darkMode}
          setDarkMode={setDarkMode}
          databases={databases}
          selectedDatabaseId={selectedDatabaseId}
          onSelectDatabase={openDatabase}
          onCreateDatabase={async (name) => {
            const created = await createDatabaseByName(name);
            if (created) openDatabase(created);
          }}
          onBackToWorkspace={() => setIsWorkspaceHome(true)}
          role={databases.find((database) => database.id === selectedDatabaseId)?.role ?? 'viewer'}
        />
      )}
    </AnimatePresence>
  );
}

export function App() {
  return (
    <GraphProvider>
      <ReviewProvider>
        <ChatProvider>
          <PopupProvider>
            <AppContent />
          </PopupProvider>
        </ChatProvider>
      </ReviewProvider>
    </GraphProvider>
  );
}
