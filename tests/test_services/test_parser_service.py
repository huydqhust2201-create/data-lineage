import json
from pathlib import Path

import pytest

from src.services.parser_service import SQLParserService


@pytest.fixture
def parser_service():
    return SQLParserService(default_dialect="postgres")


def test_ground_truth_parser_precision_chinook_sakila(parser_service):
    """
    Kiểm thử độ chính xác của parser tĩnh trên 2 trường hợp phức tạp mới:
    Chinook (09_chinook_complex) và Sakila (10_sakila_complex).
    """
    sql_dir = Path("tests/ground_truth/sql")
    expected_dir = Path("tests/ground_truth/expected")

    test_files = [
        "08_olist_complex.sql",
        "09_chinook_complex.sql",
        "10_sakila_complex.sql",
        "11_alarm_quiz_lineage.sql",
        "12_alarm_face_mission_lineage.sql",
        "13_saas_analytics_pipeline.sql",
    ]

    for file_name in test_files:
        sql_path = sql_dir / file_name
        expected_path = expected_dir / f"{sql_path.stem}.json"

        assert expected_path.exists(), f"Thiếu file expected: {expected_path}"

        # Parse file SQL thực tế
        actual_edges = parser_service.parse_file(str(sql_path))

        # Đọc kết quả mong đợi
        with open(expected_path, encoding="utf-8") as f:
            expected_edges = json.load(f)

        # Kiểm tra xem các cạnh mong đợi có tồn tại trong kết quả thực tế không
        for expected in expected_edges:
            # Tìm cạnh khớp trong actual_edges
            found = False
            for actual in actual_edges:
                if (
                    actual.source_table == expected["source_table"]
                    and actual.source_column == expected["source_column"]
                    and actual.target_table == expected["target_table"]
                    and actual.target_column == expected["target_column"]
                ):
                    found = True
                    break

            assert found, (
                f"LỖI TRONG FILE: {file_name}\n"
                f"Không tìm thấy cạnh lineage mong đợi: "
                f"{expected['source_table']}.{expected['source_column']} -> "
                f"{expected['target_table']}.{expected['target_column']}\n"
                f"Danh sách cạnh thực tế tìm thấy: {[(a.source_table, a.source_column, a.target_table, a.target_column) for a in actual_edges]}"
            )


def test_multi_statement_file_extracts_lineage_from_every_statement(parser_service):
    """Regression: sqlglot.parse_one() chỉ đọc ĐÚNG 1 câu lệnh của cả file,
    âm thầm bỏ hết phần còn lại — với file DDL thực tế nhiều CREATE TABLE +
    CREATE VIEW (vd export MySQL), kết quả trước đây sai lệch/thiếu cạnh mà
    không có cảnh báo nào. _parse_core() phải dùng sqlglot.parse() và duyệt
    từng statement để không bỏ sót."""
    sql = """
        CREATE TABLE BacSi (
            MaBS INT PRIMARY KEY,
            HoTenBS VARCHAR(100) NOT NULL
        );

        CREATE TABLE DichVuKham (
            MaDV INT PRIMARY KEY,
            TenDV VARCHAR(100) NOT NULL
        );

        CREATE OR REPLACE VIEW vw_LichHenConTrong AS
        SELECT bs.HoTenBS, dv.TenDV
        FROM LichHen lh
        JOIN BacSi bs ON lh.MaBS = bs.MaBS
        JOIN DichVuKham dv ON lh.MaDV = dv.MaDV;

        CREATE OR REPLACE VIEW vw_DoanhThuTheoNgay AS
        SELECT SUM(tt.TongTien) AS TongDoanhThu
        FROM ThanhToan tt;
    """
    edges = parser_service.parse_sql_text(sql, target_table_fallback="nhakhoa")

    by_target = {(e.source_table, e.source_column, e.target_table, e.target_column) for e in edges}
    assert ("bacsi", "HoTenBS", "vw_lichhencontrong", "HoTenBS") in by_target
    assert ("dichvukham", "TenDV", "vw_lichhencontrong", "TenDV") in by_target
    assert ("thanhtoan", "TongTien", "vw_doanhthutheongay", "TongDoanhThu") in by_target
    # Trước fix: target_table rơi về fallback tên file thay vì tên VIEW thật.
    assert all(e.target_table != "nhakhoa" for e in edges)


