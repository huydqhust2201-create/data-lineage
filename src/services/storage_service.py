import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import networkx as nx
import psycopg2
import psycopg2.extras

from src.config import get_settings

# Owner: Lê Huy Hoàng (PRD.md mục 11)
# Lưu đồ thị lineage vào Postgres (bảng lineage_edges) thay vì file GraphML —
# để dữ liệu sống sót qua restart và nhất quán giữa nhiều worker process
# (trước đây _graph trong graph_service.py chỉ nằm trong RAM của 1 process,
# nên nhiều worker sẽ thấy dữ liệu khác nhau).
#
# Model: 1 dòng = 1 cạnh trong MultiDiGraph. save() ghi đè toàn bộ (snapshot),
# giống cách GraphML cũ hoạt động — không phải incremental upsert. Node đơn lẻ
# không có cạnh nào sẽ không được lưu riêng; graph_service hiện không tạo node
# kiểu đó nên chưa phải vấn đề thực tế.
#
# add_edge() trong graph_service.py CHƯA gọi save() sau khi mutate — persistence
# ở đây mới là "cơ chế", chưa được nối vào write path. Ai nối API /ingest thật
# cần tự gọi storage_service.save(graph) sau khi ghi xong 1 batch.

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage_edges (
    id SERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL REFERENCES databases(id) ON DELETE CASCADE,
    source_table TEXT NOT NULL,
    source_column TEXT,
    target_table TEXT NOT NULL,
    target_column TEXT,
    transform_type TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    source_type TEXT NOT NULL,
    evidence JSONB,
    dependency_kind TEXT NOT NULL DEFAULT 'output'
);
-- Migration cho DB đã deploy trước khi có control lineage: nếu không round-trip
-- dependency_kind thì mọi cạnh control (join_key/group_key/filter/window_*) khi
-- load lại sẽ thành "output", khiến add_edge KHÔNG dedup được và nhân bản cạnh
-- mỗi lần re-ingest (risk note lặp lại trên UI).
ALTER TABLE lineage_edges ADD COLUMN IF NOT EXISTS dependency_kind TEXT NOT NULL DEFAULT 'output';
"""
_USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
# Migration cộng thêm (ALTER TABLE) — password_hash/google_sub thêm sau khi bảng
# users đã tồn tại từ trước ở các DB đã deploy. Cả 2 cột đều nullable: tài khoản
# chỉ-Google không có password_hash, tài khoản chỉ-mật-khẩu không có google_sub.
# Dùng partial unique index thay vì UNIQUE trên cột — idempotent an toàn qua
# nhiều lần chạy và NULL không đụng nhau giữa các tài khoản khác loại.
_AUTH_COLUMNS_SCHEMA = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub_key ON users (google_sub) WHERE google_sub IS NOT NULL;
"""
_DATABASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS databases (
    id BIGSERIAL PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_id, name)
);

CREATE TABLE IF NOT EXISTS database_members (
    database_id BIGINT NOT NULL REFERENCES databases(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('engineer', 'viewer')),
    PRIMARY KEY (database_id, user_id)
);
"""

# Lịch sử ingest — chỉ là LOG, không đổi cách dữ liệu gộp vào graph (vẫn cộng
# dồn theo database_id như trước). Giải quyết nhu cầu "database không nhất
# thiết nằm trong 1 file — nhiều lượt ingest bổ sung dần" cần xem lại lượt
# nào từ path nào ra bao nhiêu cạnh, tách theo project/database.
_INGEST_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingest_runs (
    id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL REFERENCES databases(id) ON DELETE CASCADE,
    input_path TEXT NOT NULL,
    sql_files_found INT NOT NULL,
    parsed_count INT NOT NULL,
    unparsed_count INT NOT NULL,
    pending_review_count INT NOT NULL,
    triggered_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ingest_runs_database_time
    ON ingest_runs (database_id, started_at DESC);
"""

# Cảnh báo breaking change — ghi tự động trong graph_build_node khi 1 bảng bị
# DROP/RENAME nhưng vẫn còn bảng downstream tham chiếu (phát hiện TRƯỚC khi
# áp dụng thay đổi, so trên đồ thị working còn nguyên vẹn — xem
# lineage_nodes.graph_build_node). Không cần user tự paste DDL vào DDL
# preview mới biết — tự phát hiện ngay lúc ingest.
_BREAKING_CHANGE_ALERTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS breaking_change_alerts (
    id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL REFERENCES databases(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('drop', 'rename')),
    table_name TEXT NOT NULL,
    new_name TEXT,
    downstream_tables JSONB NOT NULL,
    suggested_action TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged BOOLEAN NOT NULL DEFAULT FALSE
);
ALTER TABLE breaking_change_alerts ADD COLUMN IF NOT EXISTS acknowledged BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE breaking_change_alerts DROP COLUMN IF EXISTS resolved_at;

CREATE UNIQUE INDEX IF NOT EXISTS breaking_change_alerts_identity
    ON breaking_change_alerts (database_id, kind, table_name, COALESCE(new_name, ''));

CREATE INDEX IF NOT EXISTS breaking_change_alerts_database_time
    ON breaking_change_alerts (database_id, detected_at DESC);
"""

# Session hội thoại chat — 1 luồng liên tục / (database_id, user_id), giống
# cách Claude Code lưu conversation: định danh theo user thật (không phải
# UUID ngẫu nhiên per-conversation) nên không có khái niệm "session_id lạ với
# worker này" — mọi worker/process đều nhìn thấy đúng 1 luồng của user đó
# trong Postgres. chat_turns là APPEND-ONLY (mỗi lượt 1 dòng INSERT thuần,
# không đọc-sửa-ghi cả mảng) — giống transcript JSONL append-only của Claude
# Code, khác hẳn thiết kế JSONB-blob-overwrite trước đó.
_CHAT_SESSIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    database_id BIGINT NOT NULL REFERENCES databases(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pending_clarification JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (database_id, user_id)
);

CREATE TABLE IF NOT EXISTS chat_turns (
    id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    question TEXT NOT NULL,
    resolved_table TEXT,
    answer TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (database_id, user_id) REFERENCES chat_sessions (database_id, user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS chat_turns_session_time
    ON chat_turns (database_id, user_id, created_at DESC);
"""

