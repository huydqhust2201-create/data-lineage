import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import networkx as nx

from src.agents.state import LineageAgentState
from src.config import get_settings
from src.models.schemas import GraphEvent, LineageEdge, PendingColumnDescription, PendingDescription
from src.services import (
    asset_service,
    column_description_review_service,
    description_review_service,
    description_service,
    embedding_service,
    graph_service,
    llm_extraction_service,
    parser_service,
    sql_document_service,
    storage_service,
)

logger = logging.getLogger(__name__)

_parser = None


def _get_parser():
    global _parser
    if _parser is None:
        _parser = parser_service.SQLParserService(default_dialect=get_settings().sql_dialect)
    return _parser


def _normalize_evidence_path(edge: LineageEdge, input_path: str) -> LineageEdge:
    """Keep graph event paths absolute while making edge citations portable."""
    if edge.evidence is None or edge.evidence.file_path is None:
        return edge
    evidence = edge.evidence.model_copy(
        update={"file_path": asset_service.relative_to_ingest_root(edge.evidence.file_path, input_path)}
    )
    return edge.model_copy(update={"evidence": evidence})


def _normalize_event_evidence_paths(events: list[GraphEvent], input_path: str) -> list[GraphEvent]:
    return [
        event.model_copy(update={"edges": [_normalize_evidence_path(edge, input_path) for edge in event.edges]})
        if event.kind == "edges"
        else event
        for event in events
    ]


def parse_node(state: LineageAgentState) -> dict:
    """FR-1/FR-2: quét file .sql trong input_path, parse bằng sqlglot.

    File chỉ có DDL hợp lệ cũng là parse thành công, dù chưa có lineage edge.
    Chỉ file không tạo được event nào mới chuyển qua LLM (FR-3), kèm lý do
    cụ thể (fallback_reason) để LLM/evidence dùng lại.
    """
    input_path = state["input_path"]
    sql_files = sorted(str(p) for p in Path(input_path).rglob("*.sql"))

    parsed_edges: list[LineageEdge] = []
    graph_events: list[GraphEvent] = []
    unparsed_files = []
    fallback_reasons: dict[str, str] = {}
    parser_instance = _get_parser()
    for file_path in sql_files:
        events, reason = parser_instance.parse_file_events(file_path)
        if events:
            events = _normalize_event_evidence_paths(events, input_path)
            graph_events.extend(events)
            parsed_edges.extend(edge for event in events if event.kind == "edges" for edge in event.edges)
        elif reason is None:
            # Không có event lẫn lý do fail = parser đã xác định chắc chắn file
            # này không có gì để trích (vd macro dbt thuần) — không phải thất
            # bại, không cần LLM fallback (khác voi reason có giá trị, luôn có
            # nghĩa "cần LLM giúp").
            continue
        else:
            unparsed_files.append(file_path)
            fallback_reasons[file_path] = reason

    logger.info(
        "parse_node: %d file, %d cạnh parser, %d file cần LLM", len(sql_files), len(parsed_edges), len(unparsed_files)
    )
    return {
        "sql_files": sql_files,
        "parsed_edges": parsed_edges,
        "graph_events": graph_events,
        "unparsed_files": unparsed_files,
        "fallback_reasons": fallback_reasons,
    }


def llm_extract_node(state: LineageAgentState) -> dict:
    """FR-3: file parser fail -> LLM extraction, kèm log rõ nhánh xử lý."""
    unparsed_files = state.get("unparsed_files", [])
    if not unparsed_files:
        return {"llm_edges": [], "graph_events": []}

    fallback_reasons = state.get("fallback_reasons", {})
    try:
        results = llm_extraction_service.extract_edges_from_files(unparsed_files, fallback_reasons=fallback_reasons)
        llm_edges = [edge for edges in results.values() for edge in edges]
        graph_events = [
            GraphEvent(file_path=file_path, order=0, kind="edges", edges=edges)
            for file_path, edges in results.items()
            if edges
        ]
        graph_events = _normalize_event_evidence_paths(graph_events, state["input_path"])
        llm_edges = [edge for event in graph_events if event.kind == "edges" for edge in event.edges]
        logger.info("llm_extract_node: %d file -> %d cạnh LLM", len(unparsed_files), len(llm_edges))
        return {"llm_edges": llm_edges, "graph_events": graph_events}
    except Exception as e:
        logger.exception("llm_extract_node failed: %s", e)
        return {"llm_edges": [], "graph_events": [], "error": f"Lỗi trong quá trình trích xuất LLM: {str(e)}"}


