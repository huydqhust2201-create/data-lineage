from datetime import UTC, datetime, timedelta

import pytest

from src.services import ingest_watcher


def _run_record(input_path: str, started_at: datetime):
    return type(
        "FakeRun",
        (),
        {"input_path": input_path, "started_at": started_at},
    )()


def test_has_sql_file_changed_since_true_when_file_newer(tmp_path):
    sql_file = tmp_path / "model.sql"
    sql_file.write_text("select 1", encoding="utf-8")
    since = datetime.now(UTC) - timedelta(hours=1)

    assert ingest_watcher._has_sql_file_changed_since(str(tmp_path), since) is True


def test_has_sql_file_changed_since_false_when_file_older(tmp_path):
    sql_file = tmp_path / "model.sql"
    sql_file.write_text("select 1", encoding="utf-8")
    since = datetime.now(UTC) + timedelta(hours=1)

    assert ingest_watcher._has_sql_file_changed_since(str(tmp_path), since) is False


def test_has_sql_file_changed_since_false_when_path_missing(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert ingest_watcher._has_sql_file_changed_since(str(missing), datetime.now(UTC)) is False


@pytest.mark.asyncio
async def test_check_and_reingest_skips_database_with_no_runs(monkeypatch):
    monkeypatch.setattr(ingest_watcher.storage_service, "list_all_database_ids", lambda: [1])
    monkeypatch.setattr(ingest_watcher.storage_service, "list_ingest_runs", lambda database_id, limit=1: [])
    called = []
    monkeypatch.setattr(ingest_watcher.ingest_service, "run_ingest", lambda *a, **k: called.append(a))

    result = await ingest_watcher.check_and_reingest_stale_paths()

    assert result == []
    assert called == []


@pytest.mark.asyncio
async def test_check_and_reingest_skips_when_path_no_longer_exists(monkeypatch, tmp_path):
    missing_path = str(tmp_path / "deleted-upload-dir")
    monkeypatch.setattr(ingest_watcher.storage_service, "list_all_database_ids", lambda: [1])
    monkeypatch.setattr(
        ingest_watcher.storage_service,
        "list_ingest_runs",
        lambda database_id, limit=1: [_run_record(missing_path, datetime.now(UTC) - timedelta(hours=1))],
    )
    called = []
    monkeypatch.setattr(ingest_watcher.ingest_service, "run_ingest", lambda *a, **k: called.append(a))

    result = await ingest_watcher.check_and_reingest_stale_paths()

    assert result == []
    assert called == []


@pytest.mark.asyncio
async def test_check_and_reingest_skips_when_no_file_changed(monkeypatch, tmp_path):
    (tmp_path / "model.sql").write_text("select 1", encoding="utf-8")
    started_at = datetime.now(UTC) + timedelta(hours=1)  # file is older than this
    monkeypatch.setattr(ingest_watcher.storage_service, "list_all_database_ids", lambda: [1])
    monkeypatch.setattr(
        ingest_watcher.storage_service,
        "list_ingest_runs",
        lambda database_id, limit=1: [_run_record(str(tmp_path), started_at)],
    )
    called = []
    monkeypatch.setattr(ingest_watcher.ingest_service, "run_ingest", lambda *a, **k: called.append(a))

    result = await ingest_watcher.check_and_reingest_stale_paths()

    assert result == []
    assert called == []


@pytest.mark.asyncio
async def test_check_and_reingest_reingests_when_file_changed(monkeypatch, tmp_path):
    (tmp_path / "model.sql").write_text("select 1", encoding="utf-8")
    started_at = datetime.now(UTC) - timedelta(hours=1)  # file is newer than this
    monkeypatch.setattr(ingest_watcher.storage_service, "list_all_database_ids", lambda: [1])
    monkeypatch.setattr(
        ingest_watcher.storage_service,
        "list_ingest_runs",
        lambda database_id, limit=1: [_run_record(str(tmp_path), started_at)],
    )
    called = []

    async def fake_run_ingest(input_path, database_id, user_id):
        called.append((input_path, database_id, user_id))

    monkeypatch.setattr(ingest_watcher.ingest_service, "run_ingest", fake_run_ingest)

    result = await ingest_watcher.check_and_reingest_stale_paths()

    assert result == [{"database_id": 1, "input_path": str(tmp_path)}]
    assert called == [(str(tmp_path), 1, None)]


@pytest.mark.asyncio
async def test_check_and_reingest_continues_after_one_database_fails(monkeypatch, tmp_path):
    (tmp_path / "model.sql").write_text("select 1", encoding="utf-8")
    started_at = datetime.now(UTC) - timedelta(hours=1)
    monkeypatch.setattr(ingest_watcher.storage_service, "list_all_database_ids", lambda: [1, 2])

    def fake_list_runs(database_id, limit=1):
        return [_run_record(str(tmp_path), started_at)]

    monkeypatch.setattr(ingest_watcher.storage_service, "list_ingest_runs", fake_list_runs)

    calls = []

    async def fake_run_ingest(input_path, database_id, user_id):
        calls.append(database_id)
        if database_id == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(ingest_watcher.ingest_service, "run_ingest", fake_run_ingest)

    result = await ingest_watcher.check_and_reingest_stale_paths()

    assert calls == [1, 2]
    assert result == [{"database_id": 2, "input_path": str(tmp_path)}]
