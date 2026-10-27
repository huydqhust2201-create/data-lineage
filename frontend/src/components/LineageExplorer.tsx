import React, { useMemo, useState, useCallback, useEffect } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  ControlButton,
  Background,
  useNodesState,
  useEdgesState,
  Edge,
  Node,
  MarkerType,
  BackgroundVariant,
  Panel,
  ReactFlowInstance
} from '@xyflow/react';
import { LineageNodeData, LineageEdgeData, ColumnDef } from '../types/lineage';
import { CustomTableNode, LineageViewMode, AffectedColumnInfo } from './CustomTableNode';
import { computeDepths } from '../utils/computeDepths';
import { useImpact } from '../hooks/useImpact';
import { RESOLUTION_METHOD_LABELS } from '../utils/resolutionMethod';

const CLL_TRANSFORM_LABELS: Record<string, string> = {
  direct: 'Ánh xạ trực tiếp',
  conditional: 'Điều kiện (CASE/COALESCE)',
  aggregation: 'Tổng hợp',
  join: 'Join',
  unknown: 'Không rõ biến đổi',
};
import { 
  Search, 
  Layers, 
  ShieldCheck, 
  RotateCcw, 
  X, 
  Zap, 
  Code2,
  SlidersHorizontal,
  LayoutGrid,
  List,
  Sparkles,
  GitBranch,
  Filter,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Database,
  Table,
  Info,
  Clock,
  Map,
  User,
  Tag,
  Hash,
  ExternalLink,
  Copy,
  Check,
  Flame,
  GitCommit,
  Share2,
  Trash2,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

interface LineageExplorerProps {
  nodes: LineageNodeData[];
  edges: LineageEdgeData[];
  darkMode: boolean;
  onAnalyzeImpact: (node: LineageNodeData) => void;
  onOpenHITL: () => void;
  selectedNodeId?: string;
  impactedNodeIds?: string[];
  upstreamNodeIds?: string[];
  layoutDirection: 'LR' | 'TB';
  onClearGraph?: () => void;
  canClearGraph?: boolean;
  onConfirmPendingEdge?: (edgeId: string) => Promise<void> | void;
  onRejectPendingEdge?: (edgeId: string) => Promise<void> | void;
  onAskCopilotAboutEdge?: (question: string) => void;
  canReview?: boolean;
}

const nodeTypes = {
  customTable: CustomTableNode
};

export const LineageExplorer: React.FC<LineageExplorerProps> = ({
  nodes: rawNodesData,
  edges: rawEdgesData,
  darkMode,
  onAnalyzeImpact,
  onOpenHITL,
  selectedNodeId: externalSelectedNodeId,
  impactedNodeIds = [],
  upstreamNodeIds = [],
  layoutDirection,
  onClearGraph,
  canClearGraph = true,
  onConfirmPendingEdge,
  onRejectPendingEdge,
  onAskCopilotAboutEdge,
  canReview = true,
}) => {
  // Atlan State Controls
  const [viewMode, setViewMode] = useState<LineageViewMode>('compact');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedLayer, setSelectedLayer] = useState<string>('all');
  const [selectedRelationship, setSelectedRelationship] = useState<string>('all');

  const initialNodesData = rawNodesData;
  const initialEdgesData = rawEdgesData;
  const depthById = useMemo(
    () => computeDepths(initialNodesData.map(node => node.id), initialEdgesData),
    [initialNodesData, initialEdgesData]
  );

  // Active column trace (Column-Level Lineage - CLL) — trước đây tự BFS
  // client-side trên dữ liệu đã tải, kèm suy đoán "cùng tên cột thì chắc
  // cùng lineage" khi thiếu columnMappings (dễ sai). Giờ gọi thẳng endpoint
  // impact thật (đã có sẵn đa tầng + column-aware từ graph_service._traverse),
  // không đoán mò — cạnh thiếu evidence cột thì bỏ qua, không suy diễn.
  const [activeTracedColumn, setActiveTracedColumn] = useState<{ nodeId: string; colName: string } | null>(null);
  const { result: cllDownstreamResult, query: queryCllDownstream } = useImpact();
  const { result: cllUpstreamResult, query: queryCllUpstream } = useImpact();

  useEffect(() => {
    if (!activeTracedColumn) return;
    queryCllDownstream(activeTracedColumn.nodeId, 'downstream', activeTracedColumn.colName);
    queryCllUpstream(activeTracedColumn.nodeId, 'upstream', activeTracedColumn.colName);
  }, [activeTracedColumn, queryCllDownstream, queryCllUpstream]);

  // Selected Node / 360° Drawer state
  const [selectedNode, setSelectedNode] = useState<LineageNodeData | null>(null);
  const [activeDrawerTab, setActiveDrawerTab] = useState<'overview' | 'columns' | 'lineage' | 'sql'>('overview');
  const [selectedEdge, setSelectedEdge] = useState<LineageEdgeData | null>(null);
  const [edgeReviewBusy, setEdgeReviewBusy] = useState(false);
  // "Chi tiết" toggle cho khối Transformation Logic ở drawer cạnh — reset mỗi
  // lần chọn cạnh khác.
  const [showReasoningDetail, setShowReasoningDetail] = useState(false);
  useEffect(() => {
    setShowReasoningDetail(false);
  }, [selectedEdge]);

  // Focus / Isolation Mode
  const [isFocusMode, setIsFocusMode] = useState<boolean>(false);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);

  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null);
  const [copiedSql, setCopiedSql] = useState(false);
  const [isClearConfirmOpen, setIsClearConfirmOpen] = useState(false);
  const [isLegendCollapsed, setIsLegendCollapsed] = useState<boolean>(false);
  const [showMiniMap, setShowMiniMap] = useState<boolean>(true);

  // Expanded Nodes set to track which cards are expanded in layout to prevent overlap
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set());

  const handleToggleExpandNode = useCallback((nodeId: string) => {
    setExpandedNodeIds(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }, []);


  // Sync external selected node
  useEffect(() => {
    if (externalSelectedNodeId) {
      const match = initialNodesData.find(n => n.id === externalSelectedNodeId);
      if (match) {
        setSelectedNode(match);
        setFocusedNodeId(match.id);
        setIsFocusMode(true);
      }
    }
  }, [externalSelectedNodeId, initialNodesData]);

  // Fit viewport when drawer opens/closes to prevent node overlapping
  useEffect(() => {
    if (rfInstance) {
      const timer = setTimeout(() => {
        rfInstance.fitView({ duration: 600, padding: 0.15 });
      }, 350);
      return () => clearTimeout(timer);
    }
  }, [selectedNode, selectedEdge, rfInstance]);


  // Compute matched nodes, edges, affected columns and direct column-to-column connections for active Column-Level Lineage
  const { cllMatchedNodeIds, cllMatchedEdgeIds, nodeAffectedColumns, cllEdgesList } = useMemo(() => {
    type CllEdge = { id: string; source: string; target: string; sourceCol: string; targetCol: string; transformType?: string; isVerified: boolean };
    if (!activeTracedColumn) {
      return {
        cllMatchedNodeIds: new Set<string>(),
        cllMatchedEdgeIds: new Set<string>(),
        nodeAffectedColumns: {} as Record<string, AffectedColumnInfo[]>,
        cllEdgesList: [] as CllEdge[],
      };
    }

    const matchedNodes = new Set<string>([activeTracedColumn.nodeId]);
    const matchedEdges = new Set<string>();
    const affectedMap: Record<string, AffectedColumnInfo[]> = {};
    const edgesList: CllEdge[] = [];

    // Nguồn sự thật duy nhất: GET /impact/{table}?column= 2 chiều (đã có
    // multi-hop column-aware traversal ở backend) — không tự suy đoán "cùng
    // tên cột thì chắc cùng lineage" nữa như bản client-BFS trước đây; cạnh
    // không có đủ evidence cột (source/target.column rỗng) bị bỏ qua thay vì
    // đoán mò.
    const allEdges = [
      ...(cllDownstreamResult?.confirmed ?? []),
      ...(cllDownstreamResult?.inferred_pending ?? []),
      ...(cllUpstreamResult?.confirmed ?? []),
      ...(cllUpstreamResult?.inferred_pending ?? []),
    ];

    allEdges.forEach((edge, idx) => {
      if (!edge.source.column || !edge.target.column) return;
      const sourceCol = edge.source.column;
      const targetCol = edge.target.column;
      const isVerified = edge.confidence === 1.0;
      const transformType = CLL_TRANSFORM_LABELS[edge.transform_type] ?? 'Không rõ biến đổi';

      matchedNodes.add(edge.source.table);
      matchedNodes.add(edge.target.table);
      const edgeId = `cll-${idx}-${edge.source.table}-${sourceCol}-${edge.target.table}-${targetCol}`;
      matchedEdges.add(edgeId);

      const targetNode = initialNodesData.find(n => n.id === edge.target.table);
      const targetColDef = targetNode?.columns.find(c => c.name.toLowerCase() === targetCol.toLowerCase());
      if (!affectedMap[edge.target.table]) affectedMap[edge.target.table] = [];
      if (!affectedMap[edge.target.table].some(x => x.colName.toLowerCase() === targetCol.toLowerCase())) {
        affectedMap[edge.target.table].push({
          colName: targetCol,
          type: targetColDef?.type,
          transformType,
          isStartNode: false,
          isPrimaryKey: targetColDef?.isPrimaryKey,
          isForeignKey: targetColDef?.isForeignKey,
          sourceCol,
        });
      }

      const sourceNode = initialNodesData.find(n => n.id === edge.source.table);
      const sourceColDef = sourceNode?.columns.find(c => c.name.toLowerCase() === sourceCol.toLowerCase());
      if (!affectedMap[edge.source.table]) affectedMap[edge.source.table] = [];
      if (!affectedMap[edge.source.table].some(x => x.colName.toLowerCase() === sourceCol.toLowerCase())) {
        affectedMap[edge.source.table].push({
          colName: sourceCol,
          type: sourceColDef?.type,
          transformType,
          isStartNode: false,
          isPrimaryKey: sourceColDef?.isPrimaryKey,
          isForeignKey: sourceColDef?.isForeignKey,
          sourceCol,
        });
      }

      edgesList.push({
        id: edgeId,
        source: edge.source.table,
        target: edge.target.table,
        sourceCol,
        targetCol,
        transformType,
        isVerified,
      });
    });

    return {
      cllMatchedNodeIds: matchedNodes,
      cllMatchedEdgeIds: matchedEdges,
      nodeAffectedColumns: affectedMap,
      cllEdgesList: edgesList,
    };
  }, [activeTracedColumn, cllDownstreamResult, cllUpstreamResult, initialNodesData]);

  // Compute transitive upstream & downstream for card isolation mode
  const { focusedUpstreamIds, focusedDownstreamIds, directNeighborIds } = useMemo(() => {
    if (!isFocusMode || !focusedNodeId) {
      return {
        focusedUpstreamIds: new Set<string>(),
        focusedDownstreamIds: new Set<string>(),
        directNeighborIds: new Set<string>()
      };
    }

    const upstream = new Set<string>();
    const downstream = new Set<string>();
    const direct = new Set<string>();

    // Direct neighbors
    initialEdgesData.forEach(e => {
      if (e.target === focusedNodeId) {
        direct.add(e.source);
      }
      if (e.source === focusedNodeId) {
        direct.add(e.target);
      }
    });

    // Full Upstream traversal
    let upQueue = [focusedNodeId];
    while (upQueue.length > 0) {
      const curr = upQueue.shift()!;
      initialEdgesData.forEach(e => {
        if (e.target === curr && !upstream.has(e.source)) {
          upstream.add(e.source);
          upQueue.push(e.source);
        }
      });
    }

    // Full Downstream traversal
    let downQueue = [focusedNodeId];
    while (downQueue.length > 0) {
      const curr = downQueue.shift()!;
      initialEdgesData.forEach(e => {
        if (e.source === curr && !downstream.has(e.target)) {
          downstream.add(e.target);
          downQueue.push(e.target);
        }
      });
    }

    return { focusedUpstreamIds: upstream, focusedDownstreamIds: downstream, directNeighborIds: direct };
  }, [isFocusMode, focusedNodeId, initialEdgesData]);

  // Handler: Select column to trace Column-Level Lineage (CLL) with isolation
  const handleSelectColumn = useCallback((nodeId: string, colName: string) => {
    if (activeTracedColumn?.nodeId === nodeId && activeTracedColumn?.colName === colName) {
      setActiveTracedColumn(null);
    } else {
      setActiveTracedColumn({ nodeId, colName });
      setFocusedNodeId(nodeId);
      setIsFocusMode(true);
      const match = initialNodesData.find(n => n.id === nodeId);
      if (match) {
        setSelectedNode(match);
        setActiveDrawerTab('columns');
        setSelectedEdge(null);
      }
    }
  }, [activeTracedColumn, initialNodesData]);

  // Handler: Click on node/card immediately turns on isolation for that card
  const handleInspectNode = useCallback((node: LineageNodeData) => {
    setSelectedNode(node);
    setFocusedNodeId(node.id);
    setIsFocusMode(true);
    setActiveTracedColumn(null); // Clear specific column to isolate full table flow
    setSelectedEdge(null);
    setActiveDrawerTab('overview');
  }, []);

  // Compute active nodes based on selected relationship filter to hide unconnected ones
  const activeEdgeNodeIds = useMemo(() => {
    if (selectedRelationship === 'all') return null;
    const ids = new Set<string>();
    initialEdgesData.forEach(e => {
      const isVerified = e.confidence === 1.0 || e.inferredBy === 'sqlglot_parser' || e.inferredBy === 'human_verified';
      const isPendingHITL = e.status === 'pending_hitl';
      
      let matches = false;
      if (selectedRelationship === 'verified') {
        matches = isVerified && !isPendingHITL;
      } else if (selectedRelationship === 'llm') {
        matches = !isVerified && !isPendingHITL;
      } else if (selectedRelationship === 'hitl') {
        matches = isPendingHITL;
      }
      
      if (matches) {
        ids.add(e.source);
        ids.add(e.target);
      }
    });
    return ids;
  }, [initialEdgesData, selectedRelationship]);


  // Compute Node Positioning (Clean Layer Columns) with Dimming Support
  const computeInitialNodes = useCallback((mode: LineageViewMode) => {
    const layerBuckets = new globalThis.Map<number, LineageNodeData[]>();

    const filteredNodesData = activeEdgeNodeIds 
      ? initialNodesData.filter(n => activeEdgeNodeIds.has(n.id))
      : initialNodesData;

    filteredNodesData.forEach(n => {
      const col = depthById[n.id] ?? 0;
      const bucket = layerBuckets.get(col) ?? [];
      bucket.push(n);
      layerBuckets.set(col, bucket);
    });
    const maxCol = layerBuckets.size > 0 ? Math.max(...layerBuckets.keys()) : 0;

    const isCompactMode = mode === 'compact';
    const xSpacing = isCompactMode ? 340 : 550;
    const gap = 35;
    const nodeWidth = isCompactMode ? 260 : 300;

    // Helper to calculate height of a node dynamically based on actual column count to prevent overlapping
    const getNodeHeight = (item: LineageNodeData) => {
      const isExpanded = expandedNodeIds.has(item.id) || (activeTracedColumn?.nodeId === item.id) || (selectedNode?.id === item.id);
      const columnCount = item.columns.length;

      // Spacing for affected columns when tracing a column (CLL)
      const affectedCols = nodeAffectedColumns[item.id] || [];
      const hasAffectedCols = affectedCols.length > 0 && activeTracedColumn?.nodeId !== item.id;
      const affectedHeight = hasAffectedCols ? (50 + affectedCols.length * 32) : 0;

      if (isCompactMode) {
        if (isExpanded) {
          // Dynamic columns list container height: 32px per column + 24px header, capped at 220px
          const colsHeight = Math.min(220, columnCount * 32 + 24);
          // Base compact collapsed height (145px) + columns container height + padding (20px)
          return 145 + colsHeight + 20 + affectedHeight;
        } else {
          return 145 + affectedHeight;
        }
      } else {
        if (isExpanded) {
          // Dynamic columns list container height: 33px per column (no capping in full mode)
          const colsHeight = columnCount * 33;
          // Base full height (header, padding, column titles, and action footer) = ~200px
          // Let's add 20px extra padding/breathing room to satisfy "các bảng cách nhau 1 khoảng"
          return 200 + colsHeight + 20 + affectedHeight;
        } else {
          // Collapsed shows up to 4 columns
          const colsCountToShow = Math.min(columnCount, 4);
          const colsHeight = colsCountToShow * 33;
          // Base full height (header, padding, column titles, and action footer) = ~200px
          // Plus "+X more columns" text link (~24px)
          return 200 + colsHeight + 24 + 20 + affectedHeight;
        }
      }
    };

    // Pre-calculate heights for all columns to get tallest column height
    const colHeights: Record<number, number> = {};
    const colNodeHeights: Record<number, number[]> = {};

    layerBuckets.forEach((items, col) => {
      const heights = items.map(item => getNodeHeight(item));
      colNodeHeights[col] = heights;
      colHeights[col] = heights.reduce((sum, h) => sum + h, 0) + Math.max(0, items.length - 1) * gap;
    });

    const canvasHeight = Math.max(...Object.values(colHeights), 100);
    const result: Node[] = [];

    // TB Pre-calculations
    const xGap = 40;
    const layerWidths: Record<number, number> = {};
    layerBuckets.forEach((items, col) => {
      layerWidths[col] = items.length * nodeWidth + Math.max(0, items.length - 1) * xGap;
    });
    const canvasWidth = Math.max(...Object.values(layerWidths), 100);

    const layerYOffset: Record<number, number> = {};
    const yGap = isCompactMode ? 140 : 200;
    let accumulatedY = 60;
    for (let l = 0; l <= maxCol; l++) {
      layerYOffset[l] = accumulatedY;
      const heights = colNodeHeights[l] || [];
      const maxHeight = heights.length > 0 ? Math.max(...heights) : 0;
      accumulatedY += maxHeight + yGap;
    }

    layerBuckets.forEach((items, col) => {
      const columnHeight = colHeights[col];
      const startYOffset = (canvasHeight - columnHeight) / 2;

      let currentY = 60 + startYOffset;

      items.forEach((item, index) => {
        const nodeHeight = colNodeHeights[col][index];
        
        let xPos = 60 + col * xSpacing;
        let yPos = currentY;

        if (layoutDirection === 'TB') {
          const layerWidth = layerWidths[col];
          const startXOffset = (canvasWidth - layerWidth) / 2;
          xPos = 60 + startXOffset + index * (nodeWidth + xGap);
          yPos = layerYOffset[col];
        }

        // Advance currentY for the next node
        currentY += nodeHeight + gap;

        const isImpacted = impactedNodeIds.includes(item.id);
        const isUpstream = upstreamNodeIds.includes(item.id);
        const isColumnMatched = activeTracedColumn ? cllMatchedNodeIds.has(item.id) : false;
        const isFocused = isFocusMode && focusedNodeId === item.id;
        const isDirectNeighbor = directNeighborIds.has(item.id);
        const affectedColumns = nodeAffectedColumns[item.id] || [];

        // Calculate whether this node should be dimmed (mờ các bảng khác)
        let isDimmed = false;
        if (activeTracedColumn) {
          isDimmed = !cllMatchedNodeIds.has(item.id);
        } else if (isFocusMode && focusedNodeId) {
          const isRelevant = item.id === focusedNodeId || focusedUpstreamIds.has(item.id) || focusedDownstreamIds.has(item.id);
          isDimmed = !isRelevant;
        }

        const nodeViewMode: LineageViewMode = activeTracedColumn 
          ? (item.id === activeTracedColumn.nodeId ? 'full' : 'compact')
          : mode;

        const isNodeExpanded = expandedNodeIds.has(item.id) || (activeTracedColumn?.nodeId === item.id) || (selectedNode?.id === item.id);

        result.push({
          id: item.id,
          type: 'customTable',
          position: {
            x: xPos,
            y: yPos
          },
          data: {
            ...item,
            viewMode: nodeViewMode,
            layoutDirection,
            isImpacted,
            isUpstream,
            isFocused,
            isDirectNeighbor,
            isDimmed,
            isColumnMatched,
            affectedColumns,
            isExpanded: isNodeExpanded,
            selectedColumnName: activeTracedColumn?.nodeId === item.id ? activeTracedColumn.colName : null,
            onInspect: (n: LineageNodeData) => handleInspectNode(n),
            onAnalyzeImpact: (n: LineageNodeData) => onAnalyzeImpact(n),
            onSelectColumn: (nodeId: string, colName: string) => handleSelectColumn(nodeId, colName),
            onToggleExpand: () => handleToggleExpandNode(item.id)
          }
        });
      });
    });

    return result;
  }, [
    activeEdgeNodeIds,
    depthById,
    initialNodesData, 
    impactedNodeIds, 
    upstreamNodeIds, 
    onAnalyzeImpact, 
    activeTracedColumn, 
    cllMatchedNodeIds, 
    isFocusMode, 
    focusedNodeId, 
    focusedUpstreamIds, 
    focusedDownstreamIds, 
    directNeighborIds, 
    nodeAffectedColumns, 
    handleInspectNode, 
    handleSelectColumn,
    expandedNodeIds,
    selectedNode,
    handleToggleExpandNode,
    layoutDirection
  ]);

  const initialNodes = useMemo(() => computeInitialNodes(viewMode), [computeInitialNodes, viewMode]);

  // Transform Edges for ReactFlow with Green (Verified) and Orange (LLM) flow animations
  // When activeTracedColumn is active, direct connections go from clicked column to compact tables!
  const initialEdges: Edge[] = useMemo(() => {
    // Filter initial edges data based on the relationship status filter
    const filteredEdgesData = initialEdgesData.filter(e => {
      if (selectedRelationship === 'all') return true;
      const isVerified = e.confidence === 1.0 || e.inferredBy === 'sqlglot_parser' || e.inferredBy === 'human_verified';
      const isPendingHITL = e.status === 'pending_hitl';
      
      if (selectedRelationship === 'verified') {
        return isVerified && !isPendingHITL;
      } else if (selectedRelationship === 'llm') {
        return !isVerified && !isPendingHITL;
      } else if (selectedRelationship === 'hitl') {
        return isPendingHITL;
      }
      return true;
    });

    if (activeTracedColumn && cllEdgesList.length > 0) {
      // 1. Column-to-column connections
      const directCllEdges: Edge[] = cllEdgesList.map(c => {
        const strokeColor = c.isVerified ? '#10b981' : '#f97316';

        return {
          id: c.id,
          source: c.source,
          target: c.target,
          sourceHandle: `out-col-${c.sourceCol}`,
          targetHandle: `in-col-${c.targetCol}`,
          animated: true,
          className: 'cll-active animated',
          style: {
            stroke: strokeColor,
            strokeWidth: 3.2,
            opacity: 1,
            transition: 'opacity 0.2s ease, stroke 0.2s ease'
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: strokeColor,
            width: 14,
            height: 14
          },
          label: c.transformType,
          labelStyle: {
            fontSize: 10,
            fontWeight: 700,
            fill: c.isVerified ? '#047857' : '#c2410c',
            fontFamily: 'monospace'
          },
          labelBgStyle: {
            fill: darkMode ? '#0f172a' : '#ffffff',
            fillOpacity: 0.95,
            rx: 4,
            ry: 4
          }
        };
      });

      // 2. Dimmed background table edges
      const bgEdges: Edge[] = filteredEdgesData.map(e => ({
        id: `bg-${e.id}`,
        source: e.source,
        target: e.target,
        sourceHandle: 'out',
        targetHandle: 'in',
        animated: false,
        className: '',
        style: {
          stroke: '#94a3b8',
          strokeWidth: 1.2,
          opacity: 0.08
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: '#94a3b8',
          width: 10,
          height: 10
        }
      }));

      return [...directCllEdges, ...bgEdges];
    }

    return filteredEdgesData.map(e => {
      const isVerified = e.inferredBy === 'sqlglot_parser' || e.inferredBy === 'human_verified' || e.confidence === 1.0;
      const isPendingHITL = e.status === 'pending_hitl';
      const isImpacted = impactedNodeIds.includes(e.source) && impactedNodeIds.includes(e.target);

      // Visual styling: Green for Verified, Orange for LLM Inferred
      const baseColor = isVerified ? '#10b981' : '#f97316';

      let strokeColor = baseColor;
      let strokeWidth = 2.2;
      let opacity = 1;
      let animated = false;
      let edgeClass = '';

      if (isFocusMode && focusedNodeId) {
        const isSourceRelevant = focusedNodeId === e.source || focusedUpstreamIds.has(e.source) || focusedDownstreamIds.has(e.source);
        const isTargetRelevant = focusedNodeId === e.target || focusedUpstreamIds.has(e.target) || focusedDownstreamIds.has(e.target);
        const isRelevantEdge = isSourceRelevant && isTargetRelevant;

        if (isRelevantEdge) {
          strokeColor = baseColor;
          strokeWidth = 2.6;
          opacity = 1;
          animated = true;
          edgeClass = 'animated';
        } else {
          opacity = 0.12;
          strokeColor = '#94a3b8';
          strokeWidth = 1.2;
          animated = false;
          edgeClass = '';
        }
      } else if (isImpacted) {
        strokeColor = '#ef4444';
        strokeWidth = 2.8;
        animated = true;
        edgeClass = 'impacted animated';
      } else if (isPendingHITL) {
        strokeColor = '#f97316';
        strokeWidth = 2.2;
        animated = true;
        edgeClass = 'animated';
      }

      let strokeDasharray = isPendingHITL ? '5,5' : undefined;

      // Control lineage (filter/join_key/group_key/window_*): không mang dữ liệu,
      // chỉ quyết định hàng nào xuất hiện — vẽ mờ hơn, nét chấm, để không lấn
      // át cạnh data lineage khi 1 cặp bảng có cả hai.
      const isControl = !!e.dependencyKind && e.dependencyKind !== 'output';
      if (isControl && !isImpacted) {
        strokeColor = '#b45309';
        strokeWidth = 1.3;
        opacity = Math.min(opacity, 0.55);
        strokeDasharray = '2,3';
        animated = false;
        edgeClass = '';
      }

      return {
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: 'out',
        targetHandle: 'in',
        animated,
        className: edgeClass,
        style: {
          stroke: strokeColor,
          strokeWidth,
          opacity,
          strokeDasharray,
          transition: 'opacity 0.2s ease, stroke 0.2s ease'
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: strokeColor,
          width: 14,
          height: 14
        },
        label: e.confidence < 1.0 ? `${(e.confidence * 100).toFixed(0)}% AI` : undefined,
        labelStyle: {
          fontSize: 10,
          fontWeight: 700,
          fill: isVerified ? '#047857' : '#c2410c',
          fontFamily: 'monospace'
        },
        labelBgStyle: {
          fill: darkMode ? '#0f172a' : '#ffffff',
          fillOpacity: 0.92,
          rx: 4,
          ry: 4
        },
        data: e as any
      };
    });
  }, [
    initialEdgesData, 
    selectedRelationship,
    impactedNodeIds, 
    activeTracedColumn, 
    cllEdgesList, 
    isFocusMode, 
    focusedNodeId, 
    focusedUpstreamIds, 
    focusedDownstreamIds, 
    darkMode
  ]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync state
  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  // Fit viewport automatically when layoutDirection or relationship filter changes
  useEffect(() => {
    if (rfInstance) {
      const timer = setTimeout(() => {
        rfInstance.fitView({ duration: 600, padding: 0.15 });
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [layoutDirection, selectedRelationship, rfInstance]);

  // Handler: Reset layout / node positions to default
  const handleResetPositions = useCallback(() => {
    const freshNodes = computeInitialNodes(viewMode);
    setNodes(freshNodes);
    setTimeout(() => {
      rfInstance?.fitView({ duration: 500, padding: 0.15 });
    }, 50);
  }, [computeInitialNodes, viewMode, setNodes, rfInstance]);

  // Handler: Change view mode (Tinh gọn collapses all details)
  const handleChangeViewMode = (newMode: LineageViewMode) => {
    setViewMode(newMode);
    setExpandedNodeIds(new Set());
    const updated = computeInitialNodes(newMode);
    setNodes(updated);
    setTimeout(() => {
      rfInstance?.fitView({ duration: 400, padding: 0.15 });
    }, 50);
  };

  // Handler: Click blank canvas to disable isolation mode and clear selection
  const onPaneClick = useCallback(() => {
    setIsFocusMode(false);
    setFocusedNodeId(null);
    setActiveTracedColumn(null);
    setSelectedNode(null);
    setSelectedEdge(null);
    setExpandedNodeIds(new Set());
  }, []);

  // Filtered nodes (Search, Layer)
  const filteredNodes = useMemo(() => {
    return nodes.filter(node => {
      const data = node.data as unknown as LineageNodeData;
      
      // Search term
      const matchesSearch = !searchTerm || 
        data.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        data.schema.toLowerCase().includes(searchTerm.toLowerCase()) ||
        data.tags?.some(t => t.toLowerCase().includes(searchTerm.toLowerCase())) ||
        data.columns.some(c => c.name.toLowerCase().includes(searchTerm.toLowerCase()));

      // Layer Filter
      const matchesLayer = selectedLayer === 'all' || data.layer === selectedLayer;

      return matchesSearch && matchesLayer;
    });
  }, [nodes, searchTerm, selectedLayer]);

  // Click on node in graph
  const onNodeClick = useCallback((_: any, node: Node) => {
    const matched = initialNodesData.find(n => n.id === node.id);
    if (matched) {
      handleInspectNode(matched);
    }
  }, [initialNodesData, handleInspectNode]);

  // Click on edge (Inspect Process / Transformation)
  const onEdgeClick = useCallback((_: any, edge: Edge) => {
    const matched = initialEdgesData.find(e => e.id === edge.id);
    if (matched) {
      setSelectedEdge(matched);
      setSelectedNode(null);
    }
  }, [initialEdgesData]);

  // Copy SQL helper
  const handleCopySql = (sql: string) => {
    navigator.clipboard.writeText(sql);
    setCopiedSql(true);
    setTimeout(() => setCopiedSql(false), 2000);
  };

  // Duyệt/Từ chối cạnh HITL ngay tại drawer thay vì bắt user rời sang trang
  // HITL Queue — id trong LineageEdgeData của cạnh pending chính là edge_id
  // thật (pendingEdgesToLineageData không đổi id), dùng thẳng được.
  const handleConfirmSelectedEdge = async () => {
    if (!selectedEdge || !onConfirmPendingEdge) return;
    setEdgeReviewBusy(true);
    try {
      await onConfirmPendingEdge(selectedEdge.id);
      setSelectedEdge(null);
    } finally {
      setEdgeReviewBusy(false);
    }
  };

  const handleRejectSelectedEdge = async () => {
    if (!selectedEdge || !onRejectPendingEdge) return;
    setEdgeReviewBusy(true);
    try {
      await onRejectPendingEdge(selectedEdge.id);
      setSelectedEdge(null);
    } finally {
      setEdgeReviewBusy(false);
    }
  };

  const handleAskCopilotAboutSelectedEdge = () => {
    if (!selectedEdge || !onAskCopilotAboutEdge) return;
    const lines = [
      `Cạnh này đang chờ duyệt (HITL): \`${selectedEdge.source}\` -> \`${selectedEdge.target}\`, nguồn suy luận ${selectedEdge.inferredBy}, confidence ${(selectedEdge.confidence * 100).toFixed(0)}%.`,
    ];
    if (selectedEdge.reasoning) lines.push(`Lý do agent đưa ra: ${selectedEdge.reasoning}`);
    if (selectedEdge.fallbackReason) lines.push(`Vì sao parser tĩnh fail: ${selectedEdge.fallbackReason}`);
    if (selectedEdge.matchedText) {
      lines.push(
        `Đoạn SQL được trích dẫn làm căn cứ (${selectedEdge.citationVerified === false ? 'CHƯA xác minh được có thật trong file gốc' : 'đã xác minh có trong file gốc'}): ${selectedEdge.matchedText}`
      );
    }
    if (selectedEdge.filePath) lines.push(`File nguồn: ${selectedEdge.filePath}`);
    lines.push('Bạn có cho rằng cạnh này đủ tin cậy để duyệt không, và vì sao?');
    onAskCopilotAboutEdge(lines.join('\n'));
  };

  return (
    <div className="relative w-full h-full flex overflow-hidden">
      
      {/* 1. Atlan-Style Control & Filter Toolbar (Top Header) */}
      <div className="absolute top-4 left-4 z-20 flex flex-wrap items-center gap-2 bg-white/95 dark:bg-slate-900/95 backdrop-blur p-2 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-xl max-w-[calc(100vw-6rem)]">
        
        {/* View Mode Segmented Selector (Compact View / Full View) */}
        <div className="flex items-center bg-slate-100 dark:bg-slate-800 p-0.5 rounded-xl border border-slate-200 dark:border-slate-700">
          <button
            id="view-mode-compact-btn"
            onClick={() => handleChangeViewMode('compact')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-semibold transition-all cursor-pointer ${
              viewMode === 'compact'
                ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-sm'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white'
            }`}
            title="Dạng tinh gọn: Tích hợp Column-Level Lineage (CLL), hover/click để xem cột & truy vết"
          >
            <LayoutGrid className="w-3.5 h-3.5" />
            <span>Compact View</span>
          </button>

          <button
            id="view-mode-full-btn"
            onClick={() => handleChangeViewMode('full')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-semibold transition-all cursor-pointer ${
              viewMode === 'full'
                ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-sm'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white'
            }`}
            title="Dạng đầy đủ: Tích hợp Column-Level Lineage (CLL), hiển thị schema và nhấp cột để truy vết"
          >
            <List className="w-3.5 h-3.5" />
            <span>Full View</span>
          </button>
        </div>

        {/* Search Box */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            id="explorer-search-input"
            type="text"
            placeholder="Search tables, schema, columns..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-8 pr-3 py-1.5 w-40 sm:w-56 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
          />
          {searchTerm && (
            <button 
              onClick={() => setSearchTerm('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>

        {/* Relationship Status Filter */}
        <div className="hidden sm:flex items-center">
          <select
            id="explorer-relationship-filter"
            value={selectedRelationship}
            onChange={(e) => setSelectedRelationship(e.target.value)}
            className="py-1.5 px-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-800 dark:text-slate-200 cursor-pointer focus:outline-none font-mono"
          >
            <option value="all">All Status</option>
            <option value="verified">🟢 Verified Flow</option>
            <option value="llm">🟠 LLM Generated</option>
            <option value="hitl">🟠--- HITL Queue</option>
          </select>
        </div>

        {/* Graph Clear Action on DAG (Danger Zone) */}
        {canClearGraph && onClearGraph && (
          <button
            id="clear-graph-btn"
            onClick={() => {
              setIsClearConfirmOpen(true);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/30 dark:hover:bg-rose-950/50 text-rose-600 dark:text-rose-400 transition-all cursor-pointer border border-rose-200 dark:border-rose-900/50 hover:border-rose-300 dark:hover:border-rose-800 font-mono text-xs font-semibold shadow-sm"
            title="Clear entire graph (Danger Zone)"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear Graph</span>
          </button>
        )}
      </div>

      {/* 2. Active Column-Level Lineage (CLL) Banner Indicator */}
      {activeTracedColumn && (
        <div className="absolute top-20 left-4 z-20 flex items-center gap-3 px-4 py-2 bg-indigo-900/95 text-white rounded-2xl border border-indigo-700 shadow-xl text-xs animate-in slide-in-from-top duration-200 backdrop-blur">
          <div className="flex items-center gap-2">
            <span className="p-1 rounded-lg bg-indigo-600 text-white">
              <Sparkles className="w-3.5 h-3.5" />
            </span>
            <span>Tracing Column:</span>
            <strong className="text-amber-300 underline font-bold font-mono">
              {activeTracedColumn.nodeId}.{activeTracedColumn.colName}
            </strong>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-indigo-200 pl-2 border-l border-indigo-700">
            <span>{cllMatchedNodeIds.size} bảng trong luồng dữ liệu</span>
            <span>&bull;</span>
            <span>{cllMatchedEdgeIds.size} bước chuyển đổi</span>
          </div>

          <button
            onClick={() => setActiveTracedColumn(null)}
            className="px-2 py-0.5 rounded-lg bg-indigo-800 hover:bg-indigo-700 text-white text-[10px] font-bold border border-indigo-600 cursor-pointer transition-colors"
          >
            Clear Trace &times;
          </button>
        </div>
      )}

      {/* 3. Atlan Top-Right Legend & Status Bar */}
      {isLegendCollapsed ? (
        <button
          onClick={() => setIsLegendCollapsed(false)}
          className={`absolute top-4 z-20 p-2 bg-white/95 dark:bg-slate-900/95 backdrop-blur rounded-xl border border-slate-200 dark:border-slate-800 shadow-md text-slate-500 hover:text-indigo-500 dark:hover:text-indigo-400 cursor-pointer transition-all duration-300 ${
            selectedNode ? 'right-[450px]' : 'right-4'
          }`}
          title="Show Legend"
        >
          <Info className="w-4 h-4 text-indigo-500" />
        </button>
      ) : (
        <div className={`absolute top-4 z-20 flex flex-wrap items-center gap-3.5 px-3 py-1.5 bg-white/95 dark:bg-slate-900/95 backdrop-blur rounded-xl border border-slate-200 dark:border-slate-800 text-[11px] text-slate-600 dark:text-slate-300 shadow-md transition-all duration-300 ${
          selectedNode ? 'right-[450px]' : 'right-4'
        }`}>
          <span className="font-bold text-slate-900 dark:text-white flex items-center gap-1">
            <Info className="w-3.5 h-3.5 text-indigo-500" />
            <span>Lineage Flow:</span>
          </span>
          <div className="flex items-center gap-1.5" title="Đường kết nối màu xanh lá biểu thị luồng dữ liệu đã được Parser sqlglot/Kỹ sư dữ liệu xác thực (100%)">
            <span className="w-5 h-[3px] bg-emerald-500 rounded-full shadow-sm shadow-emerald-500/50 inline-block" />
            <span className="text-emerald-700 dark:text-emerald-400 font-semibold">Verified Flow</span>
          </div>
          <div className="flex items-center gap-1.5" title="Đường kết nối màu cam biểu thị luồng suy luận tự động bởi Gemini LLM">
            <span className="w-5 h-[3px] bg-orange-500 rounded-full shadow-sm shadow-orange-500/50 inline-block" />
            <span className="text-orange-600 dark:text-orange-400 font-semibold">LLM Generated</span>
          </div>
          <div className="flex items-center gap-1.5" title="Đường đứt nét màu cam biểu thị luồng đang chờ xác thực HITL">
            <span className="w-5 h-0 border-t-2 border-dashed border-orange-500 inline-block" />
            <span className="text-orange-600 dark:text-orange-400 font-semibold">HITL Queue</span>
          </div>
          {isFocusMode && (
            <div className="flex items-center gap-1 pl-1.5 border-l border-slate-200 dark:border-slate-700">
              <span className="px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 text-[10px] font-bold">
                Isolated
              </span>
            </div>
          )}
          <button
            onClick={() => setIsLegendCollapsed(true)}
            className="p-0.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors cursor-pointer ml-1"
            title="Hide Legend"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* 4. React Flow Graph Canvas */}
      <div className={`h-full transition-all duration-300 ${
        (selectedNode || selectedEdge) ? 'w-full lg:w-[calc(100%-440px)]' : 'w-full'
      }`}>
        <ReactFlow
          nodes={filteredNodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onPaneClick={onPaneClick}
          onInit={setRfInstance}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.2}
          maxZoom={1.5}
          attributionPosition="bottom-right"
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1.5}
            color={darkMode ? '#334155' : '#cbd5e1'}
          />
          <Controls 
            showFitView={false} 
            showInteractive={false}
            className="!bg-slate-900 !border-slate-800 !rounded-2xl !shadow-lg" 
          >
            <ControlButton 
              onClick={handleResetPositions}
              title="Khôi phục vị trí các bảng về bố cục phân tầng chuẩn"
              aria-label="Reset Positions"
              className="reset-position-button"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </ControlButton>
            <ControlButton 
              onClick={() => setShowMiniMap(!showMiniMap)}
              title={showMiniMap ? "Ẩn bản đồ thu nhỏ" : "Hiện bản đồ thu nhỏ"}
              aria-label="Toggle MiniMap"
            >
              <Map className="w-3.5 h-3.5" />
            </ControlButton>
          </Controls>
          {showMiniMap && (
            <MiniMap
              nodeStrokeColor={darkMode ? '#475569' : '#cbd5e1'}
              nodeColor={darkMode ? '#1e293b' : '#f1f5f9'}
              nodeBorderRadius={4}
              style={{ width: 140, height: 100 }}
              className="!bg-white/90 dark:!bg-slate-900/90 !border-slate-200 dark:!border-slate-800 !rounded-2xl !shadow-lg !bottom-4 !left-[80px]"
            />
          )}
        </ReactFlow>
      </div>

      {/* 5. Atlan 360° Metadata Slide-over Profile Drawer */}
      {selectedNode && (
        <aside 
          id="node-inspector-drawer"
          className="absolute right-4 top-4 bottom-4 w-[420px] max-w-[calc(100vw-3rem)] z-30 bg-white/95 dark:bg-slate-900/95 backdrop-blur border border-slate-200 dark:border-slate-800 rounded-3xl shadow-2xl p-5 flex flex-col justify-between overflow-hidden animate-in slide-in-from-right duration-200"
        >
          {/* Drawer Top Header */}
          <div>
            <div className="flex items-start justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
              <div className="min-w-0 flex-1 pr-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950 px-2 py-0.5 rounded-md border border-indigo-200 dark:border-indigo-800">
                    {selectedNode.schema}
                  </span>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {selectedNode.layer.replace('_', ' ').toUpperCase()}
                  </span>
                </div>

                <h3 className="font-mono text-lg font-bold text-slate-900 dark:text-white truncate" title={selectedNode.name}>
                  {selectedNode.name}
                </h3>
              </div>

              <div className="flex items-center gap-1">
                <button
                  id="close-drawer-btn"
                  onClick={() => setSelectedNode(null)}
                  className="p-1.5 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Atlan Drawer Tabs */}
            <div className="flex items-center gap-1 border-b border-slate-100 dark:border-slate-800 pt-2 text-xs font-semibold">
              <button
                onClick={() => setActiveDrawerTab('overview')}
                className={`px-3 py-2 border-b-2 transition-colors cursor-pointer ${
                  activeDrawerTab === 'overview'
                    ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 font-bold'
                    : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white'
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => setActiveDrawerTab('columns')}
                className={`px-3 py-2 border-b-2 transition-colors cursor-pointer flex items-center gap-1 ${
                  activeDrawerTab === 'columns'
                    ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 font-bold'
                    : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white'
                }`}
              >
                <span>Columns</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-100 dark:bg-slate-800">
                  {selectedNode.columns.length}
                </span>
              </button>
              <button
                onClick={() => setActiveDrawerTab('lineage')}
                className={`px-3 py-2 border-b-2 transition-colors cursor-pointer ${
                  activeDrawerTab === 'lineage'
                    ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 font-bold'
                    : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white'
                }`}
              >
                Lineage
              </button>
              {selectedNode.rawSql && (
                <button
                  onClick={() => setActiveDrawerTab('sql')}
                  className={`px-3 py-2 border-b-2 transition-colors cursor-pointer ${
                    activeDrawerTab === 'sql'
                      ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 font-bold'
                      : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-white'
                  }`}
                >
                  SQL Code
                </button>
              )}
            </div>
          </div>

          {/* Drawer Body Scroll Area */}
          <div className="flex-1 overflow-y-auto py-3 space-y-3 custom-scrollbar">
            
            {/* TAB 1: OVERVIEW & GOVERNANCE */}
            {activeDrawerTab === 'overview' && (
              <div className="space-y-3 text-xs">
                {/* Description */}
                <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-2xl border border-slate-100 dark:border-slate-800">
                  <span className="text-[10px] text-slate-400 block mb-1 uppercase font-bold">
                    Asset Description
                  </span>
                  <p className="text-slate-700 dark:text-slate-300 leading-relaxed">
                    {selectedNode.description || 'Chưa có mô tả'}
                  </p>
                  {selectedNode.description && (
                    <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                      {selectedNode.descriptionLabel && <span className="rounded bg-slate-200/70 px-1.5 py-0.5 text-slate-600 dark:bg-slate-700 dark:text-slate-300">{selectedNode.descriptionLabel}</span>}
                      {selectedNode.descriptionSource && <span className="rounded bg-slate-200/70 px-1.5 py-0.5 text-slate-600 dark:bg-slate-700 dark:text-slate-300">{selectedNode.descriptionSource}</span>}
                      {selectedNode.descriptionIsStale && <span className="rounded bg-amber-100 px-1.5 py-0.5 font-semibold text-amber-700 dark:bg-amber-950 dark:text-amber-300">Mô tả đã cũ</span>}
                    </div>
                  )}
                </div>

                {/* Key Governance Metrics Grid */}
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="p-2.5 bg-slate-50 dark:bg-slate-800/60 rounded-2xl border border-slate-100 dark:border-slate-800">
                    <span className="text-slate-400 block text-[10px]">Data Quality SLA</span>
                    <span className="font-bold text-emerald-600 dark:text-emerald-400 text-sm flex items-center gap-1 mt-0.5">
                      <ShieldCheck className="w-3.5 h-3.5" />
                      {selectedNode.qualityScore || 99.5}% Passed
                    </span>
                  </div>

                  <div className="p-2.5 bg-slate-50 dark:bg-slate-800/60 rounded-2xl border border-slate-100 dark:border-slate-800">
                    <span className="text-slate-400 block text-[10px]">Freshness SLA</span>
                    <span className="font-bold text-slate-800 dark:text-slate-200 text-sm flex items-center gap-1 mt-0.5">
                      <Clock className="w-3.5 h-3.5 text-indigo-500" />
                      {selectedNode.freshness || 'Real-time'}
                    </span>
                  </div>

                  <div className="p-2.5 bg-slate-50 dark:bg-slate-800/60 rounded-2xl border border-slate-100 dark:border-slate-800">
                    <span className="text-slate-400 block text-[10px]">Asset Owner</span>
                    <span className="font-bold text-slate-800 dark:text-slate-200 truncate block mt-0.5">
                      {selectedNode.owner}
                    </span>
                  </div>

                  <div className="p-2.5 bg-slate-50 dark:bg-slate-800/60 rounded-2xl border border-slate-100 dark:border-slate-800">
                    <span className="text-slate-400 block text-[10px]">Row Count</span>
                    <span className="font-bold text-slate-800 dark:text-slate-200 block mt-0.5">
                      {selectedNode.rowCount ? selectedNode.rowCount.toLocaleString() : 'N/A'}
                    </span>
                  </div>
                </div>

                {/* Business Glossary Tags */}
                <div>
                  <span className="text-[10px] text-slate-400 block mb-1.5 uppercase font-bold">
                    Business Glossary &amp; Tags
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedNode.tags.map((tag, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 rounded-lg bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 text-[10px] flex items-center gap-1"
                      >
                        <Hash className="w-2.5 h-2.5" />
                        <span>{tag}</span>
                      </span>
                    ))}
                    {selectedNode.isDynamicSql && (
                      <span className="px-2 py-0.5 rounded-lg bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800 font-mono text-[10px]">
                        Dynamic SQL
                      </span>
                    )}
                  </div>
                </div>

                {/* File Path */}
                {selectedNode.filePath && (
                  <div className="p-2 bg-slate-50 dark:bg-slate-800/40 rounded-xl border border-slate-100 dark:border-slate-800 text-[10px] font-mono text-slate-500">
                    <span className="text-slate-400 block">Repository File:</span>
                    <code className="text-slate-700 dark:text-slate-300">{selectedNode.filePath}</code>
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: SCHEMA & COLUMNS (Trace CLL 1-Click) */}
            {activeDrawerTab === 'columns' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
                  <span>Click any column to trace end-to-end lineage</span>
                </div>

                <div className="space-y-1.5">
                  {selectedNode.columns.map((col, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-800 space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-slate-900 dark:text-white">
                          {col.isPrimaryKey && <span className="text-amber-500 text-[10px]">PK</span>}
                          {col.isForeignKey && <span className="text-indigo-500 text-[10px]">FK</span>}
                          <span>{col.name}</span>
                        </div>

                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] font-mono text-slate-400 bg-slate-200/60 dark:bg-slate-700/60 px-1.5 py-0.5 rounded">
                            {col.type}
                          </span>
                          <button
                            onClick={() => handleSelectColumn(selectedNode.id, col.name)}
                            className="px-2 py-0.5 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-950 dark:hover:bg-indigo-900 text-indigo-600 dark:text-indigo-300 rounded text-[10px] font-mono font-semibold border border-indigo-200 dark:border-indigo-800 cursor-pointer flex items-center gap-1"
                          >
                            <Sparkles className="w-2.5 h-2.5" />
                            <span>Trace CLL</span>
                          </button>
                        </div>
                      </div>

                      {col.description && (
                        <p className="text-[11px] text-slate-500 dark:text-slate-400">
                          {col.description}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* TAB 3: LINEAGE & BLAST RADIUS — gom nhóm theo bảng hàng xóm, liệt
                kê từng cột thay vì lặp lại tên bảng 1 lần / 1 cạnh mức cột. */}
            {activeDrawerTab === 'lineage' && (() => {
              type ColPair = { neighborCol: string; selfCol: string; transformType?: string };
              type ControlDep = { neighborCol: string; kind: string };
              type NeighborGroup = {
                id: string;
                name: string;
                badge: string;
                cols: ColPair[];
                controls: ControlDep[];
              };
              const DEP_LABELS: Record<string, string> = {
                filter: 'lọc (WHERE)',
                join_key: 'khoá JOIN',
                group_key: 'GROUP BY',
                window_partition: 'PARTITION BY',
                window_order: 'ORDER BY (window)',
              };
              const buildGroups = (dir: 'upstream' | 'downstream'): NeighborGroup[] => {
                const rel = initialEdgesData.filter(e =>
                  dir === 'upstream' ? e.target === selectedNode.id : e.source === selectedNode.id,
                );
                const byNeighbor = new globalThis.Map<string, NeighborGroup>();
                for (const e of rel) {
                  const neighborId = dir === 'upstream' ? e.source : e.target;
                  const node = initialNodesData.find(n => n.id === neighborId);
                  let g = byNeighbor.get(neighborId);
                  if (!g) {
                    g = {
                      id: neighborId,
                      name: node?.name || neighborId,
                      badge: dir === 'upstream' ? e.inferredBy : (node?.layer || e.inferredBy),
                      cols: [],
                      controls: [],
                    };
                    byNeighbor.set(neighborId, g);
                  }
                  if (e.dependencyKind && e.dependencyKind !== 'output') {
                    // Control lineage: cạnh nào cũng là neighbor.controlColumn ảnh
                    // hưởng selectedNode (upstream: neighbor lọc/join vào self;
                    // downstream: self lọc/join vào neighbor — dùng chung field).
                    const col = e.controlColumn;
                    if (col && !g.controls.some(c => c.neighborCol === col && c.kind === e.dependencyKind)) {
                      g.controls.push({ neighborCol: col, kind: e.dependencyKind });
                    }
                    continue;
                  }
                  for (const m of e.columnMappings ?? []) {
                    const selfCol = dir === 'upstream' ? m.targetCol : m.sourceCol;
                    const neighborCol = dir === 'upstream' ? m.sourceCol : m.targetCol;
                    if (!selfCol || !neighborCol) continue;
                    if (!g.cols.some(c => c.neighborCol === neighborCol && c.selfCol === selfCol)) {
                      g.cols.push({ neighborCol, selfCol, transformType: m.transformType });
                    }
                  }
                }
                return Array.from(byNeighbor.values());
              };

              const renderSection = (
                title: string,
                dir: 'upstream' | 'downstream',
                arrow: '←' | '→',
                accent: string,
              ) => {
                const groups = buildGroups(dir);
                const totalCols = groups.reduce((s, g) => s + g.cols.length, 0);
                const totalCtrl = groups.reduce((s, g) => s + g.controls.length, 0);
                return (
                  <div>
                    <span className="font-mono text-[10px] font-bold text-slate-400 uppercase block mb-1.5">
                      {title} ({groups.length} bảng{totalCols > 0 ? ` · ${totalCols} cột dữ liệu` : ''}
                      {totalCtrl > 0 ? ` · ${totalCtrl} cột điều kiện` : ''})
                    </span>
                    {groups.length === 0 ? (
                      <p className="text-[11px] text-slate-400 italic px-1">Không có.</p>
                    ) : (
                      <div className="space-y-1.5">
                        {groups.map(g => (
                          <div key={g.id} className="rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 overflow-hidden">
                            <div className="px-2 py-1.5 flex items-center justify-between font-mono text-[11px] border-b border-slate-100 dark:border-slate-800/80">
                              <span className="font-bold text-slate-800 dark:text-slate-200">{g.name}</span>
                              <span className={`text-[10px] font-semibold ${accent}`}>{g.badge}</span>
                            </div>
                            {g.cols.length === 0 && g.controls.length === 0 ? (
                              <div className="px-2 py-1.5 text-[10px] text-slate-400 italic font-mono">
                                Chỉ liên kết mức bảng (không có chi tiết cột)
                              </div>
                            ) : (
                              <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
                                {g.cols.map((c, i) => (
                                  <button
                                    key={`d${i}`}
                                    onClick={() => handleSelectColumn(selectedNode.id, c.selfCol)}
                                    className="w-full px-2 py-1.5 flex items-center justify-between gap-2 font-mono text-[11px] hover:bg-white dark:hover:bg-slate-900/60 cursor-pointer transition-colors text-left"
                                  >
                                    <span className="flex items-center gap-1.5 min-w-0">
                                      <span className="font-semibold text-slate-700 dark:text-slate-200 truncate">
                                        {g.name}.<span className="text-indigo-600 dark:text-indigo-400">{c.neighborCol}</span>
                                      </span>
                                      <span className="text-slate-400 shrink-0">{arrow} {c.selfCol}</span>
                                    </span>
                                    {c.transformType && (
                                      <span className="text-[9px] uppercase text-slate-400 shrink-0">{c.transformType}</span>
                                    )}
                                  </button>
                                ))}
                                {g.controls.map((c, i) => (
                                  <div
                                    key={`c${i}`}
                                    className="w-full px-2 py-1.5 flex items-center justify-between gap-2 font-mono text-[11px] bg-amber-50/50 dark:bg-amber-950/20"
                                    title="Control lineage: cột này không mang dữ liệu vào bảng kia nhưng quyết định hàng nào xuất hiện"
                                  >
                                    <span className="flex items-center gap-1.5 min-w-0">
                                      <span className="font-semibold text-slate-700 dark:text-slate-200 truncate">
                                        {g.name}.<span className="text-amber-700 dark:text-amber-400">{c.neighborCol}</span>
                                      </span>
                                    </span>
                                    <span className="text-[9px] uppercase text-amber-700 dark:text-amber-400 shrink-0">
                                      {DEP_LABELS[c.kind] ?? c.kind}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              };

              return (
                <div className="space-y-3 text-xs">
                  {renderSection('Direct Upstream Sources', 'upstream', '→', 'text-emerald-600 dark:text-emerald-400')}
                  {renderSection('Direct Downstream Consumers', 'downstream', '←', 'text-indigo-600 dark:text-indigo-400')}
                  <p className="text-[10px] text-slate-400 px-1 pt-1">
                    Bấm một cột dữ liệu để truy vết Column-Level Lineage. Hàng nền vàng = <span className="text-amber-700 dark:text-amber-400">cột điều kiện</span> (lọc/JOIN/GROUP BY) — không mang dữ liệu nhưng quyết định hàng nào xuất hiện.
                  </p>
                </div>
              );
            })()}

            {/* TAB 4: SQL DEFINITION */}
            {activeDrawerTab === 'sql' && selectedNode.rawSql && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono text-slate-400 font-bold uppercase">
                    dbt SQL Model Code
                  </span>
                  <button
                    onClick={() => handleCopySql(selectedNode.rawSql || '')}
                    className="flex items-center gap-1 px-2 py-0.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 rounded text-[10px] font-mono text-slate-600 dark:text-slate-300 cursor-pointer"
                  >
                    {copiedSql ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                    <span>{copiedSql ? 'Copied' : 'Copy'}</span>
                  </button>
                </div>
                <pre className="p-3 bg-slate-950 text-slate-200 rounded-2xl text-[11px] font-mono overflow-x-auto border border-slate-800 max-h-72 leading-relaxed">
                  {selectedNode.rawSql}
                </pre>
              </div>
            )}

          </div>

          {/* Drawer Bottom Actions */}
          <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex gap-2">
            <button
              id="drawer-impact-btn"
              onClick={() => onAnalyzeImpact(selectedNode)}
              className="flex-1 py-2.5 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 shadow-md shadow-amber-500/20 cursor-pointer transition-all font-mono"
            >
              <Zap className="w-4 h-4" />
              <span>Simulate Blast Radius</span>
            </button>
          </div>
        </aside>
      )}

      {/* 6. Atlan Process / Edge Transformation Inspector Drawer */}
      {selectedEdge && (
        <aside 
          id="edge-inspector-drawer"
          className="absolute right-4 top-4 bottom-4 w-96 z-30 bg-white/95 dark:bg-slate-900/95 backdrop-blur border border-slate-200 dark:border-slate-800 rounded-3xl shadow-2xl p-5 flex flex-col justify-between overflow-y-auto animate-in slide-in-from-right duration-200"
        >
          <div className="space-y-4">
            <div className="flex items-start justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
              <div>
                <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                  Lineage Transformation Process
                </span>
                <h3 className="font-mono text-sm font-bold text-slate-900 dark:text-white mt-1">
                  `{selectedEdge.source}` &rarr; `{selectedEdge.target}`
                </h3>
              </div>
              <button
                onClick={() => setSelectedEdge(null)}
                className="p-1.5 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {selectedEdge.dependencyKind && selectedEdge.dependencyKind !== 'output' && (
              <div className="p-3 rounded-2xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 space-y-1 text-xs">
                <span className="flex items-center gap-1.5 text-[10px] font-mono font-bold text-amber-700 dark:text-amber-300 uppercase">
                  Control lineage · {({
                    filter: 'lọc (WHERE/HAVING)', join_key: 'khoá JOIN', group_key: 'GROUP BY',
                    window_partition: 'PARTITION BY', window_order: 'ORDER BY (window)',
                  } as Record<string, string>)[selectedEdge.dependencyKind] ?? selectedEdge.dependencyKind}
                </span>
                <p className="text-amber-800 dark:text-amber-200 leading-relaxed">
                  Cột <strong>{selectedEdge.controlColumn}</strong> của <code>{selectedEdge.source}</code> KHÔNG mang giá trị
                  vào cột nào của <code>{selectedEdge.target}</code>, nhưng quyết định <strong>hàng nào</strong> của
                  <code> {selectedEdge.target}</code> xuất hiện. Xoá/đổi tên cột này làm model đích lỗi biên dịch;
                  đổi kiểu/giá trị làm số hàng thay đổi mà không cột output nào báo.
                </p>
              </div>
            )}

            {/* Inference & Parser Info */}
            <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-2xl border border-slate-100 dark:border-slate-800 space-y-2 text-xs font-mono">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Resolution Engine:</span>
                <span className="font-bold text-emerald-600 dark:text-emerald-400">{selectedEdge.inferredBy}</span>
              </div>
              <div className="flex items-start justify-between gap-2">
                <span className="text-slate-400 shrink-0">Resolution Method:</span>
                <span className="font-bold text-slate-900 dark:text-white text-right">
                  {selectedEdge.resolutionMethod
                    ? selectedEdge.resolutionMethod
                    : selectedEdge.inferredBy === 'sqlglot_parser'
                      ? 'phân giải tĩnh (AST)'
                      : '—'}
                  {selectedEdge.resolutionMethod && RESOLUTION_METHOD_LABELS[selectedEdge.resolutionMethod] && (
                    <span className="block font-normal text-[10px] text-slate-400">
                      {RESOLUTION_METHOD_LABELS[selectedEdge.resolutionMethod]}
                    </span>
                  )}
                  {!selectedEdge.resolutionMethod && selectedEdge.inferredBy === 'sqlglot_parser' && (
                    <span className="block font-normal text-[10px] text-slate-400">
                      Parser sqlglot phân giải tất định từ cây cú pháp
                    </span>
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Confidence SLA:</span>
                <span className="font-bold text-slate-900 dark:text-white">{(selectedEdge.confidence * 100).toFixed(0)}%</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Status:</span>
                <span className="font-bold text-indigo-500 uppercase">{selectedEdge.status}</span>
              </div>
            </div>

            {/* Reasoning / SQL details */}
            {selectedEdge.reasoning && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-mono font-bold text-slate-400 uppercase">
                    Transformation Logic
                  </span>
                  {selectedEdge.reasoningDetail && (
                    <button
                      onClick={() => setShowReasoningDetail(v => !v)}
                      className="flex items-center gap-1 px-2 py-0.5 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-[10px] font-mono font-semibold text-slate-600 dark:text-slate-300 cursor-pointer transition-colors"
                    >
                      {showReasoningDetail ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                      <span>{showReasoningDetail ? 'Thu gọn' : 'Chi tiết'}</span>
                    </button>
                  )}
                </div>
                <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed bg-slate-50 dark:bg-slate-800/40 p-3 rounded-2xl border border-slate-100 dark:border-slate-800">
                  {selectedEdge.reasoning}
                </p>
                {showReasoningDetail && selectedEdge.reasoningDetail && (
                  <p className="mt-2 text-xs text-slate-600 dark:text-slate-300 leading-relaxed bg-indigo-50/60 dark:bg-indigo-950/30 p-3 rounded-2xl border border-indigo-100 dark:border-indigo-900">
                    {selectedEdge.reasoningDetail}
                    {selectedEdge.lineRange && (
                      <span className="block mt-1.5 text-[10px] font-mono text-slate-400">
                        Dòng {selectedEdge.lineRange[0]}
                        {selectedEdge.lineRange[1] !== selectedEdge.lineRange[0] ? `–${selectedEdge.lineRange[1]}` : ''} trong file nguồn
                      </span>
                    )}
                  </p>
                )}
              </div>
            )}

            {/* Vì sao parser fail, phải chuyển qua LLM fallback */}
            {selectedEdge.fallbackReason && (
              <div>
                <span className="text-[10px] font-mono font-bold text-slate-400 uppercase block mb-1">
                  Fallback Reason
                </span>
                <p className="text-xs text-amber-700 dark:text-amber-300 leading-relaxed bg-amber-50 dark:bg-amber-950/30 p-3 rounded-2xl border border-amber-100 dark:border-amber-900">
                  {selectedEdge.fallbackReason}
                </p>
              </div>
            )}

            {/* File nguồn */}
            {selectedEdge.filePath && (
              <div>
                <span className="text-[10px] font-mono font-bold text-slate-400 uppercase block mb-1">
                  Source File
                </span>
                <p className="text-[11px] font-mono text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-800/40 px-3 py-2 rounded-xl border border-slate-100 dark:border-slate-800 break-all">
                  {selectedEdge.filePath}
                </p>
              </div>
            )}

            {/* Đoạn SQL LLM trích dẫn làm căn cứ + xác minh trích dẫn có thật trong file không */}
            {selectedEdge.matchedText && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-mono font-bold text-slate-400 uppercase">
                    Cited Evidence
                  </span>
                  {selectedEdge.citationVerified === true && (
                    <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 className="w-3 h-3" /> Verified
                    </span>
                  )}
                  {selectedEdge.citationVerified === false && (
                    <span className="flex items-center gap-1 text-[10px] font-bold text-rose-600 dark:text-rose-400">
                      <AlertCircle className="w-3 h-3" /> Không tìm thấy trong file gốc
                    </span>
                  )}
                </div>
                <pre className="text-[11px] font-mono text-slate-700 dark:text-slate-300 bg-slate-900 dark:bg-black/60 text-emerald-300 p-3 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-x-auto whitespace-pre-wrap">
                  {selectedEdge.matchedText}
                </pre>
              </div>
            )}

            {/* Nguyên văn SQL của file (parser hoặc LLM) */}
            {selectedEdge.sqlSnippet && (
              <div>
                <span className="text-[10px] font-mono font-bold text-slate-400 uppercase block mb-1">
                  Raw SQL
                </span>
                <pre className="text-[11px] font-mono text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-800/40 p-3 rounded-2xl border border-slate-100 dark:border-slate-800 overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap">
                  {selectedEdge.sqlSnippet}
                </pre>
              </div>
            )}

            {/* Column Mappings if any */}
            {selectedEdge.columnMappings && selectedEdge.columnMappings.length > 0 && (
              <div>
                <span className="text-[10px] font-mono font-bold text-slate-400 uppercase block mb-1">
                  Column Mappings
                </span>
                <div className="space-y-1">
                  {selectedEdge.columnMappings.map((m, i) => (
                    <div key={i} className="p-2 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-100 dark:border-slate-800 text-[11px] font-mono flex items-center justify-between">
                      <span className="text-slate-700 dark:text-slate-300">{m.sourceCol}</span>
                      <ArrowRight className="w-3 h-3 text-slate-400" />
                      <span className="text-indigo-600 dark:text-indigo-400 font-bold">{m.targetCol}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="pt-3 border-t border-slate-100 dark:border-slate-800 space-y-2">
            {selectedEdge.status === 'pending_hitl' && onAskCopilotAboutEdge && (
              <button
                onClick={handleAskCopilotAboutSelectedEdge}
                disabled={edgeReviewBusy}
                className="w-full py-2 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-950/40 dark:hover:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Hỏi Copilot giải thích trước khi duyệt</span>
              </button>
            )}
            {selectedEdge.status === 'pending_hitl' && canReview && onConfirmPendingEdge && onRejectPendingEdge && (
              <div className="flex gap-2">
                <button
                  onClick={handleRejectSelectedEdge}
                  disabled={edgeReviewBusy}
                  className="flex-1 py-2 bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/30 dark:hover:bg-rose-900/50 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800 rounded-xl text-xs font-mono font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
                >
                  <X className="w-3.5 h-3.5" />
                  <span>Từ chối</span>
                </button>
                <button
                  onClick={handleConfirmSelectedEdge}
                  disabled={edgeReviewBusy}
                  className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-mono font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>{edgeReviewBusy ? 'Đang xử lý…' : 'Duyệt cạnh này'}</span>
                </button>
              </div>
            )}
            <button
              onClick={() => setSelectedEdge(null)}
              className="w-full py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-xs font-mono font-semibold transition-colors cursor-pointer"
            >
              Close
            </button>
          </div>
        </aside>
      )}

      {isClearConfirmOpen && (
        <div className="fixed inset-0 z-[100] bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 max-w-md w-full rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl p-6 space-y-5 animate-fadeIn">
            {/* Header */}
            <div className="flex items-center gap-3 text-rose-600 dark:text-rose-400">
              <div className="p-2 rounded-xl bg-rose-50 dark:bg-rose-950/40">
                <AlertCircle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-mono text-base font-bold text-slate-900 dark:text-white">
                  Xác nhận xóa toàn bộ đồ thị
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Hành động này không thể hoàn tác
                </p>
              </div>
            </div>

            {/* Description */}
            <div className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed font-sans">
              Bạn có chắc chắn muốn xóa toàn bộ đồ thị lineage hiện tại? Toàn bộ các bảng, các cạnh lineage và các thay đổi đang chờ duyệt sẽ bị xóa sạch khỏi hệ thống.
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
              <button
                id="confirm-cancel-clear-btn"
                onClick={() => setIsClearConfirmOpen(false)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-xl text-xs font-semibold cursor-pointer transition-colors"
              >
                Hủy bỏ
              </button>
              <button
                id="confirm-clear-btn"
                onClick={() => {
                  setIsClearConfirmOpen(false);
                  onClearGraph?.();
                }}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-semibold cursor-pointer transition-colors"
              >
                Xác nhận xóa
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