# RAG trên nội dung SQL đã ingest — cùng pattern _DESCRIPTION_SCHEMA (BGE-M3 +
# pgvector HNSW), khác đối tượng: embed thẳng văn bản SQL (không phải mô tả
# do LLM sinh ra), cho chat agent tìm kiếm ngữ nghĩa trên logic SQL thật.
# statement_order tách theo ranh giới statement mà parser_service đã tách sẵn
# — file 1 statement (model dbt thông thường) tự nhiên = 1 dòng = cả file.
_SQL_DOCUMENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage_sql_documents (
    id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL REFERENCES databases(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    statement_order INT NOT NULL,
    table_name TEXT,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding vector(1024),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (database_id, file_path, statement_order)
);

CREATE INDEX IF NOT EXISTS lineage_sql_documents_hnsw
    ON lineage_sql_documents USING hnsw (embedding vector_cosine_ops);
"""

GRAPH_LOCK_KEY = 116

_NODE_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage_nodes (
    id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL REFERENCES databases(id) ON DELETE CASCADE,
    current_name TEXT NOT NULL,
    defined_in TEXT,
    columns_produced JSONB,
    columns_consumed JSONB,
    upstream_tables JSONB,
    downstream_tables JSONB,
    source_types JSONB,
    transform_types JSONB,
    confidence_min DOUBLE PRECISION,
    confidence_max DOUBLE PRECISION,
    dropped_at TIMESTAMPTZ,
    UNIQUE (database_id, current_name),
    UNIQUE (database_id, id)
);

CREATE TABLE IF NOT EXISTS lineage_node_events (
    id BIGSERIAL PRIMARY KEY,
    database_id BIGINT NOT NULL,
    node_id BIGINT NOT NULL,
    kind TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    details JSONB,
    FOREIGN KEY (database_id, node_id) REFERENCES lineage_nodes (database_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS lineage_node_events_node_time
    ON lineage_node_events (node_id, occurred_at DESC);
"""

_DESCRIPTION_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS lineage_node_descriptions (
    database_id BIGINT NOT NULL,
    node_id BIGINT NOT NULL,
    description TEXT NOT NULL,
    source TEXT NOT NULL,
    label TEXT,
    confidence DOUBLE PRECISION,
    evidence_hash TEXT NOT NULL,
    is_stale BOOLEAN NOT NULL DEFAULT FALSE,
    embedding vector(1024),
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (database_id, node_id),
    FOREIGN KEY (database_id, node_id) REFERENCES lineage_nodes (database_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS lineage_node_descriptions_hnsw
    ON lineage_node_descriptions USING hnsw (embedding vector_cosine_ops);
"""

# Bảng riêng cho mô tả CỘT (không gộp vào lineage_node_descriptions, PK ở đó
# là node_id đơn — 1 dòng/bảng). Cùng vòng đời HITL (LLM đề xuất -> pending
# nếu confidence thấp hoặc evidence đổi -> confirm/reject/human override) và
# cùng cơ chế CAS chống ghi đè như mô tả bảng, chỉ khác khoá là (node_id,
# column_name) vì 1 bảng có nhiều cột.
_COLUMN_DESCRIPTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage_column_descriptions (
    database_id BIGINT NOT NULL,
    node_id BIGINT NOT NULL,
    column_name TEXT NOT NULL,
    description TEXT NOT NULL,
    source TEXT NOT NULL,
    label TEXT,
    confidence DOUBLE PRECISION,
    evidence_hash TEXT NOT NULL,
    is_stale BOOLEAN NOT NULL DEFAULT FALSE,
    embedding vector(1024),
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (database_id, node_id, column_name),
    FOREIGN KEY (database_id, node_id) REFERENCES lineage_nodes (database_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS lineage_column_descriptions_hnsw
    ON lineage_column_descriptions USING hnsw (embedding vector_cosine_ops);
"""

# Kiểu dữ liệu + constraint mỗi cột (Chủ đề 3). Bảng RIÊNG, khoá theo tên bảng
# (không phải node_id) — write path trong graph_build_node đã có sẵn tên bảng từ
# event `declare`, không cần resolve node_id; /graph và impact cũng tra theo tên.
# KHÔNG đụng lineage_nodes để không kéo theo 8+ chỗ upsert/load của nó.
# origin: 'declared' (từ DDL) | 'propagated' (suy qua cạnh direct).
_COLUMN_SCHEMA_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage_column_schema (
    database_id BIGINT NOT NULL REFERENCES databases(id) ON DELETE CASCADE,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    ordinal INT NOT NULL DEFAULT 0,
    data_type TEXT,
    is_nullable BOOLEAN NOT NULL DEFAULT TRUE,
    is_primary_key BOOLEAN NOT NULL DEFAULT FALSE,
    is_foreign_key BOOLEAN NOT NULL DEFAULT FALSE,
    references_table TEXT,
    references_column TEXT,
    origin TEXT NOT NULL DEFAULT 'declared',
    PRIMARY KEY (database_id, table_name, column_name)
);
"""


@dataclass
class NodeRecord:
    current_name: str
    defined_in: str | None
    source_file: str | None
    columns_produced: list[str]
    columns_consumed: list[str]
    upstream_tables: list[str]
    downstream_tables: list[str]
    source_types: list[str]
    transform_types: list[str]
    confidence_min: float | None
    confidence_max: float | None


@dataclass
class NodeProfile:
    """A node plus lifecycle aggregates used by the read-only asset capability."""

    node_id: int
    current_name: str
    defined_in: str | None
    columns_produced: list[str]
    columns_consumed: list[str]
    upstream_tables: list[str]
    downstream_tables: list[str]
    source_types: list[str]
    transform_types: list[str]
    confidence_min: float | None
    confidence_max: float | None
    dropped_at: datetime | None
    first_seen: datetime | None
    last_modified: datetime | None
    modified_count: int
    previous_names: list[tuple[str, datetime]]


@dataclass
class NodeEvent:
    node_id: int
    kind: Literal["modified", "rename", "drop", "recreated"]
    occurred_at: datetime
    details: dict | None = None


@dataclass
class DescriptionRecord:
    node_id: int
    description: str
    source: Literal["llm", "human"]
    label: str | None
    confidence: float | None
    evidence_hash: str
    is_stale: bool


@dataclass
class DescriptionNode:
    node_id: int
    record: NodeRecord
    description: DescriptionRecord | None
    last_modified: datetime | None


@dataclass
class ColumnDescriptionRecord:
    node_id: int
    column_name: str
    description: str
    source: Literal["llm", "human"]
    label: str | None
    confidence: float | None
    evidence_hash: str
    is_stale: bool


@dataclass(frozen=True)
class UserRecord:
    id: int
    email: str
    display_name: str | None
    password_hash: str | None
    google_sub: str | None


@dataclass(frozen=True)
class DatabaseRecord:
    id: int
    owner_id: int
    name: str
    created_at: datetime


@dataclass(frozen=True)
class MemberRecord:
    user_id: int
    email: str
    display_name: str | None
    role: Literal["engineer", "viewer"]


def _connect() -> psycopg2.extensions.connection:
    """Seam để test monkeypatch sang DB khác nếu cần (giống _get_extraction_llm)."""
    conn = psycopg2.connect(get_settings().database_url)
    with conn.cursor() as cur:
        # _USER_SCHEMA/_DATABASE_SCHEMA phải chạy trước — _SCHEMA và _NODE_SCHEMA
        # tham chiếu FK tới databases(id), tạo sau sẽ lỗi UndefinedTable trên 1 DB
        # hoàn toàn mới (chỉ "vô hại" trên DB đã có sẵn bảng databases từ trước).
        cur.execute(_USER_SCHEMA)
        cur.execute(_AUTH_COLUMNS_SCHEMA)
        cur.execute(_DATABASE_SCHEMA)
        cur.execute(_SCHEMA)
        cur.execute(_NODE_SCHEMA)
        cur.execute(_DESCRIPTION_SCHEMA)
        cur.execute(_COLUMN_DESCRIPTION_SCHEMA)
        cur.execute(_COLUMN_SCHEMA_SCHEMA)
        cur.execute(_INGEST_RUNS_SCHEMA)
        cur.execute(_BREAKING_CHANGE_ALERTS_SCHEMA)
        cur.execute(_CHAT_SESSIONS_SCHEMA)
        cur.execute(_SQL_DOCUMENTS_SCHEMA)
    conn.commit()
    return conn


def ping() -> bool:
    """Kiểm tra Postgres còn kết nối được — dùng cho health check (GET /status),
    KHÔNG gọi qua _connect() vì hàm đó chạy lại toàn bộ schema bootstrap
    (nhiều CREATE TABLE/ALTER TABLE) mỗi lần, quá nặng cho 1 lượt ping."""
    try:
        conn = psycopg2.connect(get_settings().database_url, connect_timeout=2)
    except psycopg2.OperationalError:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except psycopg2.Error:
        return False
    finally:
        conn.close()


_USER_COLUMNS = "id, email, display_name, password_hash, google_sub"


def _user_record(row: tuple) -> UserRecord:
    return UserRecord(id=row[0], email=row[1], display_name=row[2], password_hash=row[3], google_sub=row[4])


def get_user_by_id(user_id: int) -> UserRecord | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        return _user_record(row) if row is not None else None
    finally:
        conn.close()


def get_user_by_email(email: str) -> UserRecord | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
        return _user_record(row) if row is not None else None
    finally:
        conn.close()


def get_user_by_google_sub(google_sub: str) -> UserRecord | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE google_sub = %s", (google_sub,))
            row = cur.fetchone()
        return _user_record(row) if row is not None else None
    finally:
        conn.close()


def list_users() -> list[UserRecord]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_USER_COLUMNS} FROM users ORDER BY id")
            return [_user_record(row) for row in cur.fetchall()]
    finally:
        conn.close()


def upsert_user(email: str, display_name: str | None) -> UserRecord:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO users (email, display_name)
                VALUES (%s, %s)
                ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
                RETURNING {_USER_COLUMNS}
                """,
                (email, display_name),
            )
            row = cur.fetchone()
        conn.commit()
        return _user_record(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_user_with_password(email: str, display_name: str | None, password_hash: str) -> UserRecord | None:
    """Đăng ký tài khoản mới. Trả None nếu email đã tồn tại — KHÔNG dùng
    ON CONFLICT DO UPDATE như upsert_user, tránh cho phép "đăng ký" ghi đè
    mật khẩu của một tài khoản đã có."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO users (email, display_name, password_hash)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                RETURNING {_USER_COLUMNS}
                """,
                (email, display_name, password_hash),
            )
            row = cur.fetchone()
        conn.commit()
        return _user_record(row) if row is not None else None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_user_password(user_id: int, password_hash: str) -> UserRecord:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE users SET password_hash = %s WHERE id = %s RETURNING {_USER_COLUMNS}",
                (password_hash, user_id),
            )
            row = cur.fetchone()
        conn.commit()
        return _user_record(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def link_google_account(user_id: int, google_sub: str) -> UserRecord:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE users SET google_sub = %s WHERE id = %s RETURNING {_USER_COLUMNS}",
                (google_sub, user_id),
            )
            row = cur.fetchone()
        conn.commit()
        return _user_record(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _database_record(row: tuple) -> DatabaseRecord:
    return DatabaseRecord(id=row[0], owner_id=row[1], name=row[2], created_at=row[3])


def get_database_by_id(database_id: int) -> DatabaseRecord | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, owner_id, name, created_at FROM databases WHERE id = %s", (database_id,))
            row = cur.fetchone()
        return _database_record(row) if row is not None else None
    finally:
        conn.close()


def get_database_by_owner_and_name(owner_id: int, name: str) -> DatabaseRecord | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, owner_id, name, created_at FROM databases WHERE owner_id = %s AND name = %s",
                (owner_id, name),
            )
            row = cur.fetchone()
        return _database_record(row) if row is not None else None
    finally:
        conn.close()


def create_database(owner_id: int, name: str) -> DatabaseRecord | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO databases (owner_id, name) VALUES (%s, %s)
                ON CONFLICT (owner_id, name) DO NOTHING
                RETURNING id, owner_id, name, created_at
                """,
                (owner_id, name),
            )
            row = cur.fetchone()
        conn.commit()
        return _database_record(row) if row is not None else None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_databases_for_user(user_id: int) -> list[tuple[DatabaseRecord, Literal["engineer", "viewer"]]]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.id, d.owner_id, d.name, d.created_at,
                       CASE WHEN d.owner_id = %s THEN 'engineer' ELSE dm.role END
                FROM databases d
                LEFT JOIN database_members dm ON dm.database_id = d.id AND dm.user_id = %s
                WHERE d.owner_id = %s OR dm.user_id IS NOT NULL
                ORDER BY d.id
                """,
                (user_id, user_id, user_id),
            )
            rows = cur.fetchall()
        return [(_database_record(row[:4]), row[4]) for row in rows]
    finally:
        conn.close()


