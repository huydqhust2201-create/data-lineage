"""RAG trên nội dung SQL đã ingest — cho phép chat agent tìm kiếm ngữ nghĩa
trực tiếp trên văn bản SQL (không chỉ trên lineage edge/mô tả đã suy luận).

Chunk theo đúng ranh giới statement mà parser_service đã tách sẵn (dùng lại
sqlglot.parse() y hệt cách parser tách file thành statement) — file 1
statement (trường hợp phổ biến của model dbt: 1 SELECT, có thể nhiều CTE)
tự nhiên cho ra đúng 1 chunk = nguyên văn cả file; file nhiều statement (vd
migration script nhiều CREATE/ALTER/DROP) tách riêng từng statement, tránh
nhét nhiều khái niệm không liên quan vào 1 vector embedding.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from sqlglot import parse as sqlglot_parse
from sqlglot.errors import SqlglotError

from src.config import get_settings
from src.services import embedding_service, storage_service
from src.services.parser_service import preprocess_dbt_jinja

logger = logging.getLogger(__name__)


def _split_statements(file_path: str, dialect: str) -> list[tuple[int, str]]:
    """Trả về [(order, statement_sql_text)] — KHÔNG cắt ngắn (khác
    StatementPreview.sql của ddl_preview_service vốn cắt 200 ký tự chỉ để
    hiển thị). Bỏ qua file không đọc được/không parse được, không raise —
    1 file lỗi không được làm hỏng cả lượt embed các file khác."""
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("sql_document_service: không đọc được file %s: %s", file_path, exc)
        return []

    content = preprocess_dbt_jinja(content)

    try:
        statements = [s for s in sqlglot_parse(content, read=dialect) if s is not None]
    except (SqlglotError, Exception) as exc:
        logger.warning("sql_document_service: không parse được %s: %s", file_path, exc)
        return []

    result: list[tuple[int, str]] = []
    for order, statement in enumerate(statements):
        text = statement.sql(dialect=dialect)
        if text.strip():
            result.append((order, text))
    return result


def sync_sql_documents(database_id: int, sql_files: list[str]) -> int:
    """Embed lại các chunk SQL MỚI/ĐỔI so với lần ingest trước — bỏ qua chunk
    có content_hash không đổi (giống cơ chế evidence_hash của describe_node,
    tránh gọi embedding lại cho SQL không thay đổi). Trả về số chunk đã ghi.

    Gate bởi settings.description_enabled — cùng công tắc bật/tắt cả cụm RAG
    hiện có (bảng/cột), vì cùng phụ thuộc TEI/BGE-M3, không thêm flag riêng."""
    settings = get_settings()
    if not settings.description_enabled:
        return 0

    written = 0
    for file_path in sql_files:
        for order, text in _split_statements(file_path, settings.sql_dialect):
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if storage_service.get_sql_document_hash(database_id, file_path, order) == content_hash:
                continue

            vectors = embedding_service.embed([text])
            if not vectors:
                logger.warning("sql_document_service: embedding không khả dụng, bỏ qua %s#%s", file_path, order)
                continue

            table_name = Path(file_path).stem
            storage_service.upsert_sql_document(database_id, file_path, order, table_name, text, content_hash, vectors[0])
            written += 1
    return written
