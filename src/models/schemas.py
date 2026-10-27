from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class LineageEvidence(BaseModel):
    """Bằng chứng cụ thể cho 1 cạnh — để user tự thẩm định thay vì tin mù vào
    con số confidence. Cạnh parser và cạnh LLM đều có reasoning (parser: câu
    template từ transform_type + line_range; LLM: giải thích tự do bắt buộc
    từ model). fallback_reason/matched_text/citation_verified chỉ có ý nghĩa
    ở cạnh LLM.
    """

    file_path: str | None = None
    line_range: list[int] | None = Field(default=None, description="[start_line, end_line], 1-indexed")
    raw_sql: str | None = Field(default=None, description="Nguyên văn nội dung file nguồn, không rút gọn")
    reasoning: str | None = Field(
        default=None, description="Vì sao cạnh này tồn tại — có ở cả cạnh parser (template) và cạnh LLM (tự do)"
    )
    reasoning_detail: str | None = Field(
        default=None,
        description=(
            "Giải thích DÀI hơn `reasoning`, hiển thị khi user bấm 'Chi tiết' — parser: diễn giải cơ chế "
            "biến đổi + vì sao chắc chắn 100%; LLM: căn cứ trong SQL + vì sao mức tin cậy đó + phần chưa chắc. "
            "Có ở cả cạnh parser (template) và cạnh LLM (tự do)."
        ),
    )
    fallback_reason: str | None = Field(default=None, description="Chỉ có ở cạnh LLM: lý do parser fail ban đầu")
    resolution_method: str | None = Field(
        default=None,
        description=(
            "Chỉ có ở cạnh LLM: tín hiệu độ tin cậy dạng phân loại LLM trả về "
            "(static/ref_source/branch/dynamic/macro/speculative) — code map sang confidence số."
        ),
    )
    matched_text: str | None = Field(
        default=None,
        description="Chỉ có ở cạnh LLM: đoạn SQL trích dẫn nguyên văn LLM dùng làm căn cứ suy luận",
    )
    citation_verified: bool | None = Field(
        default=None,
        description=(
            "Chỉ có ở cạnh LLM có matched_text: True nếu đoạn trích thực sự tồn tại trong file gốc, "
            "False nếu không tìm thấy (nghi ngờ LLM bịa trích dẫn)"
        ),
    )
    transform_expression: str | None = Field(
        default=None,
        description=(
            "Biểu thức SQL tạo ra target_column. Parser lưu biểu diễn chuẩn hoá do SQLGlot serialise; "
            "LLM lưu đoạn nguyên văn đã trích từ nguồn và kiểm qua citation_verified."
        ),
    )
    confirmed_at: datetime | None = Field(
        default=None, description="Thời điểm cạnh LLM được duyệt qua HITL; None nếu chưa duyệt hoặc là cạnh parser"
    )


class LineageEdge(BaseModel):
    """1 quan hệ phụ thuộc giữa 2 bảng/cột. Contract dùng chung giữa parser,
    LLM extraction, graph storage và API — mọi module đọc/ghi qua schema này.
    """

    edge_id: str = Field(
        default_factory=lambda: str(uuid4()), description="ID ổn định để HITL confirm/reject 1 cạnh cụ thể"
    )
    source_table: str = Field(..., description="Bảng nguồn, vd 'raw.orders'")
    source_column: str | None = Field(default=None, description="Cột nguồn; None nếu chỉ table-level")
    target_table: str = Field(..., description="Bảng đích")
    target_column: str | None = Field(default=None, description="Cột đích; None nếu chỉ table-level")
    dependency_kind: Literal[
        "output", "filter", "join_key", "group_key", "window_partition", "window_order"
    ] = Field(
        default="output",
        description=(
            "Vai trò của cột nguồn với bảng đích. `output` = data lineage: cột nguồn chảy vào GIÁ TRỊ "
            "của 1 cột output (target_column có giá trị). Còn lại là control lineage: cột nguồn KHÔNG "
            "vào output nào nhưng quyết định HÀNG NÀO xuất hiện — `filter` (WHERE/HAVING/QUALIFY), "
            "`join_key` (ON/USING), `group_key` (GROUP BY), `window_partition`/`window_order` (OVER). "
            "Cạnh control luôn có target_column=None."
        ),
    )
    transform_type: Literal["direct", "conditional", "aggregation", "join", "unknown"] = "unknown"
    confidence: float = Field(..., ge=0.0, le=1.0, description="1.0 nếu từ parser; <1.0 nếu LLM suy luận")
    source_type: Literal["parser", "llm"] = Field(..., description="Cạnh này đến từ sqlglot/sqllineage hay LLM")
    evidence: LineageEvidence | None = Field(
        default=None, description="Bằng chứng cụ thể — None chỉ khi chưa gắn (test nội bộ)"
    )