def get_member_role(database_id: int, user_id: int) -> Literal["engineer", "viewer"] | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role FROM database_members WHERE database_id = %s AND user_id = %s",
                (database_id, user_id),
            )
            row = cur.fetchone()
        return row[0] if row is not None else None
    finally:
        conn.close()


def list_database_members(database_id: int) -> list[MemberRecord]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.email, u.display_name, dm.role
                FROM database_members dm JOIN users u ON u.id = dm.user_id
                WHERE dm.database_id = %s ORDER BY u.id
                """,
                (database_id,),
            )
            rows = cur.fetchall()
        return [MemberRecord(user_id=row[0], email=row[1], display_name=row[2], role=row[3]) for row in rows]
    finally:
        conn.close()


def upsert_database_member(database_id: int, user_id: int, role: Literal["engineer", "viewer"]) -> MemberRecord:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO database_members (database_id, user_id, role) VALUES (%s, %s, %s)
                ON CONFLICT (database_id, user_id) DO UPDATE SET role = EXCLUDED.role
                RETURNING user_id, role
                """,
                (database_id, user_id, role),
            )
            member_row = cur.fetchone()
            cur.execute("SELECT email, display_name FROM users WHERE id = %s", (user_id,))
            user_row = cur.fetchone()
        conn.commit()
        return MemberRecord(user_id=member_row[0], email=user_row[0], display_name=user_row[1], role=member_row[1])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_database_member(database_id: int, user_id: int) -> bool:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM database_members WHERE database_id = %s AND user_id = %s", (database_id, user_id))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[psycopg2.extensions.connection]:
    """Một transaction dùng chung cho graph snapshot và metadata node."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def advisory_lock(tx: psycopg2.extensions.connection, key: int = GRAPH_LOCK_KEY) -> None:
    """Khóa transaction-scoped của Postgres để tuần tự hóa graph writers."""
    with tx.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (key,))


def _commit_if_owned(conn: psycopg2.extensions.connection, tx: psycopg2.extensions.connection | None) -> None:
    if tx is None:
        conn.commit()


def _close_if_owned(conn: psycopg2.extensions.connection, tx: psycopg2.extensions.connection | None) -> None:
    if tx is None:
        conn.close()


def save(database_id: int, graph: nx.MultiDiGraph, tx: psycopg2.extensions.connection | None = None) -> None:
    """Ghi đè toàn bộ đồ thị lineage hiện tại xuống Postgres."""
    rows = [
        (
            database_id,
            u,
            attrs.get("source_column"),
            v,
            attrs.get("target_column"),
            attrs.get("transform_type", "unknown"),
            float(attrs.get("confidence", 1.0)),
            attrs.get("source_type", "parser"),
            psycopg2.extras.Json(attrs["evidence"]) if attrs.get("evidence") is not None else None,
            attrs.get("dependency_kind", "output"),
        )
        for u, v, attrs in graph.edges(data=True)
    ]
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lineage_edges WHERE database_id = %s", (database_id,))
            if rows:
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO lineage_edges "
                    "(database_id, source_table, source_column, target_table, target_column, "
                    "transform_type, confidence, source_type, evidence, dependency_kind) VALUES %s",
                    rows,
                )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def load(database_id: int, tx: psycopg2.extensions.connection | None = None) -> nx.MultiDiGraph:
    """Đọc lại đồ thị lineage từ Postgres. Trả về đồ thị rỗng nếu bảng chưa có dữ liệu."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_table, source_column, target_table, target_column, "
                "transform_type, confidence, source_type, evidence, dependency_kind "
                "FROM lineage_edges WHERE database_id = %s",
                (database_id,),
            )
            rows = cur.fetchall()
    finally:
        _close_if_owned(conn, tx)

    graph = nx.MultiDiGraph()
    # Gộp cạnh trùng lặp ngay lúc load — cùng contract dedup với
    # graph_service.add_edge: (src, tgt, source_column, target_column,
    # source_type, dependency_kind). DB cũ có thể chứa cạnh nhân bản từ trước
    # khi round-trip dependency_kind; tự lành ở lần load này, giữ bản confidence
    # cao nhất.
    seen: dict[tuple, tuple] = {}
    for (
        source_table,
        source_column,
        target_table,
        target_column,
        transform_type,
        confidence,
        source_type,
        evidence,
        dependency_kind,
    ) in rows:
        dependency_kind = dependency_kind or "output"
        key = (source_table, target_table, source_column, target_column, source_type, dependency_kind)
        prev = seen.get(key)
        if prev is not None and float(prev[5]) >= float(confidence):
            continue
        seen[key] = (
            source_table, source_column, target_table, target_column,
            transform_type, confidence, source_type, evidence, dependency_kind,
        )

    for (
        source_table,
        source_column,
        target_table,
        target_column,
        transform_type,
        confidence,
        source_type,
        evidence,
        dependency_kind,
    ) in seen.values():
        attrs = {
            "transform_type": transform_type,
            "confidence": confidence,
            "source_type": source_type,
        }
        if dependency_kind != "output":
            attrs["dependency_kind"] = dependency_kind
        if source_column is not None:
            attrs["source_column"] = source_column
        if target_column is not None:
            attrs["target_column"] = target_column
        if evidence is not None:
            attrs["evidence"] = evidence  # psycopg2 tự parse JSONB -> dict
        graph.add_edge(source_table, target_table, **attrs)
    return graph


def upsert_nodes(database_id: int, nodes: list[NodeRecord], tx: psycopg2.extensions.connection | None = None) -> dict[str, int]:
    """Ghi nhóm metadata dẫn xuất và trả map tên hiện tại sang id ổn định."""
    if not nodes:
        return {}

    rows = [
        (
            database_id, node.current_name,
            node.defined_in,
            psycopg2.extras.Json(node.columns_produced),
            psycopg2.extras.Json(node.columns_consumed),
            psycopg2.extras.Json(node.upstream_tables),
            psycopg2.extras.Json(node.downstream_tables),
            psycopg2.extras.Json(node.source_types),
            psycopg2.extras.Json(node.transform_types),
            node.confidence_min,
            node.confidence_max,
        )
        for node in nodes
    ]
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO lineage_nodes ("
                "database_id, current_name, defined_in, columns_produced, columns_consumed, "
                "upstream_tables, downstream_tables, source_types, transform_types, "
                "confidence_min, confidence_max"
                ") VALUES %s "
                "ON CONFLICT (database_id, current_name) DO UPDATE SET "
                "defined_in = EXCLUDED.defined_in, "
                "columns_produced = EXCLUDED.columns_produced, "
                "columns_consumed = EXCLUDED.columns_consumed, "
                "upstream_tables = EXCLUDED.upstream_tables, "
                "downstream_tables = EXCLUDED.downstream_tables, "
                "source_types = EXCLUDED.source_types, "
                "transform_types = EXCLUDED.transform_types, "
                "confidence_min = EXCLUDED.confidence_min, "
                "confidence_max = EXCLUDED.confidence_max "
                "RETURNING current_name, id",
                rows,
            )
            result = cur.fetchall()
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)
    return {name: node_id for name, node_id in result}


def ensure_node(database_id: int, name: str, tx: psycopg2.extensions.connection | None = None) -> int:
    """Lấy id của node, tạo dòng tối thiểu nếu đây là lần đầu thấy tên đó."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO lineage_nodes (database_id, current_name) VALUES (%s, %s) "
                "ON CONFLICT (database_id, current_name) DO UPDATE "
                "SET current_name = EXCLUDED.current_name RETURNING id",
                (database_id, name),
            )
            (node_id,) = cur.fetchone()
        _commit_if_owned(conn, tx)
        return node_id
    finally:
        _close_if_owned(conn, tx)


def rename_node_by_id(database_id: int, node_id: int, new_name: str, tx: psycopg2.extensions.connection | None = None) -> bool:
    """Đổi tên node theo id, chỉ báo thành công khi tên thực sự thay đổi."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE lineage_nodes SET current_name = %s WHERE database_id = %s AND id = %s AND current_name <> %s RETURNING id",
                (new_name, database_id, node_id, new_name),
            )
            changed = cur.fetchone() is not None
        _commit_if_owned(conn, tx)
        return changed
    finally:
        _close_if_owned(conn, tx)


