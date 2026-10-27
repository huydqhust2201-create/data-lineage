import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal

import networkx as nx  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse

from src.agents.chat import session as chat_session
from src.api.deps import current_user, ensure_database_role, require_database_role_query
from src.config import get_settings
from src.models.schemas import (
    BreakingChangeAlert,
    ChatRequest,
    ChatResponse,
    DescriptionUpdateRequest,
    GraphNode,
    GraphResponse,
    ImpactQueryResult,
    IngestRequest,
    IngestResponse,
    IngestRun,
    LineageEdge,
    PendingColumnDescription,
    PendingDescription,
)
from src.services import (
    chat_service,
    column_description_review_service,
    description_review_service,
    description_service,
    embedding_service,
    graph_service,
    impact_service,
    ingest_service,
    review_service,
    storage_service,
)

router = APIRouter(dependencies=[Depends(current_user)])


def _safe_relative_path(raw_name: str) -> Path | None:
    """Chuẩn hoá tên file client gửi lên (giữ cấu trúc thư mục con qua
    webkitRelativePath) — chặn path traversal (`..`) và path tuyệt đối trước
    khi ghi xuống thư mục tạm trên server."""
    posix = PurePosixPath(raw_name.replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts or not posix.parts:
        return None
    return Path(*posix.parts)


@router.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest, user=Depends(current_user)) -> IngestResponse:
    """FR-1..FR-5: parse -> LLM fallback -> phân loại HITL -> ghi graph.

    Trả kèm overview_graph (Luồng A): bức tranh table-level của lượt ingest
    này, để FE vẽ ngay không cần đợi user submit 1 impact query trước.
    """
    ensure_database_role(request.database_id, user, {"engineer"})
    return await ingest_service.run_ingest(request.input_path, request.database_id, user.id)


@router.post("/ingest/upload", response_model=IngestResponse)
async def ingest_upload(
    files: list[UploadFile] = File(...),
    last_modified: str | None = Form(default=None),
    database_id: int = Form(...),
    user=Depends(current_user),
) -> IngestResponse:
    """Nhận file .sql tải trực tiếp từ máy user (không cần biết đường dẫn
    server) — ghi tạm ra 1 thư mục trên server rồi chạy đúng pipeline như
    /ingest. Giữ cấu trúc thư mục con qua tên file (client gửi kèm
    webkitRelativePath làm filename) để evidence.file_path còn ý nghĩa.

    """
    sql_files = [f for f in files if (f.filename or "").lower().endswith(".sql")]
    if not sql_files:
        raise HTTPException(status_code=400, detail="Không có file .sql nào trong danh sách tải lên")

    with tempfile.TemporaryDirectory(prefix="lineage-upload-") as tmp:
        try:
            stamps = json.loads(last_modified) if last_modified else {}
        except (TypeError, json.JSONDecodeError):
            stamps = {}
        if not isinstance(stamps, dict):
            stamps = {}
        tmp_root = Path(tmp)
        written = 0
        # None = file nằm phẳng ở root (không có thư mục cha) — vẫn là 1 giá
        # trị hợp lệ trong set này, để "1 file phẳng + 1 file trong thư mục"
        # đúng nghĩa KHÔNG đồng nhất (len > 1), không suy nhầm theo file có
        # thư mục và bỏ qua file phẳng.
        top_level_dirs: set[str | None] = set()
        for f in sql_files:
            rel = _safe_relative_path(f.filename or "")
            if rel is None:
                continue
            top_level_dirs.add(rel.parts[0] if len(rel.parts) > 1 else None)
            dest = tmp_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(await f.read())
            stamp = stamps.get(f.filename or "")
            if isinstance(stamp, (int, float)):
                os.utime(dest, (stamp / 1000, stamp / 1000))
            written += 1

        if written == 0:
            raise HTTPException(status_code=400, detail="Tên file tải lên không hợp lệ")

        ensure_database_role(database_id, user, {"engineer"})
        return await ingest_service.run_ingest(str(tmp_root), database_id, user.id)


