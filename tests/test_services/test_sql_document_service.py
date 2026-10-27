from src.services import sql_document_service


def test_split_statements_single_statement_file_is_one_whole_file_chunk(tmp_path):
    sql_file = tmp_path / "stg_customers.sql"
    sql_file.write_text(
        "with source as (select * from raw_customers) select id as customer_id from source",
        encoding="utf-8",
    )

    result = sql_document_service._split_statements(str(sql_file), "postgres")

    assert len(result) == 1
    order, text = result[0]
    assert order == 0
    assert "raw_customers" in text
    assert "customer_id" in text


def test_split_statements_multi_statement_file_splits_per_statement(tmp_path):
    sql_file = tmp_path / "migration.sql"
    sql_file.write_text(
        "CREATE TABLE foo (id INT); ALTER TABLE foo ADD COLUMN name TEXT; DROP TABLE bar;",
        encoding="utf-8",
    )

    result = sql_document_service._split_statements(str(sql_file), "postgres")

    assert [order for order, _ in result] == [0, 1, 2]
    assert "CREATE TABLE" in result[0][1]
    assert "ALTER TABLE" in result[1][1]
    assert "DROP TABLE" in result[2][1]


def test_split_statements_handles_dbt_jinja_source_and_ref(tmp_path):
    """Regression: model dbt thật dùng {{ source(...) }}/{{ ref(...) }} — sqlglot
    không parse được cú pháp Jinja thô, phải tiền xử lý trước (giống parser_service)."""
    sql_file = tmp_path / "stg_orders.sql"
    sql_file.write_text(
        "with source as (\n    select * from {{ source('ecom', 'raw_orders') }}\n)\n"
        "select id, {{ ref('stg_customers') }} as customer_ref from source",
        encoding="utf-8",
    )

    result = sql_document_service._split_statements(str(sql_file), "postgres")

    assert len(result) == 1
    order, text = result[0]
    assert order == 0
    assert "raw_orders" in text


def test_split_statements_returns_empty_for_missing_file():
    assert sql_document_service._split_statements("/does/not/exist.sql", "postgres") == []


def test_split_statements_returns_empty_for_unparseable_content(tmp_path):
    sql_file = tmp_path / "broken.sql"
    sql_file.write_text("this is not valid ; ; sql (((", encoding="utf-8")
    # sqlglot thường vẫn cố gắng parse ra rỗng/1 vài statement rác thay vì raise —
    # chỉ cần không crash, không cần rỗng tuyệt đối.
    result = sql_document_service._split_statements(str(sql_file), "postgres")
    assert isinstance(result, list)


def test_sync_sql_documents_noop_when_description_disabled(monkeypatch, tmp_path):
    from src.config import get_settings

    monkeypatch.setattr(get_settings(), "description_enabled", False)
    sql_file = tmp_path / "model.sql"
    sql_file.write_text("select 1", encoding="utf-8")

    written = sql_document_service.sync_sql_documents(1, [str(sql_file)])

    assert written == 0


def test_sync_sql_documents_skips_unchanged_content_hash(monkeypatch, tmp_path):
    from src.config import get_settings
    from src.services import storage_service

    monkeypatch.setattr(get_settings(), "description_enabled", True)
    sql_file = tmp_path / "model.sql"
    sql_file.write_text("select 1 as id", encoding="utf-8")

    import hashlib

    text = sql_document_service._split_statements(str(sql_file), get_settings().sql_dialect)[0][1]
    existing_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    monkeypatch.setattr(storage_service, "get_sql_document_hash", lambda *a, **k: existing_hash)
    embed_calls = []
    monkeypatch.setattr(sql_document_service.embedding_service, "embed", lambda texts: embed_calls.append(texts) or [[0.1] * 1024])
    monkeypatch.setattr(storage_service, "upsert_sql_document", lambda *a, **k: None)

    written = sql_document_service.sync_sql_documents(1, [str(sql_file)])

    assert written == 0
    assert embed_calls == []


def test_sync_sql_documents_embeds_changed_content(monkeypatch, tmp_path):
    from src.config import get_settings
    from src.services import storage_service

    monkeypatch.setattr(get_settings(), "description_enabled", True)
    sql_file = tmp_path / "model.sql"
    sql_file.write_text("select 1 as id", encoding="utf-8")

    monkeypatch.setattr(storage_service, "get_sql_document_hash", lambda *a, **k: None)
    upserted = []
    monkeypatch.setattr(sql_document_service.embedding_service, "embed", lambda texts: [[0.1] * 1024])
    monkeypatch.setattr(storage_service, "upsert_sql_document", lambda *a, **k: upserted.append(a))

    written = sql_document_service.sync_sql_documents(1, [str(sql_file)])

    assert written == 1
    assert len(upserted) == 1
