"""Tier 2 (Chủ đề 3): _propagate_column_schema — lan KIỂU qua cạnh direct."""

import networkx as nx

from src.agents.nodes.lineage_nodes import _propagate_column_schema


def _g(*edges: tuple) -> nx.MultiDiGraph:
    """edges: (src, tgt, src_col, tgt_col, **overrides-as-dict-optional)."""
    g = nx.MultiDiGraph()
    for e in edges:
        src, tgt, sc, tc = e[0], e[1], e[2], e[3]
        attrs = {"source_type": "parser", "transform_type": "direct"}
        if len(e) > 4:
            attrs.update(e[4])
        if sc is not None:
            attrs["source_column"] = sc
        if tc is not None:
            attrs["target_column"] = tc
        g.add_edge(src, tgt, **attrs)
    return g


_RAW = {
    "raw_patients": [
        {"name": "patient_id", "data_type": "INT", "is_nullable": False, "is_primary_key": True,
         "is_foreign_key": False, "references_table": None, "references_column": None, "origin": "declared"},
        {"name": "full_name", "data_type": "VARCHAR(200)", "is_nullable": False, "is_primary_key": False,
         "is_foreign_key": False, "references_table": None, "references_column": None, "origin": "declared"},
    ]
}


def test_single_hop_propagates_data_type_only():
    g = _g(("raw_patients", "stg_patients", "full_name", "patient_name"))
    out = _propagate_column_schema(g, _RAW)
    assert "stg_patients" in out
    col = out["stg_patients"][0]
    assert col["name"] == "patient_name"
    assert col["data_type"] == "VARCHAR(200)"
    assert col["origin"] == "propagated"
    # is_nullable LUÔN True (không suy được qua đồ thị), KHÔNG mang PK/FK
    assert col["is_nullable"] is True
    assert col["is_primary_key"] is False
    assert col["is_foreign_key"] is False


def test_not_null_source_still_propagates_as_nullable():
    # patient_id declared NOT NULL — nhưng propagated phải để nullable=True
    # (có thể đi qua LEFT JOIN mà đồ thị không thấy).
    g = _g(("raw_patients", "stg_patients", "patient_id", "patient_id"))
    col = _propagate_column_schema(g, _RAW)["stg_patients"][0]
    assert col["is_nullable"] is True
    assert col["is_primary_key"] is False  # PK không "chảy" qua SELECT


def test_multi_hop_fills_through_chain():
    g = _g(
        ("raw_patients", "stg_patients", "full_name", "patient_name"),
        ("stg_patients", "patient_summary", "patient_name", "name"),
        ("patient_summary", "mart_final", "name", "name"),
    )
    out = _propagate_column_schema(g, _RAW)
    assert out["stg_patients"][0]["data_type"] == "VARCHAR(200)"
    assert out["patient_summary"][0]["data_type"] == "VARCHAR(200)"
    assert out["mart_final"][0]["data_type"] == "VARCHAR(200)"


def test_cycle_returns_empty():
    g = _g(
        ("raw_patients", "a", "full_name", "x"),
        ("a", "b", "x", "x"),
        ("b", "a", "x", "x"),
    )
    assert _propagate_column_schema(g, _RAW) == {}


def test_does_not_overwrite_declared():
    g = _g(("raw_patients", "stg_patients", "full_name", "patient_name"))
    declared = {
        **_RAW,
        "stg_patients": [
            {"name": "patient_name", "data_type": "TEXT", "is_nullable": True, "is_primary_key": False,
             "is_foreign_key": False, "references_table": None, "references_column": None, "origin": "declared"},
        ],
    }
    out = _propagate_column_schema(g, declared)
    assert "stg_patients" not in out  # đã declared -> không propagate đè


def test_skips_non_direct_and_llm_edges():
    g = _g(
        ("raw_patients", "agg_table", "full_name", "cnt", {"transform_type": "aggregation"}),
        ("raw_patients", "llm_table", "full_name", "x", {"source_type": "llm"}),
    )
    assert _propagate_column_schema(g, _RAW) == {}


def test_skips_edges_without_both_columns_or_without_source_type():
    g = _g(
        ("raw_patients", "t1", "full_name", None),   # thiếu target_column
        ("raw_patients", "t2", None, "x"),           # thiếu source_column
    )
    assert _propagate_column_schema(g, _RAW) == {}


def test_skips_when_source_column_has_no_data_type():
    raw = {"r": [{"name": "c", "data_type": None, "is_nullable": True, "is_primary_key": False,
                  "is_foreign_key": False, "references_table": None, "references_column": None, "origin": "declared"}]}
    g = _g(("r", "t", "c", "c"))
    assert _propagate_column_schema(g, raw) == {}


def test_first_direct_source_wins_for_same_target_column():
    raw = {
        "a": [{"name": "k", "data_type": "INT", "is_nullable": True, "is_primary_key": False,
               "is_foreign_key": False, "references_table": None, "references_column": None, "origin": "declared"}],
        "b": [{"name": "k", "data_type": "TEXT", "is_nullable": True, "is_primary_key": False,
               "is_foreign_key": False, "references_table": None, "references_column": None, "origin": "declared"}],
    }
    g = _g(("a", "t", "k", "k"), ("b", "t", "k", "k"))
    out = _propagate_column_schema(g, raw)
    assert len(out["t"]) == 1  # chỉ 1 entry cho cột "k"
