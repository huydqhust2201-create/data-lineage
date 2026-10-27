"""Impact analysis cho cạnh control lineage (dependency_kind != "output")."""

import networkx as nx
import pytest

from src.models.schemas import LineageEdge
from src.services import graph_service, impact_service

_DB = 987654


@pytest.fixture(autouse=True)
def _isolated_graph():
    graph_service._reset_graph(_DB, nx.MultiDiGraph())
    yield
    graph_service._reset_graph(_DB, None)


def test_risk_note_control_lineage_distinct_from_output():
    # cột filter bị drop → nói về "lỗi biên dịch" / "tập hàng", KHÔNG phải
    # "cột đích mất dữ liệu"
    filter_drop = impact_service.risk_note("unknown", "drop", "filter")
    assert "lọc" in filter_drop.lower() or "where" in filter_drop.lower()
    assert "biên dịch" in filter_drop.lower()

    join_type = impact_service.risk_note("unknown", "type", "join_key")
    assert "join" in join_type.lower()

    # dependency_kind mặc định "output" → giữ nguyên bảng transform cũ
    assert impact_service.risk_note("join", "type", "output") == impact_service.risk_note("join", "type")


def test_risk_note_conditional_not_pass_through():
    # cột đích tính bằng CASE — đổi VALUE cột nguồn KHÔNG phải "rủi ro thấp,
    # truyền thẳng" như 'direct'
    cond = impact_service.risk_note("conditional", "value")
    direct = impact_service.risk_note("direct", "value")
    assert cond != direct
    assert "cao" in cond.lower()
    assert "thấp" in direct.lower()


def test_risk_note_control_lineage_covers_all_change_kinds():
    # Mọi change_kind trên cạnh control đều ra text riêng, KHÔNG rơi về câu
    # "Chưa xác định được loại transform" của _RISK_BY_TRANSFORM["unknown"].
    for dep in ("filter", "join_key", "group_key", "window_partition", "window_order"):
        for ck in impact_service.ChangeKind.__args__:
            note = impact_service.risk_note("unknown", ck, dep)
            assert note
            assert "chưa xác định" not in note.lower(), (dep, ck)

    # add_column trên cột control = rủi ro thấp (không đụng vai trò lọc/join)
    assert "thấp" in impact_service.risk_note("unknown", "add_column", "filter").lower()
    # constraint trên khoá join = rủi ro cao (đổi cardinality / mất RI)
    assert "cao" in impact_service.risk_note("unknown", "constraint", "join_key").lower()


def test_impact_surfaces_filter_column_dependency():
    # readmission_flag lọc theo stg_patients.is_active — cột này KHÔNG vào
    # output nào, trước đây impact "is_active" trả rỗng.
    graph_service.add_edge(
        _DB,
        LineageEdge(
            source_table="stg_patients",
            source_column="is_active",
            target_table="readmission_flag",
            target_column=None,
            dependency_kind="filter",
            transform_type="unknown",
            confidence=1.0,
            source_type="parser",
        ),
    )

    result = impact_service.query_impact(_DB, "stg_patients", "is_active", "downstream", change_kind="drop")

    assert len(result.confirmed) == 1
    view = result.confirmed[0]
    assert view.target.table == "readmission_flag"
    assert view.dependency_kind == "filter"
    assert "biên dịch" in view.risk.lower()