def test_parser_service_cache(parser_service, tmp_path):
    path = tmp_path / "model.sql"
    path.write_text("SELECT id AS order_id FROM raw_orders", encoding="utf-8")

    edges1, reason1 = parser_service.parse_file_with_diagnostics(str(path))
    assert len(edges1) == 1

    edges2, reason2 = parser_service.parse_file_with_diagnostics(str(path))
    assert len(edges2) == 1
    assert reason1 == reason2

    assert edges1[0].edge_id != edges2[0].edge_id
    assert edges1[0].source_table == edges2[0].source_table


def test_parser_extracts_control_lineage_where_and_join(parser_service):
    edges = parser_service.parse_sql_text(
        "CREATE TABLE high_risk AS "
        "SELECT p.patient_id, p.name "
        "FROM stg_patients p "
        "JOIN visit_summary v ON p.patient_id = v.patient_id "
        "WHERE p.age >= 65"
    )
    by_kind = {(e.dependency_kind, e.source_table, e.source_column) for e in edges}

    # output (data) lineage giữ nguyên
    assert ("output", "stg_patients", "patient_id") in by_kind
    assert ("output", "stg_patients", "name") in by_kind
    # control lineage MỚI: cột WHERE (age) không vào output nào
    assert ("filter", "stg_patients", "age") in by_kind
    assert not any(e.dependency_kind == "output" and e.source_column == "age" for e in edges)
    # cột JOIN key
    assert ("join_key", "stg_patients", "patient_id") in by_kind
    assert ("join_key", "visit_summary", "patient_id") in by_kind
    # cạnh control luôn target_column=None
    assert all(e.target_column is None for e in edges if e.dependency_kind != "output")


def test_parser_transform_type_conditional_for_case_and_coalesce(parser_service):
    edges = parser_service.parse_sql_text(
        "CREATE TABLE flags AS SELECT "
        "id, "
        "CASE WHEN score >= 50 THEN 'pass' ELSE 'fail' END AS grade, "
        "COALESCE(note, 'n/a') AS note "
        "FROM raw_scores"
    )
    by_target = {e.target_column: e.transform_type for e in edges if e.dependency_kind == "output"}
    assert by_target["id"] == "direct"
    assert by_target["grade"] == "conditional"
    assert by_target["note"] == "conditional"


def test_parser_transform_type_sum_case_stays_aggregation(parser_service):
    # SUM(CASE WHEN ...) — bản chất là gộp hàng, không phải conditional thuần
    edges = parser_service.parse_sql_text(
        "CREATE TABLE t AS SELECT k, SUM(CASE WHEN flag THEN 1 ELSE 0 END) AS n FROM src GROUP BY k"
    )
    assert next(e for e in edges if e.target_column == "n").transform_type == "aggregation"


def test_parser_control_lineage_group_by(parser_service):
    edges = parser_service.parse_sql_text(
        "CREATE TABLE daily AS SELECT order_date, sum(amount) AS total FROM orders GROUP BY order_date"
    )
    assert any(e.dependency_kind == "group_key" and e.source_column == "order_date" for e in edges)


def test_parser_control_lineage_skips_unqualified_column_in_multi_table_query(parser_service):
    # `status` không kèm tên bảng + truy vấn 2 bảng -> không đoán, bỏ qua
    edges = parser_service.parse_sql_text(
        "CREATE TABLE t AS SELECT a.id FROM a JOIN b ON a.id = b.id WHERE status = 'x'"
    )
    assert not any(e.dependency_kind == "filter" and e.source_column == "status" for e in edges)


