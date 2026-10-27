export type DataLayer = 'source' | 'staging' | 'intermediate' | 'marts' | 'unknown' | 'bi_dashboard' | 'feature_store' | 'reverse_etl';

export type ConfidenceTier = 'verified_parser' | 'high_llm' | 'low_llm_hitl';

export type AssetConnector = 'snowflake' | 'dbt' | 'postgres' | 'bigquery' | 'tableau' | 'powerbi' | 'databricks' | 'airflow' | 'kafka' | 's3';
export type CertificationStatus = 'VERIFIED' | 'DRAFT' | 'DEPRECATED' | 'UNDER_REVIEW';
export type AssetTier = 'Tier 1' | 'Tier 2' | 'Tier 3';

export interface ColumnDef {
  name: string;
  type: string;
  isPrimaryKey?: boolean;
  isForeignKey?: boolean;
  isNullable?: boolean;
  referencesTable?: string | null;
  /** 'declared' = từ DDL nguồn; 'propagated' = suy qua cạnh direct (tin cậy thấp hơn) */
  schemaOrigin?: 'declared' | 'propagated';
  description?: string;
  descriptionLabel?: string;
  sourceColumns?: { tableId: string; column: string }[];
  transformType?: 'DIRECT' | 'DERIVED' | 'AGGREGATION' | 'JOIN';
}

export interface LineageNodeData {
  id: string;
  name: string;
  schema: string;
  layer: DataLayer;
  type: 'table' | 'view' | 'materialized_view' | 'source_stream' | 'dashboard' | 'ml_feature';
  description: string;
  descriptionLabel?: string;
  descriptionSource?: string;
  descriptionIsStale?: boolean;
  columns: ColumnDef[];
  owner: string;
  tags: string[];
  rawSql?: string;
  compiledSql?: string;
  freshness?: string;
  rowCount?: number;
  qualityScore?: number;
  isDynamicSql?: boolean;
  hasJinja?: boolean;
  filePath?: string;
  connector?: AssetConnector;
  certification?: CertificationStatus;
  tier?: AssetTier;
  glossaryTerms?: string[];
  popularityScore?: number;
}

export interface LineageEdgeData {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  confidence: number; // 0.0 - 1.0
  inferredBy: 'sqlglot_parser' | 'gemini_llm' | 'gpt4o_mini' | 'human_verified';
  status: 'active' | 'pending_hitl' | 'rejected' | 'modified';
  reasoning?: string;
  /** Giải thích dài hơn `reasoning` — hiện khi user bấm "Chi tiết" ở drawer cạnh. */
  reasoningDetail?: string;
  /** [start_line, end_line] 1-indexed trong file nguồn (xấp xỉ, từ parser). */
  lineRange?: [number, number];
  /** Chỉ cạnh LLM: tín hiệu độ tin cậy phân loại (static/ref_source/branch/…). */
  resolutionMethod?: string;
  /** `output` = data lineage (mặc định); còn lại = control lineage
   * (cột chỉ ảnh hưởng HÀNG NÀO xuất hiện: filter/join_key/group_key/window_*). */
  dependencyKind?: 'output' | 'filter' | 'join_key' | 'group_key' | 'window_partition' | 'window_order';
  /** Cột nguồn của cạnh control lineage (dependencyKind !== 'output') — cạnh
   * control không có target_column nên không nằm trong columnMappings. */
  controlColumn?: string;
  sqlSnippet?: string;
  columnMappings?: { sourceCol: string; targetCol: string; transformType?: string }[];
  reviewedBy?: string;
  reviewedAt?: string;
  // Bằng chứng thật từ backend (LineageEvidence) — chỉ có ý nghĩa với cạnh
  // AI suy luận (gemini_llm), không phải mọi cạnh đều có đủ.
  filePath?: string;
  /** Đoạn SQL đúng nguyên văn LLM trích dẫn làm căn cứ suy luận. */
  matchedText?: string;
  /** true nếu matchedText thực sự tồn tại trong file gốc (backend đã verify),
   * false nếu không tìm thấy (nghi ngờ LLM bịa trích dẫn), null/undefined nếu
   * cạnh không có matchedText để verify. */
  citationVerified?: boolean | null;
  /** Vì sao parser fail, phải chuyển qua LLM fallback. */
  fallbackReason?: string;
}

export interface HITLQueueItem {
  id: string;
  edgeId: string;
  sourceTable: string;
  targetTable: string;
  sourceSchema: string;
  targetSchema: string;
  confidence: number;
  inferredBy: 'gemini_llm' | 'gpt4o_mini';
  reason: string;
  /** Giải thích dài hơn `reason`, hiện khi bấm "Chi tiết". */
  reasonDetail?: string;
  /** Chỉ cạnh LLM: static/ref_source/branch/dynamic/macro/speculative. */
  resolutionMethod?: string;
  sqlSnippet: string;
  filePath: string;
  suggestedColumnMappings: { sourceCol: string; targetCol: string }[];
  status: 'pending' | 'confirmed' | 'rejected' | 'edited';
  timestamp: string;
  detectedIssue: 'dynamic_sql' | 'jinja_macro' | 'string_concatenation' | 'ambiguous_alias';
}

export interface ImpactAnalysisResult {
  targetNodeId: string;
  targetNodeName: string;
  operation: 'drop_table' | 'modify_schema' | 'drop_column' | 'rename_column' | 'rename_table' | 'change_logic' | 'add_column' | 'change_constraint';
  impactedColumn?: string;
  upstreamNodes: {
    node: LineageNodeData;
    depth: number;
    path: string[];
  }[];
  downstreamNodes: {
    node: LineageNodeData;
    depth: number;
    path: string[];
    riskLevel: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
    impactReason: string;
    affectedColumns?: string[];
  }[];
  totalImpactedCount: number;
  criticalDashboards: string[];
  mlFeaturesAffected: string[];
  riskScore: number; // 0 to 100
  mitigationAdvice: string[];
}

export interface CopilotMessage {
  id: string;
  sender: 'user' | 'agent' | 'system';
  content: string;
  timestamp: string;
  thoughtProcess?: {
    step: string;
    action: string;
    observation: string;
  }[];
  relatedNodes?: string[];
  impactData?: Partial<ImpactAnalysisResult>;
  suggestedQueries?: string[];
}

export interface IngestJob {
  id: string;
  fileName: string;
  totalModels: number;
  parsedBySqlglot: number;
  routedToLLM: number;
  routedToHITL: number;
  status: 'scanning' | 'parsing_sqlglot' | 'llm_fallback' | 'hitl_queued' | 'completed' | 'failed';
  log: string[];
  startTime: string;
}
