// Chuyển GraphResponse thật (GET /api/v1/graph) sang LineageNodeData/LineageEdgeData
// mà UI mới (PR #60) đang dùng. UI mới có nhiều trường "enterprise" (owner,
// tags, quality score, certification, connector Snowflake/BigQuery...) mà
// backend thật không hề có — theo quyết định của team, các trường đó được
// gán 1 giá trị placeholder CỐ ĐỊNH, không bịa số liệu trông như thật (không
// random, không tính toán giả — luôn cùng 1 giá trị cho mọi node/edge) để
// không đánh lừa người xem UI. schema/layer suy ra từ quy ước đặt tên bảng
// dbt thật (vd "stg_orders" -> layer "staging") — đây là suy luận từ dữ liệu
// thật, không phải bịa.
import type { GraphNode, GraphResponse, LineageEdge as BackendEdge } from "../types/backend";
import type { ColumnDef, DataLayer, LineageEdgeData, LineageNodeData } from "../types/lineage";

const PLACEHOLDER = {
  owner: "—",
  connector: "postgres" as const,
  certification: "DRAFT" as const,
  tier: "Tier 2" as const,
};

type LayerInput = { nodeId: string; upstream: Set<string>; downstream: Set<string> };

function inferLayer(
  { nodeId, upstream, downstream }: LayerInput,
  sourceTables: ReadonlySet<string>,
): DataLayer {
  if (upstream.size === 0 && downstream.size === 0) return "unknown";
  if (upstream.size === 0) return "source";
  const allUpstreamAreSources = Array.from(upstream).every((table) => sourceTables.has(table));
  if (downstream.size === 0) {
    return allUpstreamAreSources && /(^|\.)stg[_.]/.test(nodeId.toLowerCase()) ? "staging" : "marts";
  }
  return allUpstreamAreSources ? "staging" : "intermediate";
}

function splitSchemaAndName(nodeId: string): { schema: string; name: string } {
  const dot = nodeId.indexOf(".");
  if (dot === -1) return { schema: "public", name: nodeId };
  return { schema: nodeId.slice(0, dot), name: nodeId.slice(dot + 1) };
}

function columnsForNode(node: GraphNode, edges: BackendEdge[]): ColumnDef[] {
  const nodeId = node.id;
  const seen = new Map<string, ColumnDef>();
  for (const edge of edges) {
    if (edge.source_table === nodeId && edge.source_column) {
      seen.set(edge.source_column, { name: edge.source_column, type: "unknown" });
    }
    if (edge.target_table === nodeId && edge.target_column) {
      seen.set(edge.target_column, {
        name: edge.target_column,
        type: "unknown",
        transformType:
          edge.transform_type === "direct"
            ? "DIRECT"
            : edge.transform_type === "aggregation"
              ? "AGGREGATION"
              : edge.transform_type === "join"
                ? "JOIN"
                : "DERIVED", // conditional / union / unknown → DERIVED
        sourceColumns: edge.source_column ? [{ tableId: edge.source_table, column: edge.source_column }] : undefined,
      });
    }
  }
  for (const column of node.columns) {
    const existing = seen.get(column.column);
    seen.set(column.column, { ...existing, name: column.column, type: existing?.type ?? "unknown", description: column.description, descriptionLabel: column.label ?? undefined });
  }
  // Kiểu + constraint từ DDL nguồn (declared) hoặc suy qua cạnh direct (propagated).
  // Chỉ tồn tại cho bảng raw + model nhận được qua propagation — phần còn lại giữ "unknown".
  for (const cs of node.column_schemas ?? []) {
    const existing = seen.get(cs.name);
    seen.set(cs.name, {
      ...existing,
      name: cs.name,
      type: cs.data_type ?? existing?.type ?? "unknown",
      isPrimaryKey: cs.is_primary_key || existing?.isPrimaryKey,
      isForeignKey: cs.is_foreign_key || existing?.isForeignKey,
      isNullable: cs.is_nullable,
      referencesTable: cs.references_table,
      schemaOrigin: cs.origin,
    });
  }
  return Array.from(seen.values());
}

function toLineageNode(node: GraphNode, edges: BackendEdge[], layer: DataLayer): LineageNodeData {
  const { schema, name } = splitSchemaAndName(node.id);
  return {
    id: node.id,
    name,
    schema,
    layer,
    type: "table",
    description: node.description ?? "",
    descriptionLabel: node.description_label ?? undefined,
    descriptionSource: node.description_source ?? undefined,
    descriptionIsStale: node.description_is_stale,
    columns: columnsForNode(node, edges),
    owner: PLACEHOLDER.owner,
    tags: [],
    connector: PLACEHOLDER.connector,
    certification: PLACEHOLDER.certification,
    tier: PLACEHOLDER.tier,
    glossaryTerms: [],
  };
}