class GraphEvent(BaseModel):
    """One ordered SQL statement reduced to its graph effect."""

    file_path: str
    order: int = Field(ge=0)
    kind: Literal["edges", "rename", "drop", "declare"]
    edges: list[LineageEdge] = Field(default_factory=list)
    table: str | None = None
    new_name: str | None = None
    columns: list["ColumnSchema"] = Field(
        default_factory=list,
        description="Chỉ có ở event `declare` từ CREATE TABLE có danh sách cột tường minh (DDL bảng nguồn) — kiểu + constraint mỗi cột.",
    )

    @model_validator(mode="after")
    def validate_payload(self) -> "GraphEvent":
        if self.kind == "edges" and not self.edges:
            raise ValueError("edges event requires at least one lineage edge")
        if self.kind == "rename" and (not self.table or not self.new_name):
            raise ValueError("rename event requires table and new_name")
        if self.kind == "drop" and not self.table:
            raise ValueError("drop event requires table")
        if self.kind == "declare" and (not self.table or self.edges):
            raise ValueError("declare event requires table and no edges")
        return self


class StatementPreview(BaseModel):
    """One DDL statement and its simulated outcome."""

    order: int = Field(ge=0)
    sql: str
    kind: Literal["drop", "rename", "unsupported"]
    table: str | None = None
    new_name: str | None = None
    status: Literal["applied", "unknown_table", "unsupported", "rename_conflict"]


class DdlPreviewResult(BaseModel):
    """The dry-run lineage impact of an ordered DDL script."""

    statements: list[StatementPreview]
    removed_edges: list[LineageEdge]
    orphaned_tables: list[str]
    unknown_tables: list[str]
    rename_conflicts: list[dict[str, str]]
    unsupported_statements: list[str]
    risk_by_statement: list["StatementRiskGroup"] = Field(default_factory=list)
    parse_error: str | None = None
    edges_before: int
    edges_after: int
    tables_before: int
    tables_after: int


class ImpactEndpoint(BaseModel):
    """1 đầu (nguồn hoặc đích) của cạnh trong response impact — dạng lồng nhau
    thay vì phẳng (source_table/source_column) để đọc rõ hơn ở API layer."""

    table: str
    column: str | None = None


