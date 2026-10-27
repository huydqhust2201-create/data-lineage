"""Chủ đề 3: risk note nhận biết kiểu + constraint hiện tại của cột đang đổi."""

import networkx as nx
import pytest

from src.models.schemas import LineageEdge
from src.services import graph_service, impact_service

_DB = 876543


@pytest.fixture(autouse=True)
def _isolated_graph():
    graph_service._reset_graph(_DB, nx.MultiDiGraph())
    yield
    graph_service._reset_graph(_DB, None)


# ---- _type_transition_verdict (thuần, không DB) -------------------------------


@pytest.mark.parametrize(
    "cur,tgt,needle",
    [
        ("INTEGER", "BIGINT", "mở rộng"),
        ("BIGINT", "SMALLINT", "THU HẸP"),
        ("DECIMAL(12,2)", "INTEGER", "THU HẸP"),
        ("INTEGER", "NUMERIC(10,2)", "an toàn"),
        ("VARCHAR(20)", "TIMESTAMP", "ĐỔI HỌ KIỂU"),
        ("VARCHAR(20)", "VARCHAR(50)", "cùng kiểu cơ bản"),
        ("TEXT", "CHAR(5)", "cùng họ chuỗi"),
    ],
)
def test_type_transition_verdict(cur, tgt, needle):
    assert needle in impact_service._type_transition_verdict(cur, tgt)


# ---- schema_change_note -----------------------------------------------------


def _col(**kw):
    base = {
        "name": "c",
        "data_type": "INTEGER",
        "is_nullable": True,
        "is_primary_key": False,
        "is_foreign_key": False,
        "references_table": None,
        "references_column": None,
        "origin": "declared",
    }
    base.update(kw)
    return base


def test_note_none_without_schema_or_for_value_change():
    assert impact_service.schema_change_note(None, "constraint") is None
    assert impact_service.schema_change_note(_col(), "value") is None
    assert impact_service.schema_change_note(_col(), "rename") is None


def test_pk_column_states_facts_only_no_verdict():
    # Hướng SỰ THẬT: nêu "PRIMARY KEY (ngầm NOT NULL)" rồi để người đọc + note
    # theo-cạnh tự suy — KHÔNG viết verdict "no-op" riêng.
    note = impact_service.schema_change_note(
        _col(name="patient_id", is_primary_key=True, is_nullable=False), "constraint"
    )
    assert "PRIMARY KEY (ngầm NOT NULL)" in note
    assert "no-op" not in note.lower()  # verdict đã bỏ


def test_constraint_on_nullable_column_warns_backfill_and_join_loss():
    note = impact_service.schema_change_note(_col(name="x", is_nullable=True), "constraint", join_key_count=3)
    assert "backfill" in note.lower()
    assert "3 model" in note


def test_risk_note_missing_cell_falls_back_safely(monkeypatch):
    # Ô trống trong bảng luật -> câu an toàn, KHÔNG KeyError, KHÔNG bịa mức.
    monkeypatch.setitem(impact_service._RISK_BY_TRANSFORM, "direct", {"drop": "x"})
    note = impact_service.risk_note("direct", "type")  # "type" không còn trong dict
    assert note == impact_service._RISK_FALLBACK
    assert "thủ công" in note


def test_type_change_classifies_when_target_given():
    note = impact_service.schema_change_note(_col(name="amt", data_type="DECIMAL(12,2)"), "type", target_type="INTEGER")
    assert "THU HẸP" in note


def test_propagated_origin_is_hedged():
    note = impact_service.schema_change_note(
        _col(name="x", data_type="INTEGER", origin="propagated"), "type", target_type="TEXT"
    )
    assert "suy diễn" in note.lower()


def test_drop_flags_key_columns():
    assert "PRIMARY KEY" in impact_service.schema_change_note(_col(is_primary_key=True), "drop")
    fk = impact_service.schema_change_note(_col(is_foreign_key=True, references_table="raw_x"), "drop")
    assert "raw_x" in fk


# ---- query_impact tích hợp: prefix ghép trước note theo-cạnh ----------------


def test_query_impact_prepends_schema_prefix(monkeypatch):
    graph_service.add_edge(
        _DB,
        LineageEdge(
            source_table="raw_patients",
            source_column="patient_id",
            target_table="stg_patients",
            target_column="patient_id",
            transform_type="direct",
            confidence=1.0,
            source_type="parser",
        ),
    )
    monkeypatch.setattr(
        impact_service.storage_service,
        "load_column_schema_by_names",
        lambda _db, names, *a, **k: {
            "raw_patients": [
                {
                    "name": "patient_id",
                    "data_type": "INTEGER",
                    "is_nullable": False,
                    "is_primary_key": True,
                    "is_foreign_key": False,
                    "references_table": None,
                    "references_column": None,
                    "origin": "declared",
                }
            ]
        },
    )

    result = impact_service.query_impact(_DB, "raw_patients", "patient_id", "downstream", change_kind="constraint")
    assert result.confirmed
    view = result.confirmed[0]
    assert view.risk.startswith("Cột `patient_id`: kiểu `INTEGER`, PRIMARY KEY (ngầm NOT NULL).")
    assert " — " in view.risk  # có cả prefix (sự thật) lẫn note theo-cạnh
    # schema_note = đúng phần prefix, để FE hiển thị 1 lần cho cả nhóm
    assert view.schema_note and view.risk.startswith(view.schema_note + " — ")


def test_query_impact_no_schema_falls_back_to_static_note(monkeypatch):
    graph_service.add_edge(
        _DB,
        LineageEdge(
            source_table="raw_x",
            source_column="a",
            target_table="stg_x",
            target_column="a",
            transform_type="direct",
            confidence=1.0,
            source_type="parser",
        ),
    )
    monkeypatch.setattr(
        impact_service.storage_service, "load_column_schema_by_names", lambda *a, **k: {}
    )
    result = impact_service.query_impact(_DB, "raw_x", "a", "downstream", change_kind="type")
    assert result.confirmed
    # Không có schema -> chính xác note tĩnh cũ, không prefix, schema_note None.
    assert result.confirmed[0].risk == impact_service.risk_note("direct", "type", "output")
    assert result.confirmed[0].schema_note is None