@router.get("/ingest-runs", response_model=list[IngestRun])
async def list_ingest_runs(
    database_id: int, _user=Depends(require_database_role_query("engineer", "viewer"))
) -> list[IngestRun]:
    """Lịch sử ingest của 1 database — để user xem lại đã ingest gì, từ path
    nào, khi nào (project có thể ingest nhiều lần từ nhiều thư mục khác nhau)."""
    return [
        IngestRun(
            id=run.id,
            input_path=run.input_path,
            sql_files_found=run.sql_files_found,
            parsed_count=run.parsed_count,
            unparsed_count=run.unparsed_count,
            pending_review_count=run.pending_review_count,
            triggered_by_user_id=run.triggered_by_user_id,
            started_at=run.started_at,
        )
        for run in storage_service.list_ingest_runs(database_id)
    ]


@router.get("/breaking-change-alerts", response_model=list[BreakingChangeAlert])
async def list_breaking_change_alerts(
    database_id: int,
    include_acknowledged: bool = False,
    _user=Depends(require_database_role_query("engineer", "viewer")),
) -> list[BreakingChangeAlert]:
    """Cảnh báo breaking change tự phát hiện khi ingest (bảng bị DROP/RENAME
    nhưng vẫn còn bảng downstream tham chiếu) — không cần user tự paste DDL
    vào DDL preview mới biết."""
    return [
        BreakingChangeAlert(
            id=alert.id,
            kind=alert.kind,
            table_name=alert.table_name,
            new_name=alert.new_name,
            downstream_tables=alert.downstream_tables,
            suggested_action=alert.suggested_action,
            detected_at=alert.detected_at,
            acknowledged=alert.acknowledged,
        )
        for alert in storage_service.list_breaking_change_alerts(database_id, include_acknowledged)
    ]


