import json

import pytest

from eval import run_extraction_eval as runner
from src.services.llm_extraction_service import ExtractionResponse, RawEdge


def make_fixtures(tmp_path, expected_text=None):
    root = tmp_path / "fixtures"
    (root / "sql").mkdir(parents=True)
    (root / "expected").mkdir()
    (root / "sql" / "case.sql").write_text("select * from raw.orders", encoding="utf-8")
    expected = expected_text or json.dumps({"expected_edges": [{"source_table": "raw.orders", "target_table": "case"}]})
    (root / "expected" / "case.json").write_text(expected, encoding="utf-8")
    return root


def test_cache_miss_requires_live(tmp_path, capsys):
    fixtures = make_fixtures(tmp_path)
    assert runner.main(["--fixtures", str(fixtures), "--cache-dir", str(tmp_path / "cache")]) == 1
    output = capsys.readouterr().err
    assert "case" in output and "--live" in output


def test_cache_hit_never_calls_extractor(monkeypatch, tmp_path):
    fixtures = make_fixtures(tmp_path)
    sql = (fixtures / "sql" / "case.sql").read_text(encoding="utf-8")
    cache = tmp_path / "cache"
    settings = runner.get_settings()
    path = runner._cache_path(cache, sql, "case", settings.sql_dialect, settings.model_name)
    path.parent.mkdir()
    path.write_text(
        json.dumps({"response": {"edges": [{"source_table": "raw.orders", "target_table": "case"}]}}), encoding="utf-8"
    )
    monkeypatch.setattr(runner, "extract_raw", lambda *_args, **_kwargs: pytest.fail("extractor called"))
    report = tmp_path / "report.md"
    assert runner.main(["--fixtures", str(fixtures), "--cache-dir", str(cache), "--out", str(report), "--live"]) == 0
    assert "Fixture sources: `1 cache hits, 0 live queries`" in report.read_text(encoding="utf-8")


def test_cache_key_changes_for_each_prompt_input(tmp_path):
    cache = tmp_path / "cache"
    base = runner._cache_path(cache, "select 1", "orders_daily", "postgres", "model-a")
    assert base != runner._cache_path(cache, "select 1", "orders_weekly", "postgres", "model-a")
    assert base != runner._cache_path(cache, "select 1", "orders_daily", "snowflake", "model-a")
    assert base != runner._cache_path(cache, "select 1", "orders_daily", "postgres", "model-b")


def test_report_has_valid_fixture_table_sources_and_refusal_diagnostic(monkeypatch, tmp_path):
    fixtures = make_fixtures(tmp_path, json.dumps({"expected_edges": []}))
    response = ExtractionResponse()
    monkeypatch.setattr(runner, "extract_raw", lambda *_args, **_kwargs: response)
    report = tmp_path / "report.md"
    assert (
        runner.main(
            ["--fixtures", str(fixtures), "--cache-dir", str(tmp_path / "cache"), "--out", str(report), "--live"]
        )
        == 0
    )
    text = report.read_text(encoding="utf-8")
    assert "| Fixture | Source |" in text
    assert "| case | live |" in text
    assert "No-hallucination fixtures: 1/1 correct" in text
    assert "Run mode:" not in text


def test_no_hallucination_headline_counts_hallucinated_empty_expected_fixture(tmp_path):
    fixtures = tmp_path / "fixtures"
    sql_dir = fixtures / "sql"
    expected_dir = fixtures / "expected"
    sql_dir.mkdir(parents=True)
    expected_dir.mkdir()
    for name in ("correct_refusal", "hallucinated_refusal"):
        (sql_dir / f"{name}.sql").write_text("select 1", encoding="utf-8")
        (expected_dir / f"{name}.json").write_text(json.dumps({"expected_edges": []}), encoding="utf-8")

    cache = tmp_path / "cache"
    settings = runner.get_settings()
    responses = {
        "correct_refusal": ExtractionResponse(),
        "hallucinated_refusal": ExtractionResponse(
            edges=[RawEdge(source_table="raw.orders", target_table="fct_sales")]
        ),
    }
    for name, response in responses.items():
        sql_text = (sql_dir / f"{name}.sql").read_text(encoding="utf-8")
        path = runner._cache_path(cache, sql_text, name, settings.sql_dialect, settings.model_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"response": response.model_dump()}), encoding="utf-8")

    report = tmp_path / "report.md"
    assert runner.main(["--fixtures", str(fixtures), "--cache-dir", str(cache), "--out", str(report)]) == 0
    assert "No-hallucination fixtures: 1/2 correct" in report.read_text(encoding="utf-8")


def test_live_cache_write_round_trips(monkeypatch, tmp_path):
    fixtures = make_fixtures(tmp_path)
    response = ExtractionResponse(edges=[RawEdge(source_table="raw.orders", target_table="case")])
    monkeypatch.setattr(runner, "extract_raw", lambda *_args, **_kwargs: response)
    cache = tmp_path / "cache"
    assert (
        runner.main(
            ["--fixtures", str(fixtures), "--cache-dir", str(cache), "--out", str(tmp_path / "report.md"), "--live"]
        )
        == 0
    )
    payload = json.loads(next(cache.glob("*.json")).read_text(encoding="utf-8"))
    assert ExtractionResponse.model_validate(payload["response"]) == response


def test_malformed_expected_and_refresh_requirements(tmp_path, capsys):
    fixtures = make_fixtures(tmp_path, "not json")
    assert runner.main(["--fixtures", str(fixtures), "--cache-dir", str(tmp_path / "cache")]) == 1
    assert "Malformed expected fixture" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        runner.main(["--refresh"])