def hitl_node(state: LineageAgentState) -> dict:
    """FR-4: cạnh confidence >= threshold thì xác nhận thẳng, còn lại chờ HITL.

    Không dùng LangGraph interrupt — confirm/reject thật xảy ra qua API riêng
    (POST /pending-review/{edge_id}/confirm|reject) sau khi lượt ingest này
    đã trả response, nên node này chỉ cần PHÂN LOẠI, không cần pause.
    """
    threshold = get_settings().confidence_threshold
    all_edges = state.get("parsed_edges", []) + state.get("llm_edges", [])

    confirmed = [e for e in all_edges if e.confidence >= threshold]
    pending = [e for e in all_edges if e.confidence < threshold]

    logger.info(
        "hitl_node: %d cạnh xác nhận thẳng, %d cạnh chờ HITL (threshold=%.2f)", len(confirmed), len(pending), threshold
    )
    return {"confirmed_edges": confirmed, "pending_review": pending}


def _breaking_change_suggestion(kind: str, table: str, new_name: str | None, downstream: list[str]) -> str:
    preview = ", ".join(downstream[:5])
    if len(downstream) > 5:
        preview += f" và {len(downstream) - 5} bảng khác"
    if kind == "drop":
        return (
            f"Bảng '{table}' đã bị xoá khỏi source, nhưng {len(downstream)} bảng downstream vẫn tham chiếu "
            f"tới nó ({preview}). Cân nhắc giữ lại 1 view tương thích ngược hoặc cập nhật các model đó "
            f"trước khi merge."
        )
    return (
        f"Bảng '{table}' đã đổi tên thành '{new_name}', {len(downstream)} bảng downstream cần cập nhật "
        f"tham chiếu ({preview})."
    )


def _propagate_column_schema(
    graph: nx.MultiDiGraph, declared: dict[str, list[dict]]
) -> dict[str, list[dict]]:
    """Tier 2 (Chủ đề 3): lan KIỂU DỮ LIỆU cột qua cạnh parser
    `transform_type='direct'` (truyền cột nguyên trạng qua SELECT).

    CHỈ mang `data_type`. KHÔNG mang:
    - PK/FK: khoá không "chảy" qua SELECT.
    - `is_nullable`: 1 cột NOT NULL đi qua LEFT JOIN trở thành nullable, nhưng
      `_propagate_column_schema` không nhìn thấy loại JOIN từ đồ thị. Khẳng định
      NOT NULL sai còn nguy hiểm hơn (impact sẽ báo "no-op") nên cột propagated
      luôn để `is_nullable=True` = "chưa xác định, giả định cho phép NULL".
      `schema_change_note` xử lý riêng cột `origin='propagated'` khi đổi constraint.

    Đi theo thứ tự topo để chuỗi nhiều hop (raw->stg->int->mart) điền dần. Bỏ
    qua toàn bộ nếu đồ thị có chu trình. Không đè lên cột đã có schema 'declared'.
    """
    try:
        order = list(nx.topological_sort(graph))
    except nx.NetworkXUnfeasible:
        return {}
    known: dict[str, dict[str, dict]] = {
        t: {c["name"]: c for c in cols} for t, cols in declared.items()
    }
    propagated: dict[str, list[dict]] = {}
    for node in order:
        for src, _tgt, attrs in graph.in_edges(node, data=True):
            if attrs.get("source_type") != "parser" or attrs.get("transform_type") != "direct":
                continue
            sc, tc = attrs.get("source_column"), attrs.get("target_column")
            if not sc or not tc or tc in known.get(node, {}):
                continue
            src_col = known.get(src, {}).get(sc)
            if src_col is None or src_col.get("data_type") is None:
                continue
            entry = {
                "name": tc,
                "data_type": src_col["data_type"],
                "is_nullable": True,  # xem docstring — không suy được qua đồ thị
                "is_primary_key": False,
                "is_foreign_key": False,
                "references_table": None,
                "references_column": None,
                "origin": "propagated",
            }
            known.setdefault(node, {})[tc] = entry
            propagated.setdefault(node, []).append(entry)
    return propagated