@router.post("/breaking-change-alerts/{alert_id}/acknowledge", status_code=204)
async def acknowledge_breaking_change_alert(
    alert_id: int, database_id: int, _user=Depends(require_database_role_query("engineer"))
) -> Response:
    if not storage_service.acknowledge_breaking_change_alert(database_id, alert_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo này")
    return Response(status_code=204)


@router.get("/pending-review", response_model=list[LineageEdge])
async def list_pending_review(database_id: int, _user=Depends(require_database_role_query("engineer", "viewer"))) -> list[LineageEdge]:
    """FR-4: cạnh đang chờ xác nhận."""
    return review_service.list_pending(database_id)


@router.post("/pending-review/{edge_id}/confirm", response_model=LineageEdge)
async def confirm_pending_review(edge_id: str, database_id: int, _user=Depends(require_database_role_query("engineer"))) -> LineageEdge:
    """FR-4/FR-5: xác nhận 1 cạnh -> ghi chính thức vào graph + persist.

    Sau lệnh này, cạnh biến mất khỏi inferred_pending và xuất hiện trong
    confirmed ở lần GET /impact tiếp theo — không cần re-ingest.
    """
    pending_edge = review_service.pop_pending(database_id, edge_id)
    if pending_edge is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy cạnh chờ duyệt: {edge_id}")
    # Ghi lại thời điểm duyệt — cạnh LLM sau khi confirm vẫn cần phân biệt
    # được với cạnh parser (luôn chắc chắn), không phải chỉ đổi màu "xanh"
    # rồi mất hết dấu vết đây từng là suy luận AI đã qua người duyệt.
    confirmed_edge = pending_edge
    if pending_edge.evidence is not None:
        confirmed_edge = pending_edge.model_copy(
            update={"evidence": pending_edge.evidence.model_copy(update={"confirmed_at": datetime.now(UTC)})}
        )
    try:
        with graph_service.commit_lock():
            with storage_service.transaction() as tx:
                storage_service.advisory_lock(tx)
                working = storage_service.load(database_id, tx)
                graph_service.add_edge(database_id, confirmed_edge, graph=working)
                storage_service.ensure_node(database_id, confirmed_edge.source_table, tx)
                storage_service.ensure_node(database_id, confirmed_edge.target_table, tx)
                storage_service.save(database_id, working, tx)
            graph_service.replace_graph(database_id, working)
    except Exception:
        review_service.add_pending(database_id, [pending_edge])
        raise
    return confirmed_edge


@router.post("/pending-review/{edge_id}/reject", status_code=204)
async def reject_pending_review(edge_id: str, database_id: int, _user=Depends(require_database_role_query("engineer"))) -> None:
    """FR-4: từ chối 1 cạnh -> loại bỏ, không ghi vào graph."""
    edge = review_service.pop_pending(database_id, edge_id)
    if edge is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy cạnh chờ duyệt: {edge_id}")


@router.get("/descriptions/pending", response_model=list[PendingDescription])
async def list_pending_descriptions(database_id: int, _user=Depends(require_database_role_query("engineer", "viewer"))) -> list[PendingDescription]:
    return description_review_service.list_pending(database_id)


@router.post("/descriptions/{node_id}/confirm")
async def confirm_pending_description(node_id: int, database_id: int, _user=Depends(require_database_role_query("engineer"))) -> PendingDescription:
    item = description_review_service.pop_pending(database_id, str(node_id))
    if item is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy mô tả chờ duyệt: {node_id}")
    if storage_service.load_description_node(database_id, node_id) is None:
        description_review_service.add_pending(database_id, [item])
        raise HTTPException(status_code=404, detail=f"Không tìm thấy node: {node_id}")
    vectors = embedding_service.embed([item.description])
    record = storage_service.DescriptionRecord(
        node_id=node_id,
        description=item.description,
        source="llm",
        label=item.label,
        confidence=item.confidence,
        evidence_hash=item.evidence_hash,
        is_stale=False,
    )
    if not storage_service.confirm_pending_description(
        database_id, record, vectors[0] if vectors else None, item.base_source, item.base_hash
    ):
        description_review_service.add_pending(database_id, [item])
        raise HTTPException(status_code=409, detail="Bản mô tả mới hơn đã tồn tại")
    return item


@router.post("/descriptions/{node_id}/reject", status_code=204)
async def reject_pending_description(node_id: int, database_id: int, _user=Depends(require_database_role_query("engineer"))) -> Response:
    if description_review_service.pop_pending(database_id, str(node_id)) is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy mô tả chờ duyệt: {node_id}")
    return Response(status_code=204)


@router.put("/descriptions/{node_id}", status_code=200)
async def put_description(node_id: int, request: DescriptionUpdateRequest, database_id: int, _user=Depends(require_database_role_query("engineer"))) -> None:
    node = storage_service.load_description_node(database_id, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy node: {node_id}")
    live_nodes = storage_service.load_live_nodes_for_description(database_id)
    if any(live.node_id == node_id for live in live_nodes):
        neighbours = {live.record.current_name: live.record for live in live_nodes}
        evidence = description_service.evidence_hash(description_service.build_evidence_payload(node, neighbours))
    else:
        evidence = node.description.evidence_hash if node.description else ""
    vectors = embedding_service.embed([request.description])
    if not storage_service.put_human_description(
        database_id, node_id, request.description, evidence, vectors[0] if vectors else None
    ):
        raise HTTPException(status_code=404, detail=f"Không tìm thấy node: {node_id}")
    description_review_service.pop_pending(database_id, str(node_id))


@router.get("/column-descriptions/pending", response_model=list[PendingColumnDescription])
async def list_pending_column_descriptions(database_id: int, _user=Depends(require_database_role_query("engineer", "viewer"))) -> list[PendingColumnDescription]:
    return column_description_review_service.list_pending(database_id)


@router.post("/column-descriptions/{node_id}/{column}/confirm")
async def confirm_pending_column_description(node_id: int, column: str, database_id: int, _user=Depends(require_database_role_query("engineer"))) -> PendingColumnDescription:
    item = column_description_review_service.pop_pending(database_id, node_id, column)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy mô tả cột chờ duyệt: {node_id}.{column}")
    if storage_service.load_description_node(database_id, node_id) is None:
        column_description_review_service.add_pending(database_id, [item])
        raise HTTPException(status_code=404, detail=f"Không tìm thấy node: {node_id}")
    vectors = embedding_service.embed([item.description])
    record = storage_service.ColumnDescriptionRecord(
        node_id=node_id,
        column_name=column,
        description=item.description,
        source="llm",
        label=item.label,
        confidence=item.confidence,
        evidence_hash=item.evidence_hash,
        is_stale=False,
    )
    if not storage_service.confirm_pending_column_description(
        database_id, record, vectors[0] if vectors else None, item.base_source, item.base_hash
    ):
        column_description_review_service.add_pending(database_id, [item])
        raise HTTPException(status_code=409, detail="Bản mô tả cột mới hơn đã tồn tại")
    return item


@router.post("/column-descriptions/{node_id}/{column}/reject", status_code=204)
async def reject_pending_column_description(node_id: int, column: str, database_id: int, _user=Depends(require_database_role_query("engineer"))) -> Response:
    if column_description_review_service.pop_pending(database_id, node_id, column) is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy mô tả cột chờ duyệt: {node_id}.{column}")
    return Response(status_code=204)


@router.put("/column-descriptions/{node_id}/{column}", status_code=200)
async def put_column_description(node_id: int, column: str, request: DescriptionUpdateRequest, database_id: int, _user=Depends(require_database_role_query("engineer"))) -> None:
    node = storage_service.load_description_node(database_id, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy node: {node_id}")
    live_nodes = storage_service.load_live_nodes_for_description(database_id)
    if any(live.node_id == node_id for live in live_nodes):
        evidence = description_service.evidence_hash(
            description_service.build_column_evidence_payload(database_id, node.record.current_name, column)
        )
    else:
        existing = storage_service.load_column_descriptions(database_id, [node_id]).get((node_id, column))
        evidence = existing.evidence_hash if existing else ""
    vectors = embedding_service.embed([request.description])
    if not storage_service.put_human_column_description(
        database_id, node_id, column, request.description, evidence, vectors[0] if vectors else None
    ):
        raise HTTPException(status_code=404, detail=f"Không tìm thấy node: {node_id}")
    column_description_review_service.pop_pending(database_id, node_id, column)


@router.get("/impact/{table}", response_model=ImpactQueryResult)
async def impact_analysis(
    database_id: int,
    table: str,
    direction: Literal["downstream", "upstream"],
    column: str | None = None,
    change_kind: impact_service.ChangeKind | None = None,
    target_type: str | None = None,
    _user=Depends(require_database_role_query("engineer", "viewer")),
) -> ImpactQueryResult:
    """FR-6/US-5/US-6, US-3/US-4: impact analysis 2 chiều — tách rõ `confirmed`
    (parser hoặc LLM đã qua HITL) vs `inferred_pending` (LLM confidence thấp,
    CHƯA qua HITL). Không bao giờ gộp chung 2 khối này.

    change_kind (tuỳ chọn): "type" (đổi kiểu dữ liệu cột), "value" (đổi giá
    trị cột), "drop" (xóa cột), "rename" (đổi tên cột), "drop_table" (xóa cả
    bảng), "rename_table" (đổi tên cả bảng), "add_column" (thêm cột mới),
    hoặc "constraint" (thêm NOT NULL/đổi PK-FK/đổi partition key) — khi có,
    mỗi cạnh trả về kèm `risk`: rủi ro cụ thể của cạnh đó dựa theo
    transform_type (join/aggregation/direct/unknown). Dùng type alias
    `impact_service.ChangeKind` trực tiếp thay vì lặp lại `Literal[...]` ở
    đây — tránh 2 nơi cùng liệt kê rồi lệch nhau khi thêm change_kind mới.

    target_type (tuỳ chọn, chỉ dùng với change_kind="type"): kiểu dữ liệu đích
    muốn đổi sang — khi có + cột đang đổi có schema, `risk` phân loại chuyển
    kiểu là mở rộng an toàn / thu hẹp mất dữ liệu / đổi họ kiểu nghiêm trọng."""
    return impact_service.query_impact(database_id, table, column, direction, change_kind, target_type)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user=Depends(current_user)) -> ChatResponse:
    """`request.session_id` chỉ giữ để tương thích ngược với frontend hiện có
    (luôn gửi kèm) — bị bỏ qua hoàn toàn. Định danh luồng hội thoại thật là
    (database_id, user_id): 1 user có đúng 1 luồng liên tục cho mỗi database,
    giống cách Claude Code lưu conversation theo user/project thay vì UUID
    ngẫu nhiên per-request (xem src/agents/chat/session.py)."""
    ensure_database_role(request.database_id, user, {"engineer", "viewer"})
    return chat_service.answer_question(request.question, user.id, request.database_id)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, user=Depends(current_user)) -> StreamingResponse:
    ensure_database_role(request.database_id, user, {"engineer", "viewer"})

    def events():
        for event in chat_service.answer_question_stream(request.question, user.id, request.database_id):
            data = event["data"]
            if hasattr(data, "model_dump"):
                data = data.model_dump(mode="json")
            yield f"event: {event['event']}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/chat/reset", status_code=204)