def test_parser_control_lineage_reasoning_mentions_role(parser_service, tmp_path):
    path = tmp_path / "m.sql"
    path.write_text(
        "CREATE TABLE m AS SELECT x.id FROM x WHERE x.active = true", encoding="utf-8"
    )
    edges, _ = parser_service.parse_file_with_diagnostics(str(path))
    filt = next(e for e in edges if e.dependency_kind == "filter")
    assert "lọc" in filt.evidence.reasoning.lower() or "where" in filt.evidence.reasoning.lower()
    assert "hàng" in filt.evidence.reasoning_detail.lower()


def test_parser_evidence_has_short_and_detailed_reasoning(parser_service, tmp_path):
    path = tmp_path / "stg_appointments.sql"
    path.write_text(
        "CREATE TABLE stg_appointments AS SELECT appointment_id, doctor_id FROM raw_appointments",
        encoding="utf-8",
    )

    edges, _ = parser_service.parse_file_with_diagnostics(str(path))

    assert edges
    for edge in edges:
        assert edge.evidence is not None
        assert edge.evidence.reasoning
        assert edge.evidence.reasoning_detail
        # Bản chi tiết phải là văn bản khác và dài hơn bản ngắn, và nói rõ
        # đây là cạnh parser tĩnh (không cần HITL).
        assert edge.evidence.reasoning_detail != edge.evidence.reasoning
        assert len(edge.evidence.reasoning_detail) > len(edge.evidence.reasoning)
        assert "HITL" in edge.evidence.reasoning_detail


def test_parser_cache_keeps_file_specific_fallback_target(parser_service, tmp_path):
    sql = "SELECT id AS order_id FROM source_tbl"
    orders_path = tmp_path / "orders.sql"
    customers_path = tmp_path / "customers.sql"
    orders_path.write_text(sql, encoding="utf-8")
    customers_path.write_text(sql, encoding="utf-8")

    orders_edges, _ = parser_service.parse_file_with_diagnostics(str(orders_path))
    customers_edges, _ = parser_service.parse_file_with_diagnostics(str(customers_path))

    assert [edge.target_table for edge in orders_edges] == ["orders"]
    assert [edge.target_table for edge in customers_edges] == ["customers"]


def test_parser_preserves_qualified_table_names(parser_service):
    edges = parser_service.parse_sql_text("CREATE TABLE mart.sales AS SELECT o.id FROM raw.orders AS o")

    assert [(edge.source_table, edge.target_table) for edge in edges] == [("raw.orders", "mart.sales")]


def test_parser_preserves_normalized_transform_expression_for_each_source_column(parser_service):
    edges = parser_service.parse_sql_text(
        "CREATE TABLE daily_revenue AS SELECT order_date, sum(amount_a + amount_b) as revenue FROM raw.orders"
    )

    by_target = {edge.target_column: [] for edge in edges}
    for edge in edges:
        by_target[edge.target_column].append(edge)

    assert by_target["order_date"][0].evidence.transform_expression == "order_date"
    revenue_edges = by_target["revenue"]
    assert len(revenue_edges) == 2
    assert {edge.source_column for edge in revenue_edges} == {"amount_a", "amount_b"}
    assert {edge.evidence.transform_expression for edge in revenue_edges} == {"SUM(amount_a + amount_b) AS revenue"}
    assert all(edge.evidence.file_path is None and edge.evidence.raw_sql is None for edge in revenue_edges)


def test_attach_evidence_preserves_transform_expression(parser_service):
    edges = parser_service.parse_sql_text("SELECT sum(amount) as revenue FROM orders", target_table_fallback="daily_revenue")
    attached = parser_service._attach_evidence(edges, "models/daily_revenue.sql", "SELECT sum(amount) as revenue FROM orders")

    evidence = attached[0].evidence
    assert evidence.transform_expression == "SUM(amount) AS revenue"
    assert evidence.file_path == "models/daily_revenue.sql"
    assert evidence.raw_sql == "SELECT sum(amount) as revenue FROM orders"


def test_parser_resolves_cte_and_alias_to_qualified_source(parser_service):
    edges = parser_service.parse_sql_text(
        "CREATE TABLE mart.sales AS WITH cleaned AS (SELECT id FROM raw.orders) SELECT c.id FROM cleaned AS c"
    )

    assert [(edge.source_table, edge.target_table) for edge in edges] == [("raw.orders", "mart.sales")]


def test_parser_drops_true_self_loops(parser_service):
    edges = parser_service.parse_sql_text("CREATE TABLE orders AS SELECT id FROM orders")

    assert edges == []


def test_parser_keeps_same_unqualified_name_in_different_schemas(parser_service):
    edges = parser_service.parse_sql_text("CREATE TABLE mart.orders AS SELECT id FROM raw.orders")

    assert [(edge.source_table, edge.target_table) for edge in edges] == [("raw.orders", "mart.orders")]


def test_parser_preserves_dbt_ref_and_source_casing(parser_service):
    ref_edges = parser_service.parse_sql_text("CREATE TABLE target AS SELECT a.id FROM {{ ref('Alarm') }} AS a")
    source_edges = parser_service.parse_sql_text(
        "CREATE TABLE target AS SELECT o.id FROM {{ source('raw', 'Orders') }} AS o"
    )

    assert [(edge.source_table, edge.target_table) for edge in ref_edges] == [("Alarm", "target")]
    assert [(edge.source_table, edge.target_table) for edge in source_edges] == [("raw.Orders", "target")]


def test_parser_extracts_ordered_ddl_events(parser_service, tmp_path):
    path = tmp_path / "migration.sql"
    path.write_text(
        "CREATE TABLE a AS SELECT id FROM s; ALTER TABLE a RENAME TO b; CREATE TABLE a AS SELECT id FROM t;",
        encoding="utf-8",
    )

    events, reason = parser_service.parse_file_events(str(path))

    assert reason is None
    assert [(event.kind, event.order) for event in events] == [
        ("edges", 0),
        ("rename", 1),
        ("edges", 2),
    ]
    assert (events[0].edges[0].source_table, events[0].edges[0].target_table) == ("s", "a")
    assert (events[1].table, events[1].new_name) == ("a", "b")
    assert (events[2].edges[0].source_table, events[2].edges[0].target_table) == ("t", "a")


@pytest.mark.parametrize(
    ("sql", "kind", "table", "new_name"),
    [
        ("ALTER TABLE raw.orders RENAME TO raw.orders_v2", "rename", "raw.orders", "raw.orders_v2"),
        ("DROP TABLE x", "drop", "x", None),
        ("DROP TABLE IF EXISTS raw.x", "drop", "raw.x", None),
    ],
)
def test_parser_extracts_ddl_event_types(parser_service, tmp_path, sql, kind, table, new_name):
    path = tmp_path / "migration.sql"
    path.write_text(sql, encoding="utf-8")

    events, reason = parser_service.parse_file_events(str(path))

    assert reason is None
    assert len(events) == 1
    assert events[0].kind == kind
    assert events[0].table == table
    assert events[0].new_name == new_name


def test_parser_ignores_non_rename_alter_actions(parser_service, tmp_path):
    path = tmp_path / "migration.sql"
    path.write_text("ALTER TABLE t ADD COLUMN c INT", encoding="utf-8")

    events, _ = parser_service.parse_file_events(str(path))

    assert events == []


def test_parser_cache_keeps_ddl_events_and_recreates_edge_ids(parser_service, tmp_path):
    path = tmp_path / "migration.sql"
    path.write_text(
        "CREATE TABLE a AS SELECT id FROM s; ALTER TABLE a RENAME TO b;",
        encoding="utf-8",
    )

    first_events, _ = parser_service.parse_file_events(str(path))
    second_events, _ = parser_service.parse_file_events(str(path))

    assert [(event.kind, event.order) for event in second_events] == [("edges", 0), ("rename", 1)]
    assert first_events[0].edges[0].edge_id != second_events[0].edges[0].edge_id


def test_parser_keeps_cte_target_for_non_dbt_sql(parser_service):
    edges = parser_service.parse_sql_text(
        "WITH renamed AS (SELECT id FROM raw.orders) SELECT id FROM renamed",
        target_table_fallback="different_file_stem",
    )

    assert [edge.target_table for edge in edges] == ["renamed"]


def test_parser_prefers_explicit_dml_target_for_dbt_model(parser_service, tmp_path):
    path = tmp_path / "model_stem.sql"
    path.write_text(
        "CREATE TABLE mart.x AS SELECT id FROM {{ ref('y') }}",
        encoding="utf-8",
    )

    edges = parser_service.parse_file(str(path))

    assert [(edge.source_table, edge.target_table) for edge in edges] == [("y", "mart.x")]


def test_parser_uses_fallback_target_for_inline_dbt_model(parser_service):
    edges = parser_service.parse_sql_text(
        "WITH renamed AS (SELECT id FROM {{ ref('raw_orders') }}) SELECT id FROM renamed",
        target_table_fallback="model_a",
    )

    assert [edge.target_table for edge in edges] == ["model_a"]


def test_parser_resolves_union_all_columns_by_position(parser_service):
    """06_union_all.sql: trước đây parser trả [] (SELECT * qua UNION không
    resolve được, phải rơi vào LLM fallback — xem CLAUDE.md). Đã fix bằng
    match cột UNION theo vị trí + lần ngược 1 cấp vào CTE nguồn khi nhánh chỉ
    là SELECT *. Giờ parser tự resolve đúng, không cần LLM cho file này nữa."""
    edges = parser_service.parse_file("tests/ground_truth/sql/06_union_all.sql")

    by_target_col = {(e.source_table, e.source_column, e.target_column) for e in edges}
    assert ("stg_orders", "order_id", "order_id") in by_target_col
    assert ("stg_orders_app", "order_id", "order_id") in by_target_col
    assert ("stg_orders", "amount", "amount") in by_target_col
    assert ("stg_orders_app", "amount", "amount") in by_target_col
    assert all(e.target_table == "all_orders" for e in edges)
    # order_source là literal ('web'/'app'), không có cột nguồn -> không sinh cạnh
    assert all(e.target_column != "order_source" for e in edges)


def test_parser_still_falls_back_when_union_branch_hits_raw_table(parser_service, tmp_path):
    """Nhánh an toàn cũ vẫn phải còn: khi UNION có nhánh SELECT * trỏ thẳng
    vào bảng thô (không phải CTE có cột tường minh), không có gì để lần
    ngược tới -> vẫn trả [] để đi qua LLM fallback, không đoán bừa."""
    path = tmp_path / "model_stem.sql"
    path.write_text(
        "with all_x as (select * from raw_a union all select * from raw_b) "
        "select * from all_x",
        encoding="utf-8",
    )

    edges = parser_service.parse_file(str(path))

    assert edges == []


def test_parser_preserves_declare_event_for_dbt_create_star(parser_service, tmp_path):
    path = tmp_path / "model_stem.sql"
    path.write_text(
        "CREATE TABLE mart.x AS SELECT * FROM {{ ref('stg_x') }}",
        encoding="utf-8",
    )

    events, reason = parser_service.parse_file_events(str(path))

    assert reason is None
    assert [(event.kind, event.table) for event in events] == [("declare", "mart.x")]


def test_parser_declare_event_carries_no_columns_for_create_as_select(parser_service, tmp_path):
    # CREATE TABLE ... AS SELECT không có danh sách cột tường minh -> event
    # declare (khi không resolve được cạnh) mang columns rỗng, đường đi cũ nguyên.
    path = tmp_path / "model_stem.sql"
    path.write_text("CREATE TABLE mart.x AS SELECT * FROM {{ ref('stg_x') }}", encoding="utf-8")
    events, reason = parser_service.parse_file_events(str(path))
    assert reason is None
    declare = [e for e in events if e.kind == "declare"]
    assert declare and declare[0].columns == []


