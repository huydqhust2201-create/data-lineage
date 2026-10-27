"""Lõi chạy 1 lượt ingest — dùng chung cho POST /ingest, POST /ingest/upload
(src/api/routes.py) và ingest_watcher.py (tự động re-ingest khi phát hiện file
đổi). Tách riêng khỏi routes.py để watcher không phải import từ tầng API.
"""

from __future__ import annotations

from src.agents.graph import agent
from src.models.schemas import GraphNode, IngestResponse, LineageEdge, OverviewGraph
from src.services import review_service, storage_service


def _overview_graph(confirmed: list[LineageEdge], pending: list[LineageEdge]) -> OverviewGraph:
    """Đồ thị table-level từ các cạnh VỪA phát hiện trong 1 lượt ingest (không
    phải toàn bộ đồ thị tích luỹ trong Postgres) — Luồng A trong spec evidence.

    confirmed_edges/pending_edges tách riêng — GỘP CHUNG từng gây bug thật:
    caller lấy nhầm edge_id của cạnh confirmed để gọi /pending-review/{id}/confirm,
    nhận 404 vì cạnh đó chưa từng vào hàng đợi pending.
    """
    tables = {e.source_table for e in confirmed + pending} | {e.target_table for e in confirmed + pending}
    return OverviewGraph(
        nodes=[GraphNode(id=t, label=t) for t in sorted(tables)],
        confirmed_edges=confirmed,
        pending_edges=pending,
    )


async def run_ingest(input_path: str, database_id: int, user_id: int | None) -> IngestResponse:
    """Chạy pipeline parse -> LLM fallback -> HITL -> graph build cho 1
    input_path, rồi ghi lại log lịch sử. user_id=None khi lượt ingest do hệ
    thống tự trigger (auto re-ingest), không phải user chủ động bấm nút."""
    result = await agent.ainvoke({"input_path": input_path, "database_id": database_id})

    confirmed: list[LineageEdge] = result.get("confirmed_edges", [])
    pending: list[LineageEdge] = result.get("pending_review", [])
    review_service.add_pending(database_id, pending)

    # `parsed_count` là con số headline "cạnh parser đọc được" hiển thị trên UI —
    # đếm cạnh DATA LINEAGE (dependency_kind="output"). Cạnh control lineage
    # (filter/join_key/group_key/window_*) vẫn vào đồ thị và impact analysis
    # nhưng không thổi phồng con số này (1 file JOIN nhiều bảng có thể sinh 3-4x
    # cạnh control).
    output_edges = [e for e in result.get("parsed_edges", []) if e.dependency_kind == "output"]
    response = IngestResponse(
        sql_files_found=len(result.get("sql_files", [])),
        parsed_count=len(output_edges),
        unparsed_count=len(result.get("unparsed_files", [])),
        pending_review_count=len(pending),
        overview_graph=_overview_graph(confirmed, pending),
        description_pending_count=result.get("descriptions_pending", 0) + result.get("column_descriptions_pending", 0),
    )
    # Chỉ là log audit — 1 project có thể ingest nhiều lần từ nhiều path khác
    # nhau, không đổi cách dữ liệu gộp vào graph (vẫn cộng dồn theo database_id).
    storage_service.record_ingest_run(
        database_id,
        input_path,
        sql_files_found=response.sql_files_found,
        parsed_count=response.parsed_count,
        unparsed_count=response.unparsed_count,
        pending_review_count=response.pending_review_count,
        triggered_by_user_id=user_id,
    )
    return response
