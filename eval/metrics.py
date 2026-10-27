"""Pure, offline lineage extraction metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.models.schemas import LineageEdge

EdgeKey = tuple[str, str]


def _normalize(name: str) -> str:
    return "".join(name.lower().split())


def edge_key(source_table: str, target_table: str) -> EdgeKey:
    """Return a case- and whitespace-insensitive table-pair key."""
    return _normalize(source_table), _normalize(target_table)


@dataclass(frozen=True)
class ScoreResult:
    """matched/missing/spurious chứa EdgeKey (score(), mức bảng) hoặc
    ColumnEdgeKey (column_score(), mức cột) tuỳ hàm sinh ra kết quả — cả hai
    đều là tuple[str, ...], không phân biệt được bằng type riêng vì
    aggregate() dùng chung cho cả 2 loại."""

    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    matched: list[tuple[str, ...]]
    missing: list[tuple[str, ...]]
    spurious: list[tuple[str, ...]]


@dataclass(frozen=True)
class TransformTypeAccuracy:
    correct: int
    total: int
    accuracy: float | None


def _rates(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = 1.0 if tp + fp == 0 and fn == 0 else (tp / (tp + fp) if tp + fp else 0.0)
    recall = 1.0 if tp + fn == 0 else tp / (tp + fn)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _expected_map(expected: list[dict[str, Any]]) -> dict[EdgeKey, dict[str, Any]]:
    return {edge_key(str(item["source_table"]), str(item["target_table"])): item for item in expected}


def _data_lineage_only(predicted: list[LineageEdge]) -> list[LineageEdge]:
    """Ground truth (tests/ground_truth/expected/*.json) chỉ từng ghi nhận
    data lineage (dependency_kind="output", cột nguồn chảy vào giá trị 1 cột
    đích) — chưa từng ghi nhận control lineage (dependency_kind khác: cột chỉ
    quyết định HÀNG NÀO xuất hiện qua WHERE/JOIN/GROUP BY/OVER, target_column
    luôn None). Từ khi parser bắt đầu phát ra cả cạnh control lineage (tính
    năng dependency_kind), so khớp thẳng với ground truth cũ sẽ đếm nhầm các
    cạnh control lineage hợp lệ này thành "spurious". Lọc trước khi so khớp
    để metric tiếp tục đo đúng thứ PRD.md mục 3 yêu cầu (lineage dữ liệu)."""
    return [edge for edge in predicted if edge.dependency_kind == "output"]


def _predicted_map(predicted: list[LineageEdge]) -> dict[EdgeKey, LineageEdge]:
    selected: dict[EdgeKey, LineageEdge] = {}
    for edge in _data_lineage_only(predicted):
        key = edge_key(edge.source_table, edge.target_table)
        current = selected.get(key)
        candidate_rank = (
            0 if edge.source_column is None and edge.target_column is None else 1,
            edge.source_column or "",
            edge.target_column or "",
        )
        current_rank = (
            0 if current is not None and current.source_column is None and current.target_column is None else 1,
            current.source_column or "" if current is not None else "",
            current.target_column or "" if current is not None else "",
        )
        if current is None or candidate_rank < current_rank:
            selected[key] = edge
    return selected


def score(predicted: list[LineageEdge], expected: list[dict[str, Any]]) -> ScoreResult:
    predicted_keys = set(_predicted_map(predicted))
    expected_keys = set(_expected_map(expected))
    matched = sorted(predicted_keys & expected_keys)
    spurious = sorted(predicted_keys - expected_keys)
    missing = sorted(expected_keys - predicted_keys)
    precision, recall, f1 = _rates(len(matched), len(spurious), len(missing))
    return ScoreResult(len(matched), len(spurious), len(missing), precision, recall, f1, matched, missing, spurious)


def transform_type_accuracy(predicted: list[LineageEdge], expected: list[dict[str, Any]]) -> TransformTypeAccuracy:
    predictions = _predicted_map(predicted)
    expected_by_key = _expected_map(expected)
    correct = total = 0
    for key in set(predictions) & set(expected_by_key):
        expected_type = expected_by_key[key].get("transform_type")
        if expected_type is None:
            continue
        total += 1
        if predictions[key].transform_type.strip().lower() == str(expected_type).strip().lower():
            correct += 1
    return TransformTypeAccuracy(correct, total, correct / total if total else None)


def aggregate(results: list[ScoreResult]) -> ScoreResult:
    tp = sum(result.tp for result in results)
    fp = sum(result.fp for result in results)
    fn = sum(result.fn for result in results)
    precision, recall, f1 = _rates(tp, fp, fn)
    return ScoreResult(
        tp,
        fp,
        fn,
        precision,
        recall,
        f1,
        [key for result in results for key in result.matched],
        [key for result in results for key in result.missing],
        [key for result in results for key in result.spurious],
    )


ColumnEdgeKey = tuple[str, str, str, str]


def column_edge_key(
    source_table: str, source_column: str | None, target_table: str, target_column: str | None
) -> ColumnEdgeKey:
    """Case/whitespace-insensitive column-pair key. None cột chuẩn hoá về ""
    — cạnh control-lineage (dependency_kind != "output", target_column=None)
    không lẫn với cạnh có cột hợp lệ."""
    return _normalize(source_table), _normalize(source_column or ""), _normalize(target_table), _normalize(target_column or "")


def _expected_column_map(expected: list[dict[str, Any]]) -> dict[ColumnEdgeKey, dict[str, Any]]:
    return {
        column_edge_key(str(item["source_table"]), item.get("source_column"), str(item["target_table"]), item.get("target_column")): item
        for item in expected
    }


def _predicted_column_map(predicted: list[LineageEdge]) -> dict[ColumnEdgeKey, LineageEdge]:
    return {
        column_edge_key(edge.source_table, edge.source_column, edge.target_table, edge.target_column): edge
        for edge in _data_lineage_only(predicted)
    }


def column_score(predicted: list[LineageEdge], expected: list[dict[str, Any]]) -> ScoreResult:
    """Precision/recall mức CỘT (source_table, source_column, target_table,
    target_column) — nghiêm ngặt hơn score() (chỉ mức bảng). Fixture nào có
    toàn source_column/target_column=null sẽ so khớp bằng key rỗng "" —
    không phải bug, nhưng con số ở đó không có ý nghĩa thật (không có claim
    nào về cột để chấm), cần nêu rõ khi đọc báo cáo."""
    predicted_keys = set(_predicted_column_map(predicted))
    expected_keys = set(_expected_column_map(expected))
    matched = sorted(predicted_keys & expected_keys)
    spurious = sorted(predicted_keys - expected_keys)
    missing = sorted(expected_keys - predicted_keys)
    precision, recall, f1 = _rates(len(matched), len(spurious), len(missing))
    return ScoreResult(len(matched), len(spurious), len(missing), precision, recall, f1, matched, missing, spurious)


def sweep(
    predicted_by_file: dict[str, list[LineageEdge]],
    expected_by_file: dict[str, list[dict[str, Any]]],
    thresholds: list[float],
) -> dict[float, ScoreResult]:
    results: dict[float, ScoreResult] = {}
    for threshold in thresholds:
        per_file = [
            score(
                [edge for edge in predicted_by_file.get(name, []) if edge.confidence >= threshold],
                expected,
            )
            for name, expected in expected_by_file.items()
        ]
        results[threshold] = aggregate(per_file)
    return results