def graph_build_node(state: LineageAgentState) -> dict:
    """Apply graph events and metadata atomically, then replace RAM after commit."""
    confirmed_ids = {edge.edge_id for edge in state.get("confirmed_edges", [])}
    rename_count = 0
    drop_count = 0
    events = sorted(state.get("graph_events", []), key=lambda item: (item.file_path, item.order))

    database_id = state["database_id"]
    with graph_service.commit_lock():
        with storage_service.transaction() as tx:
            storage_service.advisory_lock(tx)
            working = storage_service.load(database_id, tx)
            graph_changed = False
            definitions: dict[str, str] = {}
            declared_columns: dict[str, list[dict]] = {}
            lifecycle_ops: list[tuple] = []
            # Phát hiện breaking change TRƯỚC khi áp dụng drop/rename — so trên
            # `working` lúc còn nguyên vẹn (nx.descendants cho toàn bộ bảng
            # downstream đa tầng, không chỉ hàng xóm trực tiếp). Không cần user
            # tự paste DDL vào DDL preview mới biết; tự động ngay lúc ingest.
            breaking_changes: list[storage_service.BreakingChangeDetection] = []
            for event in events:
                occurred_at = datetime.fromtimestamp(os.stat(event.file_path).st_mtime, UTC)
                if event.kind == "edges":
                    for edge in event.edges:
                        if edge.edge_id in confirmed_ids:
                            graph_changed |= graph_service.add_edge(database_id, edge, graph=working)
                elif event.kind == "declare" and event.table is not None:
                    definitions[event.table] = event.file_path
                    if event.columns:
                        declared_columns[event.table] = [c.model_dump() for c in event.columns]
                elif event.kind == "rename" and event.table is not None and event.new_name is not None:
                    downstream = sorted(nx.descendants(working, event.table)) if event.table in working else []
                    if downstream:
                        breaking_changes.append(
                            storage_service.BreakingChangeDetection(
                                "rename",
                                event.table,
                                event.new_name,
                                downstream,
                                _breaking_change_suggestion("rename", event.table, event.new_name, downstream),
                            )
                        )
                    graph_changed |= graph_service.rename_table(database_id, event.table, event.new_name, graph=working)
                    if event.table in definitions:
                        definitions[event.new_name] = definitions.pop(event.table)
                    if event.table in declared_columns:
                        declared_columns[event.new_name] = declared_columns.pop(event.table)
                    lifecycle_ops.append(("rename", event.table, event.new_name, occurred_at))
                    rename_count += 1
                elif event.kind == "drop" and event.table is not None:
                    downstream = sorted(nx.descendants(working, event.table)) if event.table in working else []
                    if downstream:
                        breaking_changes.append(
                            storage_service.BreakingChangeDetection(
                                "drop",
                                event.table,
                                None,
                                downstream,
                                _breaking_change_suggestion("drop", event.table, None, downstream),
                            )
                        )
                    graph_changed |= graph_service.drop_table(database_id, event.table, graph=working)
                    definitions.pop(event.table, None)
                    declared_columns.pop(event.table, None)  # nếu không, replace_column_schema dưới re-insert lại
                    lifecycle_ops.append(("drop", event.table, occurred_at))
                    drop_count += 1

            for op in lifecycle_ops:
                if op[0] == "rename":
                    node_id = storage_service.ensure_node(database_id, op[1], tx)
                    if storage_service.rename_node_by_id(database_id, node_id, op[2], tx):
                        storage_service.append_node_events(database_id,
                            [storage_service.NodeEvent(node_id, "rename", op[3], {"from": op[1], "to": op[2]})], tx
                        )
                    storage_service.rename_column_schema_table(database_id, op[1], op[2], tx)
                else:
                    node_id = storage_service.ensure_node(database_id, op[1], tx)
                    if storage_service.mark_dropped(database_id, node_id, op[2], tx):
                        storage_service.append_node_events(database_id, [storage_service.NodeEvent(node_id, "drop", op[2])], tx)
                    storage_service.drop_column_schema_table(database_id, op[1], tx)

            records = asset_service.build_records_from_graph(working, definitions, state["input_path"])
            revived = storage_service.revive_nodes(database_id, records, tx)
            storage_service.append_node_events(database_id,
                [storage_service.NodeEvent(node_id, "recreated", occurred_at) for node_id, _, occurred_at in revived],
                tx,
            )
            node_ids = storage_service.upsert_nodes(database_id, records, tx)
            modified: list[storage_service.NodeEvent] = []
            for record in records:
                if record.source_file is None or not os.path.exists(record.source_file):
                    continue
                occurred_at = datetime.fromtimestamp(os.stat(record.source_file).st_mtime, UTC)
                if storage_service.last_event_time(database_id, node_ids[record.current_name], tx) != occurred_at:
                    modified.append(storage_service.NodeEvent(node_ids[record.current_name], "modified", occurred_at))
            storage_service.append_node_events(database_id, modified, tx)

            # Chủ đề 3: schema cột từ DDL nguồn (declared) + lan qua cạnh direct
            # (propagated). Chạy vô điều kiện như upsert_nodes — declare không phụ
            # thuộc graph_changed. mapping rỗng => no-op, không xoá schema cũ.
            storage_service.replace_column_schema(database_id, declared_columns, tx)
            storage_service.replace_propagated_column_schema(
                database_id, _propagate_column_schema(working, declared_columns), tx
            )

            if graph_changed:
                storage_service.save(database_id, working, tx)
            storage_service.sync_breaking_change_alerts(database_id, breaking_changes, tx)
        graph_service.replace_graph(database_id, working)

    cycle_detected = graph_service.has_cycle(database_id)

    logger.info(
        "graph_build_node: applied %d rename(s), %d drop(s), %d breaking-change alert(s)",
        rename_count,
        drop_count,
        len(breaking_changes),
    )

    res: dict = {
        "cycle_detected": cycle_detected,
        "breaking_changes_detected": len(breaking_changes),
    }
    if cycle_detected:
        res["error"] = "Phát hiện chu trình (cycle) trong đồ thị lineage sau khi ghi nhận các cạnh mới!"
    return res