def mark_dropped(database_id: int, node_id: int, dropped_at: datetime, tx: psycopg2.extensions.connection | None = None) -> bool:
    """Đánh dấu node đã drop nhưng giữ nguyên row và lịch sử của nó."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE lineage_nodes SET dropped_at = %s WHERE database_id = %s AND id = %s AND dropped_at IS NULL RETURNING id",
                (dropped_at, database_id, node_id),
            )
            changed = cur.fetchone() is not None
        _commit_if_owned(conn, tx)
        return changed
    finally:
        _close_if_owned(conn, tx)


def revive_nodes(
    database_id: int, records: list[NodeRecord], tx: psycopg2.extensions.connection | None = None
) -> list[tuple[int, str, datetime]]:
    """Hồi sinh các node xuất hiện lại và trả mốc mtime để caller ghi event."""
    revived: list[tuple[int, str, datetime]] = []
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            for record in records:
                if record.source_file is None or not os.path.exists(record.source_file):
                    continue
                occurred_at = datetime.fromtimestamp(os.stat(record.source_file).st_mtime, UTC)
                cur.execute(
                    "UPDATE lineage_nodes SET dropped_at = NULL "
                    "WHERE database_id = %s AND current_name = %s AND dropped_at IS NOT NULL "
                    "RETURNING id, current_name",
                    (database_id, record.current_name),
                )
                row = cur.fetchone()
                if row is not None:
                    revived.append((row[0], row[1], occurred_at))
        _commit_if_owned(conn, tx)
        return revived
    finally:
        _close_if_owned(conn, tx)


def append_node_events(database_id: int, events: list[NodeEvent], tx: psycopg2.extensions.connection | None = None) -> None:
    """Ghi thêm event; recorded_at luôn là thời điểm ghi nhận ở UTC."""
    if not events:
        return

    recorded_at = datetime.now(UTC)
    rows = [
        (database_id, event.node_id, event.kind, event.occurred_at, recorded_at, psycopg2.extras.Json(event.details))
        for event in events
    ]
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO lineage_node_events (database_id, node_id, kind, occurred_at, recorded_at, details) VALUES %s",
                rows,
            )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def last_event_time(database_id: int, node_id: int, tx: psycopg2.extensions.connection | None = None) -> datetime | None:
    """Trả mốc occurred_at mới nhất của node, hoặc None nếu chưa có event."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(occurred_at) FROM lineage_node_events WHERE database_id = %s AND node_id = %s", (database_id, node_id))
            (occurred_at,) = cur.fetchone()
        return occurred_at
    finally:
        _close_if_owned(conn, tx)


def load_nodes(database_id: int, names: list[str], tx: psycopg2.extensions.connection | None = None) -> dict[str, NodeRecord]:
    """Đọc metadata của nhiều node trong một query."""
    if not names:
        return {}

    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_name, defined_in, columns_produced, columns_consumed, "
                "upstream_tables, downstream_tables, source_types, transform_types, "
                "confidence_min, confidence_max "
                "FROM lineage_nodes WHERE database_id = %s AND current_name = ANY(%s)",
                (database_id, names),
            )
            rows = cur.fetchall()
    finally:
        _close_if_owned(conn, tx)

    return {
        row[0]: NodeRecord(
            current_name=row[0],
            defined_in=row[1],
            source_file=None,
            columns_produced=row[2] or [],
            columns_consumed=row[3] or [],
            upstream_tables=row[4] or [],
            downstream_tables=row[5] or [],
            source_types=row[6] or [],
            transform_types=row[7] or [],
            confidence_min=row[8],
            confidence_max=row[9],
        )
        for row in rows
    }


def load_asset_profiles(database_id: int, names: list[str], tx: psycopg2.extensions.connection | None = None) -> dict[str, NodeProfile]:
    """Load node metadata and lifecycle history for a batch in one query."""
    if not names:
        return {}

    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT n.id, n.current_name, n.defined_in, n.columns_produced, n.columns_consumed, "
                "n.upstream_tables, n.downstream_tables, n.source_types, n.transform_types, "
                "n.confidence_min, n.confidence_max, n.dropped_at, "
                "MIN(e.occurred_at), MAX(e.occurred_at), "
                "COUNT(e.id) FILTER (WHERE e.kind = 'modified'), "
                "COALESCE( "
                "jsonb_agg(jsonb_build_object('name', e.details->>'from', 'changed_at', e.occurred_at) "
                "ORDER BY e.occurred_at) FILTER (WHERE e.kind = 'rename'), '[]'::jsonb) "
                "FROM lineage_nodes n "
                "LEFT JOIN lineage_node_events e ON e.database_id = n.database_id AND e.node_id = n.id "
                "WHERE n.database_id = %s AND n.current_name = ANY(%s) "
                "GROUP BY n.id, n.current_name, n.defined_in, n.columns_produced, n.columns_consumed, "
                "n.upstream_tables, n.downstream_tables, n.source_types, n.transform_types, "
                "n.confidence_min, n.confidence_max, n.dropped_at",
                (database_id, names),
            )
            rows = cur.fetchall()
    finally:
        _close_if_owned(conn, tx)

    profiles: dict[str, NodeProfile] = {}
    for row in rows:
        previous_names = [
            (entry["name"], datetime.fromisoformat(entry["changed_at"]))
            for entry in row[15]
            if entry.get("name") and entry.get("changed_at")
        ]
        profiles[row[1]] = NodeProfile(
            node_id=row[0],
            current_name=row[1],
            defined_in=row[2],
            columns_produced=row[3] or [],
            columns_consumed=row[4] or [],
            upstream_tables=row[5] or [],
            downstream_tables=row[6] or [],
            source_types=row[7] or [],
            transform_types=row[8] or [],
            confidence_min=row[9],
            confidence_max=row[10],
            dropped_at=row[11],
            first_seen=row[12],
            last_modified=row[13],
            modified_count=row[14],
            previous_names=previous_names,
        )
    return profiles


def all_node_names(database_id: int, tx: psycopg2.extensions.connection | None = None) -> list[str]:
    """Trả mọi tên node, kể cả node đã drop."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_name FROM lineage_nodes WHERE database_id = %s ORDER BY current_name", (database_id,))
            return [row[0] for row in cur.fetchall()]
    finally:
        _close_if_owned(conn, tx)


def _vector_literal(embedding: list[float] | None) -> str | None:
    return None if embedding is None else "[" + ",".join(str(value) for value in embedding) + "]"


def _description_from_row(row: tuple, offset: int = 0) -> DescriptionRecord | None:
    if row[offset] is None:
        return None
    return DescriptionRecord(
        node_id=row[offset],
        description=row[offset + 1],
        source=row[offset + 2],
        label=row[offset + 3],
        confidence=row[offset + 4],
        evidence_hash=row[offset + 5],
        is_stale=row[offset + 6],
    )


def _node_record_from_row(row: tuple, offset: int = 0) -> NodeRecord:
    return NodeRecord(
        current_name=row[offset],
        defined_in=row[offset + 1],
        source_file=None,
        columns_produced=row[offset + 2] or [],
        columns_consumed=row[offset + 3] or [],
        upstream_tables=row[offset + 4] or [],
        downstream_tables=row[offset + 5] or [],
        source_types=row[offset + 6] or [],
        transform_types=row[offset + 7] or [],
        confidence_min=row[offset + 8],
        confidence_max=row[offset + 9],
    )


_DESCRIPTION_NODE_SELECT = (
    "SELECT n.id, n.current_name, n.defined_in, n.columns_produced, n.columns_consumed, "
    "n.upstream_tables, n.downstream_tables, n.source_types, n.transform_types, "
    "n.confidence_min, n.confidence_max, d.node_id, d.description, d.source, d.label, "
    "d.confidence, d.evidence_hash, d.is_stale, MAX(e.occurred_at) "
    "FROM lineage_nodes n "
    "LEFT JOIN lineage_node_descriptions d ON d.database_id = n.database_id AND d.node_id = n.id "
    "LEFT JOIN lineage_node_events e ON e.database_id = n.database_id AND e.node_id = n.id "
)
_DESCRIPTION_NODE_GROUP_BY = (
    " GROUP BY n.id, n.current_name, n.defined_in, n.columns_produced, n.columns_consumed, "
    "n.upstream_tables, n.downstream_tables, n.source_types, n.transform_types, "
    "n.confidence_min, n.confidence_max, d.node_id, d.description, d.source, d.label, "
    "d.confidence, d.evidence_hash, d.is_stale"
)


def _description_node_from_row(row: tuple) -> DescriptionNode:
    return DescriptionNode(
        node_id=row[0],
        record=_node_record_from_row(row, 1),
        description=_description_from_row(row, 11),
        last_modified=row[18],
    )


def load_live_nodes_for_description(
    database_id: int,
    tx: psycopg2.extensions.connection | None = None,
) -> list[DescriptionNode]:
    """Load each non-dropped node, its description, and stable modification marker."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                _DESCRIPTION_NODE_SELECT
                + "WHERE n.database_id = %s AND n.dropped_at IS NULL"
                + _DESCRIPTION_NODE_GROUP_BY
                + " ORDER BY n.current_name"
            , (database_id,))
            return [_description_node_from_row(row) for row in cur.fetchall()]
    finally:
        _close_if_owned(conn, tx)