class ImpactEdgeView(BaseModel):
    """1 cạnh trong response impact query. `hitl_status` chỉ có ý nghĩa với
    cạnh trong inferred_pending — cạnh confirmed luôn coi như đã duyệt.

    `edge_id`: chỉ ổn định/dùng được cho POST /pending-review/{id}/confirm|
    reject với cạnh pending (lấy thẳng từ review_service, cùng 1 object với
    hàng đợi HITL). Với cạnh confirmed, edge_id là uuid4 sinh mới mỗi lần
    truy vấn (graph_service không persist edge_id) — không dùng để gọi API,
    chỉ có mặt cho đồng nhất field.
    """
    source: ImpactEndpoint
    target: ImpactEndpoint
    source_type: Literal["parser", "llm"]
    transform_type: Literal["direct", "conditional", "aggregation", "join", "unknown"]
    dependency_kind: Literal[
        "output", "filter", "join_key", "group_key", "window_partition", "window_order"
    ] = Field(
        default="output",
        description="Vai trò của cột nguồn: `output` = chảy vào giá trị cột đích; còn lại = control "
        "lineage (chỉ ảnh hưởng HÀNG NÀO xuất hiện, không có cột đích). Xem LineageEdge.dependency_kind.",
    )
    confidence: float
    hitl_status: Literal["confirmed", "pending"] | None = None
    evidence: LineageEvidence | None = None
    edge_id: str | None = None
    risk: str | None = Field(
        default=None,
        description="Chỉ có khi request kèm change_kind — rủi ro cụ thể của CẠNH NÀY khi đổi kiểu/giá trị cột, tính theo transform_type",
    )
    schema_note: str | None = Field(
        default=None,
        description=(
            "Câu dẫn về kiểu/constraint HIỆN TẠI của cột đang đổi — GIỐNG NHAU cho mọi cạnh trong 1 "
            "lượt query (cùng 1 cột nguồn). Đã có sẵn ở đầu `risk`; tách ra để FE hiển thị 1 lần cho "
            "cả nhóm thay vì lặp mỗi dòng. None khi không có schema hoặc change_kind không liên quan."
        ),
    )
    hops: int | None = Field(
        default=None,
        description="Số bước từ bảng gốc được truy vấn tới cạnh này (hop 1 = xuất phát trực tiếp từ bảng gốc). "
        "Chỉ có khi request là REST /impact — dùng để FE nhóm kết quả theo tầng.",
    )

    @classmethod
    def from_edge(
        cls,
        edge: LineageEdge,
        *,
        hitl_status: str | None,
        risk: str | None = None,
        hops: int | None = None,
        schema_note: str | None = None,
    ) -> "ImpactEdgeView":
        return cls(
            source=ImpactEndpoint(table=edge.source_table, column=edge.source_column),
            target=ImpactEndpoint(table=edge.target_table, column=edge.target_column),
            source_type=edge.source_type,
            transform_type=edge.transform_type,
            dependency_kind=edge.dependency_kind,
            confidence=edge.confidence,
            hitl_status=hitl_status,
            evidence=edge.evidence,
            edge_id=edge.edge_id if hitl_status == "pending" else None,
            risk=risk,
            schema_note=schema_note,
            hops=hops,
        )


class StatementRisk(BaseModel):
    """Risk of one direct outgoing edge before a simulated DDL statement."""

    source_table: str
    source_column: str | None = None
    target_table: str
    target_column: str | None = None
    risk: str


class StatementRiskGroup(BaseModel):
    """Direct downstream risks associated with one applied DDL statement."""

    order: int = Field(ge=0)
    table: str
    change_kind: Literal["drop_table", "rename_table"]
    risks: list[StatementRisk] = Field(default_factory=list)


DdlPreviewResult.model_rebuild()


class ImpactQueryResult(BaseModel):
    """Kết quả truy vấn impact analysis (US-5, US-6, US-3, US-4).

    Tách rõ 2 khối theo yêu cầu: `confirmed` (parser hoặc LLM đã qua HITL —
    agent "khẳng định chắc chắn") vs `inferred_pending` (LLM confidence thấp,
    CHƯA qua HITL — "nghi ngờ, cần xác nhận thêm"). Không bao giờ gộp chung.
    """

    table: str
    column: str | None = None
    direction: Literal["downstream", "upstream"]
    confirmed: list[ImpactEdgeView] = Field(default_factory=list)
    inferred_pending: list[ImpactEdgeView] = Field(default_factory=list)


class IngestRequest(BaseModel):
    """Input cho FR-1: luôn là 1 path tường minh, không tự dò tìm."""

    input_path: str = Field(..., min_length=1, description="Folder local hoặc repo Git đã clone")
    dialect: str | None = Field(default=None, description="Override sql_dialect trong config nếu cần")
    database_id: int


