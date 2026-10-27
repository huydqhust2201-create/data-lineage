import React, { useMemo } from 'react';
import { ReactFlow, Background, BackgroundVariant, Handle, Position, MarkerType, type Node, type Edge } from '@xyflow/react';
import { GitBranch } from 'lucide-react';
import type { ImpactEdgeView } from '../types/backend';

interface ImpactBlastRadiusGraphProps {
  rootTable: string;
  rootColumn?: string;
  downstreamEdges: ImpactEdgeView[];
  upstreamEdges: ImpactEdgeView[];
}

interface BlastNodeData {
  label: string;
  column?: string | null;
  isRoot: boolean;
  pending: boolean;
  hasRisk: boolean;
  [key: string]: unknown;
}

// Node compact riêng cho blast-radius graph — không tái dùng CustomTableNode
// (nặng, có expand/collapse cột, phù hợp cho đồ thị chính) vì ở đây chỉ cần
// 1 khung nhỏ đủ đọc tên bảng + trạng thái, đặt vừa trong panel bên cạnh
// danh sách text chi tiết.
function BlastNode({ data }: { data: BlastNodeData }) {
  const borderColor = data.isRoot
    ? 'border-indigo-500 dark:border-indigo-400'
    : data.pending
      ? 'border-amber-400 dark:border-amber-600'
      : data.hasRisk
        ? 'border-rose-300 dark:border-rose-700'
        : 'border-slate-200 dark:border-slate-700';
  const bg = data.isRoot
    ? 'bg-indigo-600 text-white'
    : 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white';

  return (
    <div className={`px-3 py-2 rounded-xl border-2 shadow-sm ${borderColor} ${bg} min-w-[140px] max-w-[200px]`}>
      <Handle type="target" position={Position.Left} className="!bg-slate-400 !w-1.5 !h-1.5" />
      <Handle type="source" position={Position.Right} className="!bg-slate-400 !w-1.5 !h-1.5" />
      <div className="text-[11px] font-mono font-bold truncate">{data.label}</div>
      {data.column && <div className="text-[9px] font-mono opacity-70 truncate">.{data.column}</div>}
      {data.pending && !data.isRoot && (
        <span className="mt-1 inline-block text-[8px] font-bold px-1 py-0.5 rounded bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300">
          CHỜ DUYỆT
        </span>
      )}
    </div>
  );
}

const nodeTypes = { blast: BlastNode };

const TIER_SPACING = 220;
const ROW_SPACING = 70;

// Xếp node theo tầng hop, gốc (root) ở giữa — downstream lệch phải theo hop
// tăng dần, upstream lệch trái — đúng ý tưởng "1 bảng làm trung tâm, 1 hop 1
// hàng/cột, 2 hop 1 hàng/cột kế bên" thay vì liệt kê phẳng bằng text.
function layoutByHop(
  edges: ImpactEdgeView[],
  direction: 'down' | 'up',
  endpointKey: 'target' | 'source',
): { nodes: Node<BlastNodeData>[]; edges: Edge[] } {
  const byHop = new Map<number, Map<string, ImpactEdgeView>>();
  for (const edge of edges) {
    const hop = edge.hops ?? 1;
    const endpoint = edge[endpointKey];
    if (!byHop.has(hop)) byHop.set(hop, new Map());
    const bucket = byHop.get(hop)!;
    const existing = bucket.get(endpoint.table);
    // Giữ bản có risk hoặc pending để badge/màu không bị mất khi 1 bảng xuất
    // hiện qua nhiều cạnh ở cùng 1 tầng.
    if (!existing || edge.risk || edge.hitl_status === 'pending') bucket.set(endpoint.table, edge);
  }

  const nodes: Node<BlastNodeData>[] = [];
  const sign = direction === 'down' ? 1 : -1;
  for (const [hop, bucket] of Array.from(byHop.entries()).sort((a, b) => a[0] - b[0])) {
    const items = Array.from(bucket.entries());
    const startY = -((items.length - 1) * ROW_SPACING) / 2;
    items.forEach(([table, edge], index) => {
      nodes.push({
        id: table,
        type: 'blast',
        position: { x: sign * hop * TIER_SPACING, y: startY + index * ROW_SPACING },
        data: {
          label: table,
          column: edge[endpointKey].column,
          isRoot: false,
          pending: edge.hitl_status === 'pending',
          hasRisk: Boolean(edge.risk),
        },
      });
    });
  }

  const flowEdges: Edge[] = edges.map((edge, idx) => {
    const pending = edge.hitl_status === 'pending';
    return {
      id: `blast-${direction}-${idx}-${edge.source.table}-${edge.target.table}`,
      source: edge.source.table,
      target: edge.target.table,
      animated: pending,
      style: {
        stroke: pending ? '#f59e0b' : edge.risk ? '#f43f5e' : '#10b981',
        strokeDasharray: pending ? '5,5' : undefined,
        strokeWidth: 1.5,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: pending ? '#f59e0b' : edge.risk ? '#f43f5e' : '#10b981' },
    };
  });

  return { nodes, edges: flowEdges };
}

export const ImpactBlastRadiusGraph: React.FC<ImpactBlastRadiusGraphProps> = ({
  rootTable,
  rootColumn,
  downstreamEdges,
  upstreamEdges,
}) => {
  const { nodes, edges } = useMemo(() => {
    const down = layoutByHop(downstreamEdges, 'down', 'target');
    const up = layoutByHop(upstreamEdges, 'up', 'source');
    const rootNode: Node<BlastNodeData> = {
      id: rootTable,
      type: 'blast',
      position: { x: 0, y: 0 },
      data: { label: rootTable, column: rootColumn, isRoot: true, pending: false, hasRisk: false },
    };
    // Node downstream/upstream có thể trùng id với root nếu backend trả về
    // cạnh tự tham chiếu — bỏ trùng, ưu tiên giữ root.
    const seen = new Set([rootTable]);
    const mergedNodes = [rootNode];
    for (const node of [...down.nodes, ...up.nodes]) {
      if (seen.has(node.id)) continue;
      seen.add(node.id);
      mergedNodes.push(node);
    }
    return { nodes: mergedNodes, edges: [...down.edges, ...up.edges] };
  }, [rootTable, rootColumn, downstreamEdges, upstreamEdges]);

  if (nodes.length <= 1) {
    return (
      <div className="h-40 flex flex-col items-center justify-center text-slate-400 dark:text-slate-500 text-xs font-mono gap-2">
        <GitBranch className="w-6 h-6" />
        <span>Không có bảng liên quan nào để vẽ đồ thị.</span>
      </div>
    );
  }

  return (
    <div className="h-[420px] rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden bg-slate-50 dark:bg-slate-950/60">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
      </ReactFlow>
    </div>
  );
};