def load_description_node(database_id: int, node_id: int, tx: psycopg2.extensions.connection | None = None) -> DescriptionNode | None:
    """Load one node by stable id, including dropped nodes for the human edit route."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_DESCRIPTION_NODE_SELECT + "WHERE n.database_id = %s AND n.id = %s" + _DESCRIPTION_NODE_GROUP_BY, (database_id, node_id))
            row = cur.fetchone()
        return _description_node_from_row(row) if row is not None else None
    finally:
        _close_if_owned(conn, tx)


def load_descriptions(
    database_id: int, node_ids: list[int], tx: psycopg2.extensions.connection | None = None
) -> dict[int, DescriptionRecord]:
    if not node_ids:
        return {}
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT node_id, description, source, label, confidence, evidence_hash, is_stale "
                "FROM lineage_node_descriptions WHERE database_id = %s AND node_id = ANY(%s)",
                (database_id, node_ids),
            )
            descriptions: dict[int, DescriptionRecord] = {}
            for row in cur.fetchall():
                description = _description_from_row(row)
                if description is not None:
                    descriptions[row[0]] = description
            return descriptions
    finally:
        _close_if_owned(conn, tx)


def load_descriptions_by_names(
    database_id: int, names: list[str], tx: psycopg2.extensions.connection | None = None
) -> dict[str, DescriptionRecord]:
    """Batch-load descriptions for a set of table names trong 1 query — dùng
    cho chat agent (compose_node) chèn ngữ cảnh nghiệp vụ vào câu trả lời mà
    không mở 1 kết nối DB riêng cho mỗi bảng xuất hiện trong 1 lượt trả lời."""
    if not names:
        return {}
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT n.current_name, d.node_id, d.description, d.source, d.label, d.confidence, "
                "d.evidence_hash, d.is_stale FROM lineage_node_descriptions d "
                "JOIN lineage_nodes n ON n.database_id = d.database_id AND n.id = d.node_id WHERE d.database_id = %s AND n.current_name = ANY(%s)",
                (database_id, names),
            )
            descriptions: dict[str, DescriptionRecord] = {}
            for row in cur.fetchall():
                description = _description_from_row(row, offset=1)
                if description is not None:
                    descriptions[row[0]] = description
            return descriptions
    finally:
        _close_if_owned(conn, tx)


def load_column_descriptions_by_names(
    database_id: int, names: list[str], tx: psycopg2.extensions.connection | None = None
) -> dict[tuple[str, str], ColumnDescriptionRecord]:
    """Batch-load visible column descriptions keyed by (table, column)."""
    if not names:
        return {}
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT n.current_name, d.node_id, d.column_name, d.description, d.source, d.label, d.confidence, d.evidence_hash, d.is_stale "
                "FROM lineage_column_descriptions d JOIN lineage_nodes n ON n.database_id = d.database_id AND n.id = d.node_id "
                "WHERE d.database_id = %s AND n.current_name = ANY(%s)",
                (database_id, names),
            )
            return {(row[0], row[2]): _column_description_from_row(row, offset=1) for row in cur.fetchall()}
    finally:
        _close_if_owned(conn, tx)


_COLUMN_SCHEMA_FIELDS = (
    "column_name",
    "data_type",
    "is_nullable",
    "is_primary_key",
    "is_foreign_key",
    "references_table",
    "references_column",
    "origin",
)


def _column_schema_row_to_dict(row: tuple) -> dict:
    return {
        "name": row[0],
        "data_type": row[1],
        "is_nullable": row[2],
        "is_primary_key": row[3],
        "is_foreign_key": row[4],
        "references_table": row[5],
        "references_column": row[6],
        "origin": row[7],
    }


def _insert_column_schema_rows(cur, database_id: int, mapping: dict[str, list[dict]]) -> None:
    rows = [
        (
            database_id,
            table_name,
            col.get("name"),
            ordinal,
            col.get("data_type"),
            bool(col.get("is_nullable", True)),
            bool(col.get("is_primary_key", False)),
            bool(col.get("is_foreign_key", False)),
            col.get("references_table"),
            col.get("references_column"),
            col.get("origin", "declared"),
        )
        for table_name, cols in mapping.items()
        for ordinal, col in enumerate(cols)
        if col.get("name")
    ]
    if not rows:
        return
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO lineage_column_schema ("
        "database_id, table_name, column_name, ordinal, data_type, is_nullable, "
        "is_primary_key, is_foreign_key, references_table, references_column, origin"
        ") VALUES %s ON CONFLICT (database_id, table_name, column_name) DO NOTHING",
        rows,
    )


def replace_column_schema(
    database_id: int, mapping: dict[str, list[dict]], tx: psycopg2.extensions.connection | None = None
) -> None:
    """Ghi đè schema cột (origin='declared') cho ĐÚNG các bảng có trong `mapping`.

    Bảng không xuất hiện trong lượt ingest này giữ nguyên schema cũ — cùng
    nguyên tắc cộng dồn theo database_id như upsert_nodes. `mapping` rỗng =
    no-op (ingest không có DDL nào không được xoá schema đã có).
    """
    if not mapping:
        return
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM lineage_column_schema WHERE database_id = %s AND table_name = ANY(%s) AND origin = 'declared'",
                (database_id, list(mapping)),
            )
            _insert_column_schema_rows(cur, database_id, {t: c for t, c in mapping.items() if c})
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def replace_propagated_column_schema(
    database_id: int, mapping: dict[str, list[dict]], tx: psycopg2.extensions.connection | None = None
) -> None:
    """Ghi lại toàn bộ schema cột suy-diễn (origin='propagated') cho database.

    Xoá sạch propagated cũ rồi chèn mới — propagation phụ thuộc toàn đồ thị nên
    tính lại từ đầu mỗi lượt. `ON CONFLICT DO NOTHING` đảm bảo không đè lên hàng
    'declared' cùng (table, column).
    """
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM lineage_column_schema WHERE database_id = %s AND origin = 'propagated'",
                (database_id,),
            )
            _insert_column_schema_rows(cur, database_id, {t: c for t, c in mapping.items() if c})
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def rename_column_schema_table(
    database_id: int, old_name: str, new_name: str, tx: psycopg2.extensions.connection | None = None
) -> None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM lineage_column_schema WHERE database_id = %s AND table_name = %s",
                (database_id, new_name),
            )
            cur.execute(
                "UPDATE lineage_column_schema SET table_name = %s WHERE database_id = %s AND table_name = %s",
                (new_name, database_id, old_name),
            )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def drop_column_schema_table(
    database_id: int, table_name: str, tx: psycopg2.extensions.connection | None = None
) -> None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM lineage_column_schema WHERE database_id = %s AND table_name = %s",
                (database_id, table_name),
            )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def load_column_schema_by_names(
    database_id: int, names: list[str], tx: psycopg2.extensions.connection | None = None
) -> dict[str, list[dict]]:
    """Batch-load schema cột keyed theo tên bảng, mỗi list sắp theo `ordinal`."""
    if not names:
        return {}
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name, column_name, data_type, is_nullable, is_primary_key, "
                "is_foreign_key, references_table, references_column, origin "
                "FROM lineage_column_schema WHERE database_id = %s AND table_name = ANY(%s) "
                "ORDER BY table_name, ordinal, column_name",
                (database_id, names),
            )
            out: dict[str, list[dict]] = {}
            for row in cur.fetchall():
                out.setdefault(row[0], []).append(_column_schema_row_to_dict(row[1:]))
            return out
    finally:
        _close_if_owned(conn, tx)


def load_description_by_name(
    database_id: int, name: str, tx: psycopg2.extensions.connection | None = None
) -> tuple[int, DescriptionRecord] | None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.node_id, d.description, d.source, d.label, d.confidence, d.evidence_hash, d.is_stale "
                "FROM lineage_node_descriptions d JOIN lineage_nodes n ON n.database_id = d.database_id AND n.id = d.node_id "
                "WHERE d.database_id = %s AND n.current_name = %s",
                (database_id, name),
            )
            row = cur.fetchone()
        if row is None:
            return None
        description = _description_from_row(row)
        return (row[0], description) if description is not None else None
    finally:
        _close_if_owned(conn, tx)


def upsert_llm_descriptions(
    database_id: int,
    records: list[DescriptionRecord],
    embeddings: dict[int, list[float]],
    expected: dict[int, str | None],
    tx: psycopg2.extensions.connection | None = None,
) -> list[int]:
    """CAS write path for ingest; it never overwrites a human description."""
    conn = tx or _connect()
    written: list[int] = []
    try:
        with conn.cursor() as cur:
            for record in records:
                embedding = _vector_literal(embeddings.get(record.node_id))
                now = datetime.now(UTC)
                previous_hash = expected[record.node_id]
                if previous_hash is None:
                    cur.execute(
                        "INSERT INTO lineage_node_descriptions "
                        "(database_id, node_id, description, source, label, confidence, evidence_hash, is_stale, embedding, updated_at) "
                        "VALUES (%s, %s, %s, 'llm', %s, %s, %s, FALSE, %s::vector, %s) "
                        "ON CONFLICT (database_id, node_id) DO NOTHING RETURNING node_id",
                        (
                            database_id, record.node_id,
                            record.description,
                            record.label,
                            record.confidence,
                            record.evidence_hash,
                            embedding,
                            now,
                        ),
                    )
                else:
                    cur.execute(
                        "UPDATE lineage_node_descriptions SET description = %s, source = 'llm', label = %s, "
                        "confidence = %s, evidence_hash = %s, is_stale = FALSE, embedding = %s::vector, updated_at = %s "
                        "WHERE database_id = %s AND node_id = %s AND source = 'llm' AND evidence_hash = %s RETURNING node_id",
                        (
                            record.description,
                            record.label,
                            record.confidence,
                            record.evidence_hash,
                            embedding,
                            now,
                            database_id, record.node_id,
                            previous_hash,
                        ),
                    )
                row = cur.fetchone()
                if row is not None:
                    written.append(row[0])
        _commit_if_owned(conn, tx)
        return written
    finally:
        _close_if_owned(conn, tx)


def confirm_pending_description(
    database_id: int,
    record: DescriptionRecord,
    embedding: list[float] | None,
    base_source: Literal["llm", "human"] | None,
    base_hash: str | None,
    tx: psycopg2.extensions.connection | None = None,
) -> bool:
    """CAS write path for a human confirmation, including replacing a stale human row."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            now = datetime.now(UTC)
            vector = _vector_literal(embedding)
            if base_source is None:
                cur.execute(
                    "INSERT INTO lineage_node_descriptions "
                    "(database_id, node_id, description, source, label, confidence, evidence_hash, is_stale, embedding, updated_at) "
                    "VALUES (%s, %s, %s, 'llm', %s, %s, %s, FALSE, %s::vector, %s) "
                    "ON CONFLICT (database_id, node_id) DO NOTHING RETURNING node_id",
                    (
                        database_id, record.node_id,
                        record.description,
                        record.label,
                        record.confidence,
                        record.evidence_hash,
                        vector,
                        now,
                    ),
                )
            else:
                cur.execute(
                    "UPDATE lineage_node_descriptions SET description = %s, source = 'llm', label = %s, "
                    "confidence = %s, evidence_hash = %s, is_stale = FALSE, embedding = %s::vector, updated_at = %s "
                    "WHERE database_id = %s AND node_id = %s AND source = %s AND evidence_hash = %s RETURNING node_id",
                    (
                        record.description,
                        record.label,
                        record.confidence,
                        record.evidence_hash,
                        vector,
                        now,
                        database_id, record.node_id,
                        base_source,
                        base_hash,
                    ),
                )
            changed = cur.fetchone() is not None
        _commit_if_owned(conn, tx)
        return changed
    finally:
        _close_if_owned(conn, tx)