class GraphNode(BaseModel):
    """1 node trong đồ thị lineage — dùng cho react-flow (FR-7)."""

    id: str = Field(..., description="table hoặc table.column")
    label: str
    description: str | None = None
    description_label: str | None = None
    description_source: str | None = None
    description_is_stale: bool = False
    columns: list["ColumnDescriptionView"] = Field(default_factory=list)
    column_schemas: list["ColumnSchema"] = Field(
        default_factory=list,
        description=(
            "Kiểu dữ liệu + constraint của cột, trích từ DDL bảng nguồn (CREATE TABLE tường minh) "
            "hoặc propagate qua cạnh `direct`. Rỗng khi bảng không có DDL khai báo và không nhận "
            "được gì qua propagation. Tách riêng khỏi `columns` (mô tả) — một cột có thể có cái này, "
            "cái kia, hoặc cả hai."
        ),
    )


class ColumnDescriptionView(BaseModel):
    column: str
    description: str
    label: str | None = None
    source: str
    is_stale: bool = False


class ColumnSchema(BaseModel):
    """Kiểu dữ liệu + ràng buộc của 1 cột.

    `origin="declared"`: trích thẳng từ `CREATE TABLE x (col TYPE constraint...)` trong
    file ingest — chỉ tồn tại cho bảng raw/source (model dbt là SELECT nên không mang
    kiểu). `origin="propagated"`: suy ra qua cạnh parser `transform_type="direct"`
    (truyền cột nguyên trạng) — chỉ mang `data_type`/`is_nullable`, KHÔNG mang khoá
    (PK/UNIQUE không "chảy" qua SELECT); UI/impact hạ mức tin cậy so với `declared`.
    """

    name: str
    data_type: str | None = None
    is_nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references_table: str | None = None
    references_column: str | None = None
    origin: Literal["declared", "propagated"] = "declared"


# ColumnSchema được tham chiếu tiến (forward ref) trong GraphEvent và GraphNode —
# rebuild tường minh để pydantic phân giải ngay lúc import, không phụ thuộc thứ tự.
GraphEvent.model_rebuild()
GraphNode.model_rebuild()


class GraphResponse(BaseModel):
    """Toàn bộ đồ thị đã xác nhận, để frontend vẽ (FR-7)."""

    nodes: list[GraphNode]
    edges: list[LineageEdge]


class OverviewGraph(BaseModel):
    """Đồ thị table-level của các bảng/model VỪA phát hiện trong 1 lượt ingest
    (không phải toàn bộ đồ thị tích luỹ trong Postgres — xem GET /graph cho cái đó).

    Tách `confirmed_edges`/`pending_edges` riêng, CÙNG nguyên tắc với
    ImpactQueryResult — gộp chung từng gây nhầm lẫn thật: user lấy nhầm
    edge_id của 1 cạnh đã confirmed để gọi /pending-review/{id}/confirm,
    nhận 404 vì cạnh đó chưa từng vào hàng đợi pending.
    """

    nodes: list[GraphNode]
    confirmed_edges: list[LineageEdge]
    pending_edges: list[LineageEdge] = Field(..., description="edge_id trong đây mới gọi được /confirm|reject")


class IngestResponse(BaseModel):
    """Kết quả sau khi ingest xong 1 lượt (FR-2..FR-4)."""

    sql_files_found: int
    parsed_count: int = Field(..., description="Số cạnh parser đọc được thẳng (confidence=1.0)")
    unparsed_count: int = Field(..., description="Số file phải chuyển qua LLM fallback")
    pending_review_count: int = Field(..., description="Số cạnh confidence < threshold, chờ HITL")
    overview_graph: OverviewGraph = Field(
        ..., description="Bức tranh table-level lượt ingest này, confirmed/pending tách riêng"
    )
    description_pending_count: int = 0


