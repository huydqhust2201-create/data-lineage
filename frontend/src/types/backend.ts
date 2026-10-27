// Mirror 1:1 của src/models/schemas.py — không tự thêm field ngoài những gì
// backend thật sự trả về. Sửa backend trước, sửa file này theo sau.

export type SourceType = "parser" | "llm";
export type TransformType = "direct" | "conditional" | "aggregation" | "join" | "unknown";
export type DependencyKind =
  | "output"
  | "filter"
  | "join_key"
  | "group_key"
  | "window_partition"
  | "window_order";
export type Direction = "downstream" | "upstream";
export type HitlStatus = "confirmed" | "pending";

export interface LineageEvidence {
  file_path: string | null;
  line_range: [number, number] | null;
  raw_sql: string | null;
  reasoning: string | null;
  /** Giải thích dài hơn `reasoning`, hiện khi user bấm "Chi tiết". */
  reasoning_detail: string | null;
  fallback_reason: string | null;
  /** Chỉ cạnh LLM: static/ref_source/branch/dynamic/macro/speculative. */
  resolution_method: string | null;
  matched_text: string | null;
  citation_verified: boolean | null;
  confirmed_at: string | null;
}

export interface LineageEdge {
  edge_id: string;
  source_table: string;
  source_column: string | null;
  target_table: string;
  target_column: string | null;
  /** `output` = data lineage; còn lại = control lineage (target_column null). */
  dependency_kind: DependencyKind;
  transform_type: TransformType;
  confidence: number;
  source_type: SourceType;
  evidence: LineageEvidence | null;
}

export interface ImpactEndpoint {
  table: string;
  column: string | null;
}

export type ChangeKind =
  | "type"
  | "value"
  | "drop"
  | "rename"
  | "drop_table"
  | "rename_table"
  | "add_column"
  | "constraint";

export interface ImpactEdgeView {
  source: ImpactEndpoint;
  target: ImpactEndpoint;
  source_type: SourceType;
  transform_type: TransformType;
  dependency_kind: DependencyKind;
  confidence: number;
  hitl_status: HitlStatus | null;
  evidence: LineageEvidence | null;
  // Chỉ có giá trị thật (dùng được cho POST /pending-review/{id}) khi
  // hitl_status === "pending" — cạnh confirmed luôn null (BE cũng không gắn).
  edge_id: string | null;
  // Chỉ có khi request kèm change_kind — rủi ro cụ thể của CẠNH NÀY khi đổi
  // kiểu/giá trị cột, tính theo transform_type (join/aggregation/direct).
  risk: string | null;
  // Câu dẫn về kiểu/constraint hiện tại của cột đang đổi — GIỐNG NHAU cho mọi
  // cạnh (cùng 1 cột nguồn). Đã nằm sẵn ở đầu `risk`; tách ra để hiển thị 1 lần.
  schema_note?: string | null;
  // Số bước từ bảng gốc được truy vấn tới cạnh này (hop 1 = xuất phát trực
  // tiếp từ bảng gốc) — dùng để nhóm sub-graph impact theo từng tầng.
  hops: number | null;
}

export interface ImpactQueryResult {
  table: string;
  column: string | null;
  direction: Direction;
  confirmed: ImpactEdgeView[];
  inferred_pending: ImpactEdgeView[];
}

export interface IngestRequest {
  input_path: string;
  dialect?: string | null;
}

export interface GraphNode {
  id: string;
  label: string;
  description: string | null;
  description_label: string | null;
  description_source: string | null;
  description_is_stale: boolean;
  columns: ColumnDescriptionView[];
  column_schemas?: ColumnSchemaView[];
}

export interface ColumnDescriptionView {
  column: string;
  description: string;
  label: string | null;
  source: string;
  is_stale: boolean;
}

export interface ColumnSchemaView {
  name: string;
  data_type: string | null;
  is_nullable: boolean;
  is_primary_key: boolean;
  is_foreign_key: boolean;
  references_table: string | null;
  references_column: string | null;
  origin: "declared" | "propagated";
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: LineageEdge[];
}

export interface OverviewGraph {
  nodes: GraphNode[];
  confirmed_edges: LineageEdge[];
  pending_edges: LineageEdge[];
}

export interface IngestRun {
  id: number;
  input_path: string;
  sql_files_found: number;
  parsed_count: number;
  unparsed_count: number;
  pending_review_count: number;
  triggered_by_user_id: number | null;
  started_at: string;
}

export interface IngestResponse {
  sql_files_found: number;
  parsed_count: number;
  unparsed_count: number;
  pending_review_count: number;
  overview_graph: OverviewGraph;
  description_pending_count: number;
}

export interface ChatRequest {
  question: string;
  session_id: string | null;
}

export interface ChatStepResolved {
  table: string | null;
  column: string | null;
  direction: Direction | null;
}

export interface ChatStep {
  tool: string;
  args: Record<string, unknown>;
  resolved: ChatStepResolved | null;
  error: string | null;
  summary: string;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  confirmed: ImpactEdgeView[];
  inferred_pending: ImpactEdgeView[];
  clarification_options: string[];
  suggestions: string[];
  warnings: string[];
  steps: ChatStep[];
}

export interface StatusResponse {
  status: string;
  agent: string;
}