def describe_node(state: LineageAgentState) -> dict:
    """Generate table descriptions after graph persistence, outside database locks."""
    if not get_settings().description_enabled:
        return {"descriptions_written": 0, "descriptions_pending": 0}

    database_id = state["database_id"]
    nodes = storage_service.load_live_nodes_for_description(database_id)
    snapshot = {
        node.node_id: (node.description.source, node.description.evidence_hash) if node.description else (None, None)
        for node in nodes
    }
    neighbours = {node.record.current_name: node.record for node in nodes}
    pending_by_id = {item.node_id: item for item in description_review_service.list_pending(database_id)}
    payloads: dict[int, dict[str, object]] = {}
    hashes: dict[int, str] = {}
    stale_expected: dict[int, str] = {}
    proposal_context: dict[int, tuple[bool, str | None]] = {}

    for node in nodes:
        payload = description_service.build_evidence_payload(node, neighbours)
        current_hash = description_service.evidence_hash(payload)
        hashes[node.node_id] = current_hash
        existing = node.description
        pending = pending_by_id.get(node.node_id)
        if existing is None:
            if pending is not None and pending.evidence_hash == current_hash:
                continue
        elif existing.source == "llm" and existing.evidence_hash == current_hash:
            continue
        elif existing.source == "human":
            if existing.evidence_hash == current_hash:
                continue
            if pending is not None and pending.evidence_hash == current_hash:
                continue
            stale_expected[node.node_id] = existing.evidence_hash
            proposal_context[node.node_id] = (True, existing.description)

        prompt_payload = dict(payload)
        if node.record.defined_in:
            try:
                prompt_payload["ddl"] = (Path(state["input_path"]) / node.record.defined_in).read_text(encoding="utf-8")
            except OSError:
                logger.warning("Unable to read DDL for description: %s", node.record.defined_in)
        payloads[node.node_id] = prompt_payload

    generated = description_service.describe_tables({str(node_id): payload for node_id, payload in payloads.items()})
    threshold = get_settings().description_confidence_threshold
    records: list[storage_service.DescriptionRecord] = []
    pending_items: list[PendingDescription] = []
    for node_id_text, raw in generated.items():
        node_id = int(node_id_text)
        confidence = description_service.resolve_confidence(raw.label)
        source, base_hash = snapshot[node_id]
        node = next(node for node in nodes if node.node_id == node_id)
        if confidence < threshold or node_id in stale_expected:
            stale, current_description = proposal_context.get(node_id, (False, None))
            pending_items.append(
                PendingDescription(
                    node_id=node_id,
                    table=node.record.current_name,
                    description=raw.description,
                    label=raw.label,
                    confidence=confidence,
                    evidence_hash=hashes[node_id],
                    created_at=datetime.now(UTC),
                    base_source=source,
                    base_hash=base_hash,
                    is_stale_proposal=stale,
                    current_description=current_description,
                )
            )
        else:
            records.append(
                storage_service.DescriptionRecord(
                    node_id=node_id,
                    description=raw.description,
                    source="llm",
                    label=raw.label,
                    confidence=confidence,
                    evidence_hash=hashes[node_id],
                    is_stale=False,
                )
            )

    embeddings = embedding_service.embed([record.description for record in records]) if records else []
    embedding_by_id = {record.node_id: vector for record, vector in zip(records, embeddings, strict=False)}
    stale_generated = [item.node_id for item in pending_items if item.is_stale_proposal]
    written: list[int] = []
    if records or stale_generated:
        with storage_service.transaction() as tx:
            written = storage_service.upsert_llm_descriptions(
                database_id, records, embedding_by_id, {node_id: hash_ for node_id, (_, hash_) in snapshot.items()}, tx
            )
            storage_service.mark_descriptions_stale(database_id, stale_generated, stale_expected, tx)
    for node_id in written:
        description_review_service.pop_pending(database_id, str(node_id))
    description_review_service.add_pending(database_id, pending_items)
    return {"descriptions_written": len(written), "descriptions_pending": len(pending_items)}


