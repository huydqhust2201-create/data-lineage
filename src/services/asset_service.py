from collections import defaultdict
from pathlib import Path, PurePath

import networkx as nx  # type: ignore[import-untyped]

from src.services.storage_service import NodeRecord


def relative_to_ingest_root(file_path: str, input_root: str) -> str:
    """Return a POSIX path relative to an ingest root when it is contained.

    Evidence sometimes originates outside ``input_root`` (for example from a
    caller that supplied an external file).  Keeping that path absolute is
    safer than producing a misleading ``../`` path.
    """
    path = Path(file_path).resolve()
    root = Path(input_root).resolve()
    if not path.is_relative_to(root):
        return PurePath(path).as_posix()
    return PurePath(path.relative_to(root)).as_posix()


def build_records_from_graph(graph: nx.MultiDiGraph, definitions: dict[str, str], input_path: str) -> list[NodeRecord]:
    """Materialize one metadata record per graph/declared node in one edge pass."""
    produced: dict[str, set[str]] = defaultdict(set)
    consumed: dict[str, set[str]] = defaultdict(set)
    upstream: dict[str, set[str]] = defaultdict(set)
    downstream: dict[str, set[str]] = defaultdict(set)
    source_types: dict[str, set[str]] = defaultdict(set)
    transform_types: dict[str, set[str]] = defaultdict(set)
    confidences: dict[str, list[float]] = defaultdict(list)
    evidence_files: dict[str, str] = {}

    for source, target, attrs in graph.edges(data=True):
        upstream[target].add(source)
        downstream[source].add(target)
        if attrs.get("source_column") is not None:
            consumed[source].add(attrs["source_column"])
        if attrs.get("target_column") is not None:
            produced[target].add(attrs["target_column"])
        for name in (source, target):
            source_types[name].add(attrs.get("source_type", "parser"))
            transform_types[name].add(attrs.get("transform_type", "unknown"))
            confidences[name].append(float(attrs.get("confidence", 1.0)))
        evidence = attrs.get("evidence") or {}
        if evidence.get("file_path"):
            evidence_files.setdefault(target, evidence["file_path"])

    names = set(graph.nodes) | set(definitions)
    records: list[NodeRecord] = []
    for name in sorted(names):
        source_file = definitions.get(name) or evidence_files.get(name)
        records.append(
            NodeRecord(
                current_name=name,
                defined_in=relative_to_ingest_root(source_file, input_path) if source_file else None,
                source_file=source_file,
                columns_produced=sorted(produced[name]),
                columns_consumed=sorted(consumed[name]),
                upstream_tables=sorted(upstream[name]),
                downstream_tables=sorted(downstream[name]),
                source_types=sorted(source_types[name]),
                transform_types=sorted(transform_types[name]),
                confidence_min=min(confidences[name]) if confidences[name] else None,
                confidence_max=max(confidences[name]) if confidences[name] else None,
            )
        )
    return records
