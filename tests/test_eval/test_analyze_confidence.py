import json
from pathlib import Path

import pytest

from eval import analyze_confidence as analyzer
from eval import run_extraction_eval as runner
from src.services.llm_extraction_service import ExtractionResponse, RawEdge

MODEL = "test/model"
DIALECT = "postgres"


def snapshot_tree(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def make_fixtures(tmp_path: Path) -> Path:
    root = tmp_path / "fixtures"
    (root / "sql").mkdir(parents=True)
    (root / "expected").mkdir()
    (root / "sql" / "tp.sql").write_text("select * from raw.orders", encoding="utf-8")
    (root / "expected" / "tp.json").write_text(
        json.dumps(
            {
                "description": "expected source",
                "expected_edges": [{"source_table": "raw.orders", "target_table": "tp"}],
            }
        ),
        encoding="utf-8",
    )
    (root / "sql" / "fp.sql").write_text("select * from raw.customers", encoding="utf-8")
    (root / "expected" / "fp.json").write_text(
        json.dumps({"description": "refusal", "expected_edges": []}), encoding="utf-8"
    )
    return root


def seed_cache(cache_dir: Path, fixtures: Path, name: str, response: ExtractionResponse) -> Path:
    sql_text = (fixtures / "sql" / f"{name}.sql").read_text(encoding="utf-8")
    path = runner._cache_path(cache_dir, sql_text, name, DIALECT, MODEL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "fixture": name,
                "model": MODEL,
                "dialect": DIALECT,
                "prompt_version": analyzer.PROMPT_VERSION,
                "response": response.model_dump(),
            }
        ),
        encoding="utf-8",
    )
    return path


def run_args(fixtures: Path, cache_dir: Path, thresholds: str = "0.5,0.6,0.7") -> list[str]:
    return [
        "--fixtures",
        str(fixtures),
        "--cache-dir",
        str(cache_dir),
        "--model",
        MODEL,
        "--dialect",
        DIALECT,
        "--thresholds",
        thresholds,
    ]


def test_lists_edges_classifies_tp_fp_and_reports_bands(tmp_path, capsys):
    fixtures = make_fixtures(tmp_path)
    cache = tmp_path / "cache"
    seed_cache(
        cache,
        fixtures,
        "tp",
        ExtractionResponse(edges=[RawEdge(source_table="raw.orders", target_table="tp", confidence=0.5)]),
    )
    seed_cache(
        cache,
        fixtures,
        "fp",
        ExtractionResponse(edges=[RawEdge(source_table="raw.customers", target_table="fp", confidence=0.7)]),
    )
    assert analyzer.run(run_args(fixtures, cache)) == 0
    output = capsys.readouterr().out
    assert "| 0.50 | tp | TP | raw.orders -> tp |" in output
    assert "| 0.70 | fp | FP | raw.customers -> fp |" in output
    assert "edges in [0.6, 0.7): 0" in output
    assert "correctly-predicted (TP) edges in [0.5, 0.7): 1" in output


def test_reports_selected_experiment_and_distribution(tmp_path, capsys):
    fixtures = make_fixtures(tmp_path)
    cache = tmp_path / "cache"
    seed_cache(
        cache,
        fixtures,
        "tp",
        ExtractionResponse(edges=[RawEdge(source_table="raw.orders", target_table="tp", confidence=0.5)]),
    )
    seed_cache(
        cache,
        fixtures,
        "fp",
        ExtractionResponse(edges=[RawEdge(source_table="raw.customers", target_table="fp", confidence=0.7)]),
    )
    assert analyzer.run(run_args(fixtures, cache)) == 0
    output = capsys.readouterr().out
    assert f"Model: {MODEL}" in output
    assert f"Dialect: {DIALECT}" in output
    assert f"Prompt version: {analyzer.PROMPT_VERSION}" in output
    assert "Accepted cache entries: 2" in output
    assert "0.50: 1" in output and "0.70: 1" in output


def test_tp_band_count_excludes_false_positive(tmp_path, capsys):
    fixtures = make_fixtures(tmp_path)
    cache = tmp_path / "cache"
    seed_cache(cache, fixtures, "tp", ExtractionResponse())
    seed_cache(
        cache,
        fixtures,
        "fp",
        ExtractionResponse(edges=[RawEdge(source_table="raw.customers", target_table="fp", confidence=0.5)]),
    )
    assert analyzer.run(run_args(fixtures, cache)) == 0
    assert "correctly-predicted (TP) edges in [0.5, 0.7): 0" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("confidence", "expect_warning"),
    [(0.5, True), (0.65, False)],
)
def test_threshold_indistinguishability_warning(tmp_path, capsys, confidence, expect_warning):
    fixtures = make_fixtures(tmp_path)
    cache = tmp_path / "cache"
    seed_cache(
        cache,
        fixtures,
        "tp",
        ExtractionResponse(edges=[RawEdge(source_table="raw.orders", target_table="tp", confidence=confidence)]),
    )
    seed_cache(cache, fixtures, "fp", ExtractionResponse())
    assert analyzer.run(run_args(fixtures, cache)) == 0
    output = capsys.readouterr().out
    warning = "THRESHOLDS 0.6 AND 0.7 ARE INDISTINGUISHABLE"
    assert (warning in output) is expect_warning


@pytest.mark.parametrize("field", ["model", "dialect", "prompt_version"])
def test_rejects_metadata_mismatch(tmp_path, capsys, field):
    fixtures = make_fixtures(tmp_path)
    cache = tmp_path / "cache"
    cache_path = seed_cache(cache, fixtures, "tp", ExtractionResponse())
    seed_cache(cache, fixtures, "fp", ExtractionResponse())
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload[field] = "wrong-value"
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    assert analyzer.run(run_args(fixtures, cache)) == 1
    assert field in capsys.readouterr().err


def test_cache_miss_is_read_only_and_never_calls_extractor(monkeypatch, tmp_path, capsys):
    fixtures = make_fixtures(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    before_cache = snapshot_tree(cache)
    before_fixtures = snapshot_tree(fixtures)
    monkeypatch.setattr(runner, "extract_raw", lambda *_args, **_kwargs: pytest.fail("LLM called"))
    assert analyzer.run(run_args(fixtures, cache)) == 1
    assert "Re-run the evaluator with --live" in capsys.readouterr().err
    assert snapshot_tree(cache) == before_cache
    assert snapshot_tree(fixtures) == before_fixtures


def test_cache_miss_names_all_missing_fixtures(tmp_path, capsys):
    fixtures = make_fixtures(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    assert analyzer.run(run_args(fixtures, cache)) == 1
    output = capsys.readouterr().err
    assert "tp" in output and "fp" in output


def test_analyzer_cache_key_matches_runner(tmp_path):
    cache = tmp_path / "cache"
    assert analyzer._cache_path(cache, "sql", "name", DIALECT, MODEL) == runner._cache_path(
        cache, "sql", "name", DIALECT, MODEL
    )


def test_success_is_read_only(tmp_path):
    fixtures = make_fixtures(tmp_path)
    cache = tmp_path / "cache"
    seed_cache(cache, fixtures, "tp", ExtractionResponse())
    seed_cache(cache, fixtures, "fp", ExtractionResponse())
    before_cache = snapshot_tree(cache)
    before_fixtures = snapshot_tree(fixtures)
    assert analyzer.run(run_args(fixtures, cache)) == 0
    assert snapshot_tree(cache) == before_cache
    assert snapshot_tree(fixtures) == before_fixtures