def describe_columns_node(state: LineageAgentState) -> dict:
    """Generate column-level descriptions, sau khi table description đã chạy.

    Cùng vòng đời HITL/CAS như describe_node, chỉ khác khoá là (node_id,
    column) vì 1 bảng có nhiều cột. Evidence của 1 cột chỉ dựa trên cạnh đã
    CONFIRMED, hop đầu tiên chạm đúng column đó (xem
    description_service.build_column_evidence_payload) — không mô tả cột
    dựa trên suy luận LLM (pending) chưa qua HITL. Mô tả cho mọi cột trong
    columns_produced (cột do CHÍNH bảng này sinh ra) — columns_consumed là
    tên cột ở bảng nguồn, không phải cột của bảng đang xét.
    """
    if not get_settings().description_enabled:
        return {"column_descriptions_written": 0, "column_descriptions_pending": 0}

    database_id = state["database_id"]
    nodes = storage_service.load_live_nodes_for_description(database_id)
    node_by_id = {node.node_id: node for node in nodes}
    existing_by_key = storage_service.load_column_descriptions(database_id, [node.node_id for node in nodes])
    pending_by_key = {
        (item.node_id, item.column): item for item in column_description_review_service.list_pending(database_id)
    }

    snapshot: dict[tuple[int, str], tuple[str | None, str | None]] = {}
    payloads: dict[str, dict[str, object]] = {}
    hashes: dict[tuple[int, str], str] = {}
    stale_expected: dict[tuple[int, str], str] = {}
    proposal_context: dict[tuple[int, str], tuple[bool, str | None]] = {}
    ddl_cache: dict[int, str | None] = {}

    for node in nodes:
        for column in node.record.columns_produced:
            key = (node.node_id, column)
            payload = description_service.build_column_evidence_payload(database_id, node.record.current_name, column)
            current_hash = description_service.evidence_hash(payload)
            hashes[key] = current_hash
            existing = existing_by_key.get(key)
            snapshot[key] = (existing.source, existing.evidence_hash) if existing else (None, None)
            pending = pending_by_key.get(key)
            if existing is None:
                if pending is not None and pending.evidence_hash == current_hash:
                    continue
            elif existing.source == "llm" and existing.evidence_hash == current_hash:
                continue
            elif existing.source == "human":
                if existing.evidence_hash == current_hash:
                    continue
                if pending is not None and pending.evidence_hash == current_hash:
                    continue
                stale_expected[key] = existing.evidence_hash
                proposal_context[key] = (True, existing.description)

            prompt_payload = dict(payload)
            if node.node_id not in ddl_cache:
                ddl_cache[node.node_id] = None
                if node.record.defined_in:
                    try:
                        ddl_cache[node.node_id] = (Path(state["input_path"]) / node.record.defined_in).read_text(
                            encoding="utf-8"
                        )
                    except OSError:
                        logger.warning("Unable to read DDL for column description: %s", node.record.defined_in)
            if ddl_cache[node.node_id]:
                prompt_payload["ddl"] = ddl_cache[node.node_id]
            payloads[f"{node.node_id}:{column}"] = prompt_payload

    generated = description_service.describe_columns(payloads)
    threshold = get_settings().description_confidence_threshold
    records: list[storage_service.ColumnDescriptionRecord] = []
    pending_items: list[PendingColumnDescription] = []
    for combined_key, raw in generated.items():
        node_id_text, column = combined_key.split(":", 1)
        node_id = int(node_id_text)
        key = (node_id, column)
        confidence = description_service.resolve_confidence(raw.label)
        source, base_hash = snapshot[key]
        table_name = node_by_id[node_id].record.current_name
        if confidence < threshold or key in stale_expected:
            stale, current_description = proposal_context.get(key, (False, None))
            pending_items.append(
                PendingColumnDescription(
                    node_id=node_id,
                    table=table_name,
                    column=column,
                    description=raw.description,
                    label=raw.label,
                    confidence=confidence,
                    evidence_hash=hashes[key],
                    created_at=datetime.now(UTC),
                    base_source=source,
                    base_hash=base_hash,
                    is_stale_proposal=stale,
                    current_description=current_description,
                )
            )
        else:
            records.append(
                storage_service.ColumnDescriptionRecord(
                    node_id=node_id,
                    column_name=column,
                    description=raw.description,
                    source="llm",
                    label=raw.label,
                    confidence=confidence,
                    evidence_hash=hashes[key],
                    is_stale=False,
                )
            )

    embeddings = embedding_service.embed([record.description for record in records]) if records else []
    embedding_by_key = {
        (record.node_id, record.column_name): vector for record, vector in zip(records, embeddings, strict=False)
    }
    stale_generated = [(item.node_id, item.column) for item in pending_items if item.is_stale_proposal]
    written: list[tuple[int, str]] = []
    if records or stale_generated:
        with storage_service.transaction() as tx:
            written = storage_service.upsert_llm_column_descriptions(
                database_id, records, embedding_by_key, {key: hash_ for key, (_, hash_) in snapshot.items()}, tx
            )
            storage_service.mark_column_descriptions_stale(database_id, stale_generated, stale_expected, tx)
    for node_id, column in written:
        column_description_review_service.pop_pending(database_id, node_id, column)
    column_description_review_service.add_pending(database_id, pending_items)
    return {"column_descriptions_written": len(written), "column_descriptions_pending": len(pending_items)}


def embed_sql_node(state: LineageAgentState) -> dict:
    """RAG trên nội dung SQL: embed lại các chunk MỚI/ĐỔI so với lần ingest
    trước, cho chat agent tìm kiếm ngữ nghĩa trực tiếp trên văn bản SQL qua
    tool search_sql_content. Gate bởi settings.description_enabled bên trong
    sql_document_service.sync_sql_documents — no-op khi tắt, giống describe_node."""
    written = sql_document_service.sync_sql_documents(state["database_id"], state.get("sql_files", []))
    return {"sql_documents_written": written}
