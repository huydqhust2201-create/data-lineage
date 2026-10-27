"""So sánh thực nghiệm prompt v2 (table-level) vs v3 (column-level) trên các file
mà parser tĩnh fail — chạy LLM với cả hai prompt, áp đúng luật convert/dedup/
confidence của từng bản, và in split auto-confirm/HITL ở nhiều ngưỡng.

    python -m eval.compare_prompt_versions --dir samples/hospital --runs 2

Prompt v2 lấy từ git (`d72de8f~1:src/services/_llm_prompt_v2.txt`); v3 = file hiện
tại trong repo. Kết quả kèm ground-truth (nếu truyền `--gt`, file JSON dạng
{"<file_stem>": ["<src_table>", ...]}).

Kết quả 2026-08-28 trên `samples/hospital` (gpt-4o-mini, temp 0, 2 run) được lưu ở
`eval/results/prompt_v2_vs_v3_hospital.md`.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from src.config import get_settings
from src.services import llm_extraction_service as svc
from src.services.parser_service import SQLParserService

V2_GIT_REF = "d72de8f~1:src/services/_llm_prompt_v2.txt"
V3_PATH = Path("src/services/_llm_prompt_v3.txt")
THRESHOLDS = (0.5, 0.7, 0.8, 0.9)


def _load_v2_prompt() -> str:
    return subprocess.check_output(["git", "show", V2_GIT_REF], text=True, encoding="utf-8")


def _bare(name: str | None) -> str | None:
    if not name:
        return None
    name = name.strip().rsplit(".", 1)[-1].strip()
    return name or None


def _conf(raw: svc.RawEdge) -> float:
    rm = (raw.resolution_method or "").strip().lower()
    if rm:
        return svc.RESOLUTION_CONFIDENCE.get(rm, svc._DEFAULT_RESOLUTION_CONFIDENCE)
    return raw.confidence


def _call(prompt_text: str, sql: str, fname: str, dialect: str) -> svc.ExtractionResponse:
    svc._SYSTEM_PROMPT = prompt_text
    return svc._parse_response(svc._invoke_llm_with_retry(svc._build_prompt(sql, fname, dialect)))


def _convert(resp: svc.ExtractionResponse, dialect: str, *, columns: bool) -> list[dict]:
    """columns=False → luật v2 (khóa dedup (src,tgt)); columns=True → luật v3 (khóa đầy đủ)."""
    dedup: dict[tuple, tuple[float, str]] = {}
    for r in resp.edges:
        st = svc.normalize_table_name(r.source_table, dialect)
        tt = svc.normalize_table_name(r.target_table, dialect)
        if not st or not tt or svc.should_drop_edge(st, tt):
            continue
        sc = _bare(r.source_column) if columns else None
        tc = _bare(r.target_column) if columns else None
        key = (st, sc, tt, tc, r.transform_type) if columns else (st, tt)
        c = _conf(r)
        if key not in dedup or c > dedup[key][0]:
            dedup[key] = (c, (r.resolution_method or "").strip().lower())
    out = []
    for key, (c, rm) in dedup.items():
        if columns:
            out.append({"src": key[0], "sc": key[1], "tgt": key[2], "tc": key[3], "tt": key[4], "conf": c, "rm": rm})
        else:
            out.append({"src": key[0], "tgt": key[1], "conf": c, "rm": rm})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="samples/hospital", help="thư mục chứa .sql")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--gt", help="JSON ground-truth: {file_stem: [src_table,...]}")
    ap.add_argument("--out", help="ghi raw JSON per-run ra file này")
    args = ap.parse_args()

    dialect = get_settings().sql_dialect
    v2_prompt, v3_prompt = _load_v2_prompt(), V3_PATH.read_text(encoding="utf-8")
    gt: dict[str, set[str]] = {}
    if args.gt:
        gt = {k: set(v) for k, v in json.loads(Path(args.gt).read_text(encoding="utf-8")).items()}

    parser = SQLParserService(default_dialect=dialect)
    files = sorted(Path(args.dir).rglob("*.sql"))
    fallback = [f for f in files if not parser.parse_file_with_diagnostics(str(f))[0]]
    print(f"# {len(files)} file, {len(fallback)} đi LLM fallback: {', '.join(f.stem for f in fallback)}\n")

    raw_dump = []
    agg = {"v2": [], "v3": []}
    for f in fallback:
        sql = f.read_text(encoding="utf-8")
        row = {"file": f.stem, "runs": []}
        for _ in range(args.runs):
            r2, r3 = _call(v2_prompt, sql, f.stem, dialect), _call(v3_prompt, sql, f.stem, dialect)
            e2, e3 = _convert(r2, dialect, columns=False), _convert(r3, dialect, columns=True)
            row["runs"].append({"v2": e2, "v3": e3, "v2_unres": r2.unresolved, "v3_unres": r3.unresolved})
            agg["v2"].append((f.stem, e2))
            agg["v3"].append((f.stem, e3))
        raw_dump.append(row)

    if args.out:
        Path(args.out).write_text(json.dumps(raw_dump, ensure_ascii=False, indent=1), encoding="utf-8")

    for ver in ("v2", "v3"):
        total = sum(len(e) for _, e in agg[ver])
        rm = Counter(x["rm"] or "(none)" for _, edges in agg[ver] for x in edges)
        tp = fp = fn = 0
        for fname, edges in agg[ver]:
            g = gt.get(fname, set())
            preds = {e["src"] for e in edges}
            tp += len(preds & g)
            fp += len(preds - g)
            fn += len(g - preds)
        print(f"\n=== {ver.upper()} ===  edges={total}")
        for t in THRESHOLDS:
            c = sum(1 for _, edges in agg[ver] for e in edges if e["conf"] >= t)
            print(f"  ngưỡng {t}: auto-confirm {c:3d} / HITL {total - c:3d}  ({100*c/max(total,1):.0f}% auto)")
        if gt:
            p = tp / (tp + fp) if tp + fp else 1.0
            r = tp / (tp + fn) if tp + fn else 1.0
            print(f"  table-level vs GT: TP={tp} FP={fp} FN={fn}  P={p:.2f} R={r:.2f}")
        print(f"  resolution_method: {dict(rm)}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