class IngestRun(BaseModel):
    """1 dòng lịch sử ingest — chỉ để xem lại (audit), không ảnh hưởng cách
    dữ liệu gộp vào graph (vẫn cộng dồn theo database_id như trước)."""

    id: int
    input_path: str
    sql_files_found: int
    parsed_count: int
    unparsed_count: int
    pending_review_count: int
    triggered_by_user_id: int | None
    started_at: datetime


class BreakingChangeAlert(BaseModel):
    """1 cảnh báo breaking change — tự phát hiện trong graph_build_node khi 1
    bảng bị DROP/RENAME nhưng vẫn còn bảng downstream tham chiếu, không cần
    user chủ động paste DDL vào DDL preview mới biết."""

    id: int
    kind: Literal["drop", "rename"]
    table_name: str
    new_name: str | None
    downstream_tables: list[str]
    suggested_action: str
    detected_at: datetime
    acknowledged: bool


class TableDescription(BaseModel):
    table: str
    description: str
    source: Literal["llm", "human"]
    label: str | None = None
    confidence: float | None = None
    is_stale: bool = False
    updated_at: datetime


class PendingDescription(BaseModel):
    node_id: int
    table: str
    description: str
    label: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_hash: str
    created_at: datetime
    base_source: Literal["llm", "human"] | None = None
    base_hash: str | None = None
    is_stale_proposal: bool = False
    current_description: str | None = None


class DescriptionMatch(BaseModel):
    table: str
    score: float


class DescriptionUpdateRequest(BaseModel):
    description: str = Field(..., min_length=1)


class PendingColumnDescription(BaseModel):
    node_id: int
    table: str
    column: str
    description: str
    label: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_hash: str
    created_at: datetime
    base_source: Literal["llm", "human"] | None = None
    base_hash: str | None = None
    is_stale_proposal: bool = False
    current_description: str | None = None


class ColumnDescriptionMatch(BaseModel):
    table: str
    column: str
    score: float


class ChatRequest(BaseModel):
    """A natural-language lineage question and optional in-process session id."""

    question: str = Field(..., min_length=1, max_length=2000)
    database_id: int
    session_id: str | None = None


class ChatStep(BaseModel):
    """A complete trace of one deterministic chat capability invocation."""

    tool: str
    args: dict
    resolved: dict | None = None
    error: str | None = None
    summary: str
    duration_ms: int
    agent_step: int


class ChatResponse(BaseModel):
    """Grounded chat result with confirmed and unreviewed edges kept separate."""

    session_id: str
    answer: str
    confirmed: list[ImpactEdgeView] = Field(default_factory=list)
    inferred_pending: list[ImpactEdgeView] = Field(default_factory=list)
    clarification_options: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    steps: list[ChatStep] = Field(default_factory=list)
    stop_reason: Literal["clarification", "budget_exhausted", "completed"]
    tool_calls_used: int = Field(default=0, ge=0)


class DatabaseResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    created_at: datetime
    role: Literal["engineer", "viewer"]


class DatabaseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class MemberResponse(BaseModel):
    user_id: int
    email: str
    display_name: str | None
    role: Literal["engineer", "viewer"]


class MemberUpsertRequest(BaseModel):
    user_id: int
    role: Literal["engineer", "viewer"]


class AssetProfile(BaseModel):
    """Full asset metadata exposed to the chat agent by ``get_asset``."""

    name: str
    defined_in: str | None = None
    is_defined: bool
    has_description: bool = False
    columns_produced: list[str] = Field(default_factory=list)
    columns_consumed: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    confidence_min: float | None = None
    confidence_max: float | None = None
    transform_types: list[str] = Field(default_factory=list)
    last_modified: str | None = None
    first_seen: str | None = None
    modified_count: int
    previous_names: list[dict[str, str]] = Field(default_factory=list)
    is_dropped: bool
    dropped_at: str | None = None
    pending_count: int


class UserPublic(BaseModel):
    id: int
    email: str
    display_name: str | None


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserPublic
