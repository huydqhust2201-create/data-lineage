from eval.metrics import aggregate, column_edge_key, column_score, edge_key, score, sweep, transform_type_accuracy
from src.models.schemas import LineageEdge


def edge(source="raw.orders", target="stg_orders", confidence=0.9, transform="direct", source_column=None, target_column=None):
    return LineageEdge(
        source_table=source,
        target_table=target,
        confidence=confidence,
        source_type="llm",
        transform_type=transform,
        source_column=source_column,
        target_column=target_column,
    )


def expected(source="raw.orders", target="stg_orders", transform="direct", source_column=None, target_column=None):
    result = {"source_table": source, "target_table": target, "transform_type": transform}
    if source_column is not None:
        result["source_column"] = source_column
    if target_column is not None:
        result["target_column"] = target_column
    return result


def test_perfect_prediction():
    result = score([edge()], [expected()])
    assert (result.precision, result.recall, result.f1) == (1.0, 1.0, 1.0)


def test_missing_and_spurious_edges():
    missing = score([edge()], [expected(), expected("raw.customers", "stg_orders")])
    spurious = score([edge(), edge("raw.customers", "stg_orders")], [expected()])
    assert missing.precision == 1.0 and missing.recall < 1.0 and missing.fn == 1
    assert spurious.recall == 1.0 and spurious.precision < 1.0 and spurious.fp == 1


def test_empty_conventions_and_normalization():
    assert score([], []).f1 == 1.0
    assert score([edge()], []).precision == 0.0
    assert score([edge(" RAW. ORDERS ", "STG_ORDERS")], [expected()]).f1 == 1.0


def test_sweep_and_aggregate_use_micro_averages():
    predictions = {"a": [edge(confidence=0.4), edge("raw.customers", "stg_customers", confidence=0.9)]}
    expected_by_file = {"a": [expected(), expected("raw.customers", "stg_customers")]}
    assert sweep(predictions, expected_by_file, [0.5])[0.5].recall == 0.5
    result = aggregate([score([edge()], [expected()]), score([], [expected("raw.x", "stg_x")])])
    assert (result.tp, result.fn, result.recall) == (1, 1, 0.5)


def test_transform_type_accuracy_cases():
    assert transform_type_accuracy([edge()], [expected()]).accuracy == 1.0
    assert transform_type_accuracy([edge(transform="join")], [expected()]).accuracy == 0.0
    assert transform_type_accuracy([], [expected()]).accuracy is None
    assert transform_type_accuracy([edge()], [{"source_table": "raw.orders", "target_table": "stg_orders"}]).total == 0


def test_edge_key_and_empty_aggregate():
    assert edge_key(" RAW. Orders ", " STG_ORDERS ") == ("raw.orders", "stg_orders")
    assert aggregate([]).f1 == 1.0


def test_sweep_keeps_each_requested_threshold():
    results = sweep({"a": [edge()]}, {"a": [expected()]}, [0.4, 0.9])
    assert set(results) == {0.4, 0.9}


def test_column_edges_do_not_change_table_metrics():
    predicted = [
        edge(source_column="id", target_column="id"),
        edge(source_column="amount", target_column="total_amount"),
        edge(),
    ]
    assert score(predicted, [expected()]).f1 == 1.0


def test_transform_type_accuracy_is_order_independent_for_column_edges():
    predicted = [
        edge(transform="join", source_column="customer_id", target_column="customer_id"),
        edge(transform="direct", source_column="id", target_column="id"),
    ]
    reversed_predicted = list(reversed(predicted))
    assert transform_type_accuracy(predicted, [expected()]).accuracy == transform_type_accuracy(reversed_predicted, [expected()]).accuracy


def test_column_edge_key_normalizes_and_treats_none_as_empty():
    assert column_edge_key(" RAW. Orders ", " ID ", " STG_ORDERS ", "id") == ("raw.orders", "id", "stg_orders", "id")
    assert column_edge_key("raw.orders", None, "stg_orders", None) == ("raw.orders", "", "stg_orders", "")


def test_column_score_is_stricter_than_table_score():
    # table đúng nhưng cột sai — score() (mức bảng) cho F1=1.0, column_score() phải thấy sai
    predicted = [edge(source_column="id", target_column="wrong_alias")]
    exp = [expected(source_column="id", target_column="total_amount")]
    assert score(predicted, exp).f1 == 1.0
    result = column_score(predicted, exp)
    assert result.tp == 0 and result.fp == 1 and result.fn == 1


def test_column_score_matches_when_columns_align():
    predicted = [
        edge(source_column="id", target_column="id"),
        edge(source_column="amount", target_column="total_amount"),
    ]
    exp = [
        expected(source_column="id", target_column="id"),
        expected(source_column="amount", target_column="total_amount"),
    ]
    result = column_score(predicted, exp)
    assert (result.tp, result.fp, result.fn) == (2, 0, 0)
    assert result.precision == 1.0 and result.recall == 1.0


def test_column_score_on_all_null_columns_is_a_vacuous_empty_key_match():
    """Fixture không khai báo cột (source_column/target_column đều None ở cả 2
    phía) vẫn "khớp" qua key rỗng "" — không phải bug, nhưng không phải bằng
    chứng thật về độ chính xác cấp cột (xem docstring column_score)."""
    result = column_score([edge()], [expected()])
    assert result.f1 == 1.0
    assert result.matched == [("raw.orders", "", "stg_orders", "")]