def put_human_description(
    database_id: int,
    node_id: int,
    description: str,
    evidence_hash: str,
    embedding: list[float] | None,
    tx: psycopg2.extensions.connection | None = None,
) -> bool:
    """Unconditional human write path; a human edit always wins if the node exists."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO lineage_node_descriptions "
                "(database_id, node_id, description, source, label, confidence, evidence_hash, is_stale, embedding, updated_at) "
                "SELECT database_id, id, %s, 'human', NULL, NULL, %s, FALSE, %s::vector, %s FROM lineage_nodes WHERE database_id = %s AND id = %s "
                "ON CONFLICT (database_id, node_id) DO UPDATE SET description = EXCLUDED.description, source = 'human', "
                "label = NULL, confidence = NULL, evidence_hash = EXCLUDED.evidence_hash, is_stale = FALSE, "
                "embedding = EXCLUDED.embedding, updated_at = EXCLUDED.updated_at RETURNING node_id",
                (description, evidence_hash, _vector_literal(embedding), datetime.now(UTC), database_id, node_id),
            )
            changed = cur.fetchone() is not None
        _commit_if_owned(conn, tx)
        return changed
    finally:
        _close_if_owned(conn, tx)


def mark_descriptions_stale(
    database_id: int, node_ids: list[int], expected_hash: dict[int, str], tx: psycopg2.extensions.connection | None = None
) -> None:
    if not node_ids:
        return
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            for node_id in node_ids:
                if node_id in expected_hash:
                    cur.execute(
                        "UPDATE lineage_node_descriptions SET is_stale = TRUE "
                        "WHERE database_id = %s AND node_id = %s AND source = 'human' AND evidence_hash = %s",
                        (database_id, node_id, expected_hash[node_id]),
                    )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def search_descriptions(
    database_id: int, embedding: list[float], limit: int, tx: psycopg2.extensions.connection | None = None
) -> list[tuple[str, str, float]]:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            vector = _vector_literal(embedding)
            cur.execute(
                "SELECT n.current_name, d.description, 1 - (d.embedding <=> %s::vector) AS score "
                "FROM lineage_node_descriptions d JOIN lineage_nodes n ON n.database_id = d.database_id AND n.id = d.node_id "
                "WHERE d.database_id = %s AND d.embedding IS NOT NULL AND n.dropped_at IS NULL "
                "ORDER BY d.embedding <=> %s::vector LIMIT %s",
                (vector, database_id, vector, limit),
            )
            return [(name, description, float(score)) for name, description, score in cur.fetchall()]
    finally:
        _close_if_owned(conn, tx)


def count_searchable_descriptions(
    database_id: int, tx: psycopg2.extensions.connection | None = None
) -> int:
    """Count descriptions visible to semantic search, excluding dropped nodes."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM lineage_node_descriptions d "
                "JOIN lineage_nodes n ON n.database_id = d.database_id AND n.id = d.node_id "
                "WHERE d.database_id = %s AND d.embedding IS NOT NULL AND n.dropped_at IS NULL",
                (database_id,),
            )
            (count,) = cur.fetchone()
            return int(count)
    finally:
        _close_if_owned(conn, tx)


def clear_descriptions(database_id: int, tx: psycopg2.extensions.connection | None = None) -> None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lineage_node_descriptions WHERE database_id = %s", (database_id,))
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def _column_description_from_row(row: tuple, offset: int = 0) -> ColumnDescriptionRecord:
    return ColumnDescriptionRecord(
        node_id=row[offset],
        column_name=row[offset + 1],
        description=row[offset + 2],
        source=row[offset + 3],
        label=row[offset + 4],
        confidence=row[offset + 5],
        evidence_hash=row[offset + 6],
        is_stale=row[offset + 7],
    )


def load_column_descriptions(
    database_id: int, node_ids: list[int], tx: psycopg2.extensions.connection | None = None
) -> dict[tuple[int, str], ColumnDescriptionRecord]:
    """Batch-load every column description for a set of table node ids."""
    if not node_ids:
        return {}
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT node_id, column_name, description, source, label, confidence, evidence_hash, is_stale "
                "FROM lineage_column_descriptions WHERE database_id = %s AND node_id = ANY(%s)",
                (database_id, node_ids),
            )
            return {
                (row[0], row[1]): _column_description_from_row(row) for row in cur.fetchall()
            }
    finally:
        _close_if_owned(conn, tx)


def load_column_description_by_name(
    database_id: int, table: str, column: str, tx: psycopg2.extensions.connection | None = None
) -> tuple[int, ColumnDescriptionRecord] | None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.node_id, c.column_name, c.description, c.source, c.label, c.confidence, "
                "c.evidence_hash, c.is_stale FROM lineage_column_descriptions c "
                "JOIN lineage_nodes n ON n.database_id = c.database_id AND n.id = c.node_id "
                "WHERE c.database_id = %s AND n.current_name = %s AND c.column_name = %s",
                (database_id, table, column),
            )
            row = cur.fetchone()
        return (row[0], _column_description_from_row(row)) if row is not None else None
    finally:
        _close_if_owned(conn, tx)