async def reset_chat(
    database_id: int, _user=Depends(require_database_role_query("engineer", "viewer"))
) -> Response:
    """"Bắt đầu lại" luồng hội thoại của chính người gọi — xoá lịch sử, giữ
    nguyên định danh (database_id, user_id)."""
    chat_session.reset(database_id, _user.id)
    return Response(status_code=204)


@router.get("/graph", response_model=GraphResponse)
async def get_graph(database_id: int, _user=Depends(require_database_role_query("engineer", "viewer"))) -> GraphResponse:
    """FR-7: toàn bộ đồ thị đã xác nhận (tích luỹ, không chỉ lượt ingest gần nhất).

    """
    edges = graph_service.get_all_edges(database_id)
    tables = sorted({edge.source_table for edge in edges} | {edge.target_table for edge in edges})
    descriptions = storage_service.load_descriptions_by_names(database_id, tables)
    column_descriptions = storage_service.load_column_descriptions_by_names(database_id, tables)
    column_schema = storage_service.load_column_schema_by_names(database_id, tables)
    columns_by_table: dict[str, list[dict]] = {}
    for (table, column), record in column_descriptions.items():
        columns_by_table.setdefault(table, []).append(
            {"column": column, "description": record.description, "label": record.label, "source": record.source, "is_stale": record.is_stale}
        )
    nodes = []
    for table in tables:
        description = descriptions.get(table)
        columns = columns_by_table.get(table, [])
        nodes.append(GraphNode(id=table, label=table, description=description.description if description else None,
            description_label=description.label if description else None, description_source=description.source if description else None,
            description_is_stale=description.is_stale if description else False, columns=columns,
            column_schemas=column_schema.get(table, [])))
    return GraphResponse(nodes=nodes, edges=edges)