function toLineageEdge(edge: BackendEdge, status: LineageEdgeData["status"] = "active"): LineageEdgeData {
  return {
    id: edge.edge_id,
    source: edge.source_table,
    target: edge.target_table,
    confidence: edge.confidence,
    inferredBy: edge.source_type === "parser" ? "sqlglot_parser" : "gemini_llm",
    status,
    reasoning: edge.evidence?.reasoning ?? undefined,
    reasoningDetail: edge.evidence?.reasoning_detail ?? undefined,
    lineRange: edge.evidence?.line_range ?? undefined,
    resolutionMethod: edge.evidence?.resolution_method ?? undefined,
    dependencyKind: edge.dependency_kind ?? "output",
    controlColumn:
      edge.dependency_kind && edge.dependency_kind !== "output" ? edge.source_column ?? undefined : undefined,
    sqlSnippet: edge.evidence?.raw_sql ?? undefined,
    columnMappings:
      edge.source_column && edge.target_column
        ? [{ sourceCol: edge.source_column, targetCol: edge.target_column, transformType: edge.transform_type }]
        : undefined,
    filePath: edge.evidence?.file_path ?? undefined,
    matchedText: edge.evidence?.matched_text ?? undefined,
    citationVerified: edge.evidence?.citation_verified ?? undefined,
    fallbackReason: edge.evidence?.fallback_reason ?? undefined,
  };
}

export function graphResponseToLineageData(graph: GraphResponse | null): {
  nodes: LineageNodeData[];
  edges: LineageEdgeData[];
} {
  if (!graph) return { nodes: [], edges: [] };
  const upstream = new Map<string, Set<string>>();
  const downstream = new Map<string, Set<string>>();
  for (const node of graph.nodes) {
    upstream.set(node.id, new Set());
    downstream.set(node.id, new Set());
  }
  const addRelationship = (relationships: Map<string, Set<string>>, table: string, relatedTable: string) => {
    const related = relationships.get(table) ?? new Set<string>();
    related.add(relatedTable);
    relationships.set(table, related);
  };
  for (const edge of graph.edges) {
    addRelationship(upstream, edge.target_table, edge.source_table);
    addRelationship(downstream, edge.source_table, edge.target_table);
  }
  const sourceTables = new Set(
    graph.nodes
      .filter((node) => (upstream.get(node.id)?.size ?? 0) === 0 && (downstream.get(node.id)?.size ?? 0) > 0)
      .map((node) => node.id),
  );
  return {
    nodes: graph.nodes.map((node) => toLineageNode(
      node,
      graph.edges,
      inferLayer({ nodeId: node.id, upstream: upstream.get(node.id) ?? new Set(), downstream: downstream.get(node.id) ?? new Set() }, sourceTables),
    )),
    edges: graph.edges.map((edge) => toLineageEdge(edge)),
  };
}

// GET /graph (graph_service.get_all_edges) chỉ trả cạnh đã CONFIRMED — cạnh
// đang chờ duyệt (HITL queue, do LLM suy luận với confidence thấp) sống
// riêng ở GET /pending-review và không có mặt trong graphResponseToLineageData.
// Vì Lineage DAG chỉ render những gì có trong nodes/edges của App.tsx, cạnh
// pending phải được chuyển đổi riêng (status "pending_hitl") rồi gộp thêm
// vào, kèm placeholder node cho bảng nào chỉ xuất hiện qua cạnh pending đó
// (chưa có trong đồ thị confirmed) — nếu không đồ thị sẽ thiếu 1 đầu cạnh
// và React Flow sẽ không vẽ được cạnh.
export function pendingEdgesToLineageData(
  pending: BackendEdge[],
  existingNodeIds: Iterable<string>,
): { nodes: LineageNodeData[]; edges: LineageEdgeData[] } {
  const known = new Set(existingNodeIds);
  const extraIds = new Set<string>();
  for (const edge of pending) {
    if (!known.has(edge.source_table)) extraIds.add(edge.source_table);
    if (!known.has(edge.target_table)) extraIds.add(edge.target_table);
  }
  return {
    nodes: Array.from(extraIds).map((id) => toLineageNode({
      id, label: id, description: null, description_label: null, description_source: null,
      description_is_stale: false, columns: [],
    }, pending, "unknown")),
    edges: pending.map((edge) => toLineageEdge(edge, "pending_hitl")),
  };
}