def upsert_llm_column_descriptions(
    database_id: int,
    records: list[ColumnDescriptionRecord],
    embeddings: dict[tuple[int, str], list[float]],
    expected: dict[tuple[int, str], str | None],
    tx: psycopg2.extensions.connection | None = None,
) -> list[tuple[int, str]]:
    """CAS write path for ingest; it never overwrites a human column description."""
    conn = tx or _connect()
    written: list[tuple[int, str]] = []
    try:
        with conn.cursor() as cur:
            for record in records:
                key = (record.node_id, record.column_name)
                embedding = _vector_literal(embeddings.get(key))
                now = datetime.now(UTC)
                previous_hash = expected[key]
                if previous_hash is None:
                    cur.execute(
                        "INSERT INTO lineage_column_descriptions "
                        "(database_id, node_id, column_name, description, source, label, confidence, evidence_hash, "
                        "is_stale, embedding, updated_at) "
                        "VALUES (%s, %s, %s, %s, 'llm', %s, %s, %s, FALSE, %s::vector, %s) "
                        "ON CONFLICT (database_id, node_id, column_name) DO NOTHING RETURNING node_id, column_name",
                        (
                            database_id,
                            record.node_id,
                            record.column_name,
                            record.description,
                            record.label,
                            record.confidence,
                            record.evidence_hash,
                            embedding,
                            now,
                        ),
                    )
                else:
                    cur.execute(
                        "UPDATE lineage_column_descriptions SET description = %s, source = 'llm', label = %s, "
                        "confidence = %s, evidence_hash = %s, is_stale = FALSE, embedding = %s::vector, "
                        "updated_at = %s WHERE database_id = %s AND node_id = %s AND column_name = %s AND source = 'llm' "
                        "AND evidence_hash = %s RETURNING node_id, column_name",
                        (
                            record.description,
                            record.label,
                            record.confidence,
                            record.evidence_hash,
                            embedding,
                            now,
                            database_id,
                            record.node_id,
                            record.column_name,
                            previous_hash,
                        ),
                    )
                row = cur.fetchone()
                if row is not None:
                    written.append((row[0], row[1]))
        _commit_if_owned(conn, tx)
        return written
    finally:
        _close_if_owned(conn, tx)


def confirm_pending_column_description(
    database_id: int,
    record: ColumnDescriptionRecord,
    embedding: list[float] | None,
    base_source: Literal["llm", "human"] | None,
    base_hash: str | None,
    tx: psycopg2.extensions.connection | None = None,
) -> bool:
    """CAS write path for a human confirmation, including replacing a stale human row."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            now = datetime.now(UTC)
            vector = _vector_literal(embedding)
            if base_source is None:
                cur.execute(
                    "INSERT INTO lineage_column_descriptions "
                    "(database_id, node_id, column_name, description, source, label, confidence, evidence_hash, "
                    "is_stale, embedding, updated_at) "
                    "VALUES (%s, %s, %s, %s, 'llm', %s, %s, %s, FALSE, %s::vector, %s) "
                    "ON CONFLICT (database_id, node_id, column_name) DO NOTHING RETURNING node_id",
                    (
                        database_id,
                        record.node_id,
                        record.column_name,
                        record.description,
                        record.label,
                        record.confidence,
                        record.evidence_hash,
                        vector,
                        now,
                    ),
                )
            else:
                cur.execute(
                    "UPDATE lineage_column_descriptions SET description = %s, source = 'llm', label = %s, "
                    "confidence = %s, evidence_hash = %s, is_stale = FALSE, embedding = %s::vector, "
                    "updated_at = %s WHERE database_id = %s AND node_id = %s AND column_name = %s AND source = %s "
                    "AND evidence_hash = %s RETURNING node_id",
                    (
                        record.description,
                        record.label,
                        record.confidence,
                        record.evidence_hash,
                        vector,
                        now,
                        database_id,
                        record.node_id,
                        record.column_name,
                        base_source,
                        base_hash,
                    ),
                )
            changed = cur.fetchone() is not None
        _commit_if_owned(conn, tx)
        return changed
    finally:
        _close_if_owned(conn, tx)


def put_human_column_description(
    database_id: int,
    node_id: int,
    column_name: str,
    description: str,
    evidence_hash: str,
    embedding: list[float] | None,
    tx: psycopg2.extensions.connection | None = None,
) -> bool:
    """Unconditional human write path; a human edit always wins if the node exists."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO lineage_column_descriptions "
                "(database_id, node_id, column_name, description, source, label, confidence, evidence_hash, is_stale, "
                "embedding, updated_at) "
                "SELECT database_id, id, %s, %s, 'human', NULL, NULL, %s, FALSE, %s::vector, %s FROM lineage_nodes WHERE database_id = %s AND id = %s "
                "ON CONFLICT (database_id, node_id, column_name) DO UPDATE SET description = EXCLUDED.description, "
                "source = 'human', label = NULL, confidence = NULL, evidence_hash = EXCLUDED.evidence_hash, "
                "is_stale = FALSE, embedding = EXCLUDED.embedding, updated_at = EXCLUDED.updated_at "
                "RETURNING node_id",
                (column_name, description, evidence_hash, _vector_literal(embedding), datetime.now(UTC), database_id, node_id),
            )
            changed = cur.fetchone() is not None
        _commit_if_owned(conn, tx)
        return changed
    finally:
        _close_if_owned(conn, tx)


def mark_column_descriptions_stale(
    database_id: int,
    keys: list[tuple[int, str]],
    expected_hash: dict[tuple[int, str], str],
    tx: psycopg2.extensions.connection | None = None,
) -> None:
    if not keys:
        return
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            for node_id, column_name in keys:
                key = (node_id, column_name)
                if key in expected_hash:
                    cur.execute(
                        "UPDATE lineage_column_descriptions SET is_stale = TRUE "
                        "WHERE database_id = %s AND node_id = %s AND column_name = %s AND source = 'human' AND evidence_hash = %s",
                        (database_id, node_id, column_name, expected_hash[key]),
                    )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def search_column_descriptions(
    database_id: int, embedding: list[float], limit: int, tx: psycopg2.extensions.connection | None = None
) -> list[tuple[str, str, str, float]]:
    """Return (table, column, description, score) ordered by cosine similarity."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            vector = _vector_literal(embedding)
            cur.execute(
                "SELECT n.current_name, c.column_name, c.description, 1 - (c.embedding <=> %s::vector) AS score "
                "FROM lineage_column_descriptions c JOIN lineage_nodes n ON n.database_id = c.database_id AND n.id = c.node_id "
                "WHERE c.database_id = %s AND c.embedding IS NOT NULL AND n.dropped_at IS NULL "
                "ORDER BY c.embedding <=> %s::vector LIMIT %s",
                (vector, database_id, vector, limit),
            )
            return [(table, column, description, float(score)) for table, column, description, score in cur.fetchall()]
    finally:
        _close_if_owned(conn, tx)


def count_searchable_column_descriptions(
    database_id: int, tx: psycopg2.extensions.connection | None = None
) -> int:
    """Count column descriptions visible to semantic search, excluding dropped nodes."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM lineage_column_descriptions c "
                "JOIN lineage_nodes n ON n.database_id = c.database_id AND n.id = c.node_id "
                "WHERE c.database_id = %s AND c.embedding IS NOT NULL AND n.dropped_at IS NULL",
                (database_id,),
            )
            (count,) = cur.fetchone()
            return int(count)
    finally:
        _close_if_owned(conn, tx)


def clear_column_descriptions(database_id: int, tx: psycopg2.extensions.connection | None = None) -> None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lineage_column_descriptions WHERE database_id = %s", (database_id,))
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def clear_nodes(database_id: int, tx: psycopg2.extensions.connection | None = None) -> None:
    """Xóa node metadata và lịch sử event, độc lập với snapshot lineage_edges."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM lineage_nodes WHERE database_id = %s", (database_id,))
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def clear_breaking_change_alerts(
    database_id: int, tx: psycopg2.extensions.connection | None = None
) -> None:
    """Delete alerts whose meaning is tied to a graph the user discarded."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM breaking_change_alerts WHERE database_id = %s", (database_id,))
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


@dataclass(frozen=True)
class IngestRunRecord:
    id: int
    database_id: int
    input_path: str
    sql_files_found: int
    parsed_count: int
    unparsed_count: int
    pending_review_count: int
    triggered_by_user_id: int | None
    started_at: datetime


def record_ingest_run(
    database_id: int,
    input_path: str,
    *,
    sql_files_found: int,
    parsed_count: int,
    unparsed_count: int,
    pending_review_count: int,
    triggered_by_user_id: int | None,
    tx: psycopg2.extensions.connection | None = None,
) -> None:
    """Ghi lại 1 lượt ingest — chỉ là log, không đổi cách dữ liệu gộp vào graph
    (vẫn cộng dồn theo database_id). Cho phép user xem lại lịch sử: lượt nào,
    từ path nào, ra bao nhiêu cạnh — khi 1 project ingest nhiều lần từ nhiều
    thư mục khác nhau."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ingest_runs (database_id, input_path, sql_files_found, parsed_count, "
                "unparsed_count, pending_review_count, triggered_by_user_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    database_id,
                    input_path,
                    sql_files_found,
                    parsed_count,
                    unparsed_count,
                    pending_review_count,
                    triggered_by_user_id,
                ),
            )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def list_ingest_runs(
    database_id: int, limit: int = 20, tx: psycopg2.extensions.connection | None = None
) -> list[IngestRunRecord]:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, database_id, input_path, sql_files_found, parsed_count, unparsed_count, "
                "pending_review_count, triggered_by_user_id, started_at FROM ingest_runs "
                "WHERE database_id = %s ORDER BY started_at DESC LIMIT %s",
                (database_id, limit),
            )
            return [IngestRunRecord(*row) for row in cur.fetchall()]
    finally:
        _close_if_owned(conn, tx)


def list_all_database_ids(tx: psycopg2.extensions.connection | None = None) -> list[int]:
    """Toàn bộ database hiện có — dùng cho tác vụ hệ thống chạy nền (auto
    re-ingest), không thuộc về 1 user cụ thể nên không qua database_service."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM databases ORDER BY id")
            return [row[0] for row in cur.fetchall()]
    finally:
        _close_if_owned(conn, tx)