@router.delete("/graph", status_code=204)
async def clear_graph(database_id: int, _user=Depends(require_database_role_query("engineer"))) -> None:
    """Xoá đồ thị lineage, alert breaking-change và hàng đợi HITL đang chờ duyệt.

    Ingest KHÔNG tự động gọi endpoint này — nhiều lần ingest riêng biệt vẫn
    cộng dồn thành 1 đồ thị lineage toàn dự án theo thiết kế. Đây là hành
    động chủ động của người dùng khi muốn bắt đầu lại từ đầu.
    """
    with graph_service.commit_lock():
        with storage_service.transaction() as tx:
            storage_service.advisory_lock(tx)
            storage_service.save(database_id, nx.MultiDiGraph(), tx)
            storage_service.clear_nodes(database_id, tx)
            storage_service.clear_breaking_change_alerts(database_id, tx)
        graph_service.replace_graph(database_id, nx.MultiDiGraph())
        review_service.clear_pending(database_id)
        description_review_service.clear_pending(database_id)
        column_description_review_service.clear_pending(database_id)


@router.get("/status")
async def agent_status():
    """Kiểm tra trạng thái agent — health check thật (không còn trả cứng).

    Giữ nguyên field status/agent (frontend chỉ đọc đúng 2 field này qua
    StatusResponse) để không phá hợp đồng cũ, thêm "checks" là superset.
    llm_configured chỉ kiểm tra có API key, KHÔNG gọi OpenRouter thật —
    tránh tốn phí mỗi lần health check.
    """
    settings = get_settings()
    checks: dict[str, bool] = {
        "database": storage_service.ping(),
        "llm_configured": bool(settings.openrouter_api_key),
    }
    if settings.description_enabled:
        checks["embedding_service"] = embedding_service.is_reachable()
    healthy = all(checks.values())
    return {"status": "ready" if healthy else "degraded", "agent": "Lineage Agent v1.0", "checks": checks}