def test_parser_extracts_column_schema_from_ddl(parser_service, tmp_path):
    path = tmp_path / "_sources.sql"
    path.write_text(
        """
        CREATE TABLE raw_departments (
            department_id INTEGER NOT NULL PRIMARY KEY,
            department_name VARCHAR(120) NOT NULL
        );
        CREATE TABLE raw_doctors (
            doctor_id INTEGER PRIMARY KEY,
            full_name VARCHAR(200) NOT NULL,
            department_id INTEGER NOT NULL REFERENCES raw_departments (department_id),
            note TEXT
        );
        """,
        encoding="utf-8",
    )
    events, reason = parser_service.parse_file_events(str(path))
    assert reason is None
    by_table = {e.table: e.columns for e in events if e.kind == "declare"}
    assert set(by_table) == {"raw_departments", "raw_doctors"}

    dept = {c.name: c for c in by_table["raw_departments"]}
    assert dept["department_id"].data_type == "INT"
    assert dept["department_id"].is_primary_key is True
    assert dept["department_id"].is_nullable is False
    assert dept["department_name"].is_nullable is False
    assert dept["department_name"].is_primary_key is False

    doc = {c.name: c for c in by_table["raw_doctors"]}
    assert doc["doctor_id"].is_primary_key is True
    assert doc["doctor_id"].is_nullable is False  # PK ngầm NOT NULL
    assert doc["department_id"].is_foreign_key is True
    assert doc["department_id"].references_table == "raw_departments"
    assert doc["department_id"].references_column == "department_id"
    assert doc["note"].is_nullable is True
    assert doc["note"].is_foreign_key is False
    assert all(c.origin == "declared" for cols in by_table.values() for c in cols)


def test_parser_extracts_table_level_primary_and_foreign_key(parser_service, tmp_path):
    path = tmp_path / "_s.sql"
    path.write_text(
        """
        CREATE TABLE raw_orders (
            order_id INTEGER,
            customer_id INTEGER,
            PRIMARY KEY (order_id),
            FOREIGN KEY (customer_id) REFERENCES raw_customers (customer_id)
        );
        """,
        encoding="utf-8",
    )
    events, _ = parser_service.parse_file_events(str(path))
    cols = {c.name: c for e in events if e.kind == "declare" for c in e.columns}
    assert cols["order_id"].is_primary_key is True
    assert cols["order_id"].is_nullable is False
    assert cols["customer_id"].is_foreign_key is True
    assert cols["customer_id"].references_table == "raw_customers"


def test_parser_skips_macro_only_file_without_llm_fallback(parser_service, tmp_path):
    path = tmp_path / "cents_to_dollars.sql"
    path.write_text(
        "{% macro cents_to_dollars(column_name) -%}\n"
        "    ({{ column_name }} / 100)::numeric(16, 2)\n"
        "{%- endmacro %}\n",
        encoding="utf-8",
    )

    events, reason = parser_service.parse_file_events(str(path))

    assert events == []
    assert reason is None


def test_parser_extracts_edge_from_dbt_snapshot_block(parser_service, tmp_path):
    path = tmp_path / "payments_snapshot.sql"
    path.write_text(
        "{% snapshot payments_snapshot %}\n"
        "{{ config(target_schema='snapshots', unique_key='id', strategy='timestamp', updated_at='updated_at') }}\n"
        "select * from {{ source('raw', 'payments') }}\n"
        "{% endsnapshot %}\n",
        encoding="utf-8",
    )

    events, reason = parser_service.parse_file_events(str(path))

    assert reason is None
    edges = [edge for event in events if event.kind == "edges" for edge in event.edges]
    assert [(edge.source_table, edge.target_table) for edge in edges] == [("raw.payments", "payments_snapshot")]
    assert edges[0].source_column is None and edges[0].target_column is None
    assert edges[0].evidence.transform_expression is None