@dataclass(frozen=True)
class BreakingChangeAlertRecord:
    id: int
    database_id: int
    kind: Literal["drop", "rename"]
    table_name: str
    new_name: str | None
    downstream_tables: list[str]
    suggested_action: str
    detected_at: datetime
    acknowledged: bool


@dataclass(frozen=True)
class BreakingChangeDetection:
    kind: Literal["drop", "rename"]
    table_name: str
    new_name: str | None
    downstream_tables: list[str]
    suggested_action: str


def sync_breaking_change_alerts(
    database_id: int,
    detected: list[BreakingChangeDetection],
    tx: psycopg2.extensions.connection | None = None,
) -> None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            for alert in detected:
                cur.execute(
                    "INSERT INTO breaking_change_alerts (database_id, kind, table_name, new_name, "
                    "downstream_tables, suggested_action) VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (database_id, kind, table_name, (COALESCE(new_name, ''))) "
                    "DO UPDATE SET downstream_tables = EXCLUDED.downstream_tables, "
                    "suggested_action = EXCLUDED.suggested_action, "
                    "acknowledged = CASE WHEN breaking_change_alerts.downstream_tables "
                    "IS DISTINCT FROM EXCLUDED.downstream_tables THEN FALSE "
                    "ELSE breaking_change_alerts.acknowledged END",
                    (
                        database_id,
                        alert.kind,
                        alert.table_name,
                        alert.new_name,
                        psycopg2.extras.Json(alert.downstream_tables),
                        alert.suggested_action,
                    ),
                )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def list_breaking_change_alerts(
    database_id: int,
    include_acknowledged: bool = False,
    limit: int = 50,
    tx: psycopg2.extensions.connection | None = None,
) -> list[BreakingChangeAlertRecord]:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            query = (
                "SELECT id, database_id, kind, table_name, new_name, downstream_tables, "
                "suggested_action, detected_at, acknowledged FROM breaking_change_alerts WHERE database_id = %s"
            )
            params: list[object] = [database_id]
            if not include_acknowledged:
                query += " AND acknowledged = FALSE"
            query += " ORDER BY detected_at DESC LIMIT %s"
            params.append(limit)
            cur.execute(query, params)
            return [BreakingChangeAlertRecord(*row) for row in cur.fetchall()]
    finally:
        _close_if_owned(conn, tx)


def acknowledge_breaking_change_alert(
    database_id: int, alert_id: int, tx: psycopg2.extensions.connection | None = None
) -> bool:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE breaking_change_alerts SET acknowledged = TRUE WHERE id = %s AND database_id = %s",
                (alert_id, database_id),
            )
            updated = cur.rowcount > 0
        _commit_if_owned(conn, tx)
        return updated
    finally:
        _close_if_owned(conn, tx)


@dataclass(frozen=True)
class ChatSessionRow:
    database_id: int
    user_id: int
    pending_clarification: dict | None
    updated_at: datetime


@dataclass(frozen=True)
class ChatTurnRow:
    id: int
    database_id: int
    user_id: int
    question: str
    resolved_table: str | None
    answer: str
    created_at: datetime


def ensure_chat_session(database_id: int, user_id: int, tx: psycopg2.extensions.connection | None = None) -> None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_sessions (database_id, user_id) VALUES (%s, %s) "
                "ON CONFLICT (database_id, user_id) DO NOTHING",
                (database_id, user_id),
            )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def get_chat_session(
    database_id: int, user_id: int, tx: psycopg2.extensions.connection | None = None
) -> ChatSessionRow | None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT database_id, user_id, pending_clarification, updated_at "
                "FROM chat_sessions WHERE database_id = %s AND user_id = %s",
                (database_id, user_id),
            )
            row = cur.fetchone()
        return ChatSessionRow(*row) if row else None
    finally:
        _close_if_owned(conn, tx)


def set_chat_session_clarification(
    database_id: int,
    user_id: int,
    pending_clarification: dict | None,
    tx: psycopg2.extensions.connection | None = None,
) -> None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE chat_sessions SET pending_clarification = %s, updated_at = now() "
                "WHERE database_id = %s AND user_id = %s",
                (
                    psycopg2.extras.Json(pending_clarification) if pending_clarification is not None else None,
                    database_id,
                    user_id,
                ),
            )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def insert_chat_turn(
    database_id: int,
    user_id: int,
    question: str,
    resolved_table: str | None,
    answer: str,
    tx: psycopg2.extensions.connection | None = None,
) -> None:
    """Append-only — 1 lượt hỏi/đáp = 1 dòng INSERT, không đọc-sửa-ghi lịch sử cũ."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_turns (database_id, user_id, question, resolved_table, answer) "
                "VALUES (%s, %s, %s, %s, %s)",
                (database_id, user_id, question, resolved_table, answer),
            )
            cur.execute(
                "UPDATE chat_sessions SET updated_at = now() WHERE database_id = %s AND user_id = %s",
                (database_id, user_id),
            )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def list_recent_chat_turns(
    database_id: int, user_id: int, limit: int, tx: psycopg2.extensions.connection | None = None
) -> list[ChatTurnRow]:
    """N lượt gần nhất, trả theo thứ tự CŨ -> MỚI (đúng thứ tự hội thoại thật)."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, database_id, user_id, question, resolved_table, answer, created_at "
                "FROM chat_turns WHERE database_id = %s AND user_id = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (database_id, user_id, limit),
            )
            rows = [ChatTurnRow(*row) for row in cur.fetchall()]
        return list(reversed(rows))
    finally:
        _close_if_owned(conn, tx)


def clear_chat_session(database_id: int, user_id: int, tx: psycopg2.extensions.connection | None = None) -> None:
    """"Bắt đầu lại" — xoá lịch sử + clarification đang chờ, giữ nguyên định danh (database_id, user_id)."""
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_turns WHERE database_id = %s AND user_id = %s", (database_id, user_id))
            cur.execute(
                "UPDATE chat_sessions SET pending_clarification = NULL, updated_at = now() "
                "WHERE database_id = %s AND user_id = %s",
                (database_id, user_id),
            )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def get_sql_document_hash(
    database_id: int, file_path: str, statement_order: int, tx: psycopg2.extensions.connection | None = None
) -> str | None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash FROM lineage_sql_documents "
                "WHERE database_id = %s AND file_path = %s AND statement_order = %s",
                (database_id, file_path, statement_order),
            )
            row = cur.fetchone()
        return row[0] if row else None
    finally:
        _close_if_owned(conn, tx)


def upsert_sql_document(
    database_id: int,
    file_path: str,
    statement_order: int,
    table_name: str | None,
    content: str,
    content_hash: str,
    embedding: list[float],
    tx: psycopg2.extensions.connection | None = None,
) -> None:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO lineage_sql_documents "
                "(database_id, file_path, statement_order, table_name, content, content_hash, embedding, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s::vector, now()) "
                "ON CONFLICT (database_id, file_path, statement_order) DO UPDATE SET "
                "table_name = EXCLUDED.table_name, content = EXCLUDED.content, "
                "content_hash = EXCLUDED.content_hash, embedding = EXCLUDED.embedding, updated_at = now()",
                (database_id, file_path, statement_order, table_name, content, content_hash, _vector_literal(embedding)),
            )
        _commit_if_owned(conn, tx)
    finally:
        _close_if_owned(conn, tx)


def count_searchable_sql_documents(database_id: int, tx: psycopg2.extensions.connection | None = None) -> int:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM lineage_sql_documents WHERE database_id = %s AND embedding IS NOT NULL",
                (database_id,),
            )
            (count,) = cur.fetchone()
            return int(count)
    finally:
        _close_if_owned(conn, tx)


def search_sql_documents(
    database_id: int, embedding: list[float], limit: int, tx: psycopg2.extensions.connection | None = None
) -> list[tuple[str, int, str | None, str, float]]:
    conn = tx or _connect()
    try:
        with conn.cursor() as cur:
            vector = _vector_literal(embedding)
            cur.execute(
                "SELECT file_path, statement_order, table_name, content, 1 - (embedding <=> %s::vector) AS score "
                "FROM lineage_sql_documents WHERE database_id = %s AND embedding IS NOT NULL "
                "ORDER BY embedding <=> %s::vector LIMIT %s",
                (vector, database_id, vector, limit),
            )
            return [
                (file_path, order, table_name, content, float(score))
                for file_path, order, table_name, content, score in cur.fetchall()
            ]
    finally:
        _close_if_owned(conn, tx)
