from uuid import uuid4

import psycopg2
import pytest

from src.config import get_settings
from src.services import storage_service


def _postgres_available() -> bool:
    try:
        conn = psycopg2.connect(get_settings().database_url, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="Postgres không sẵn sàng ở DATABASE_URL")


@pytest.fixture
def email():
    """Email ngẫu nhiên, tự dọn dẹp sau test — bảng users KHÔNG bị wipe như
    lineage_edges/lineage_nodes (test này không cần PYTEST_ALLOW_DB_WIPE)."""
    value = f"storage-test-{uuid4().hex}@example.com"
    yield value
    with storage_service.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE email = %s", (value,))


def test_create_user_with_password_then_lookup_by_email(email):
    created = storage_service.create_user_with_password(email, "Test User", "hashed-value")
    assert created is not None
    assert created.email == email
    assert created.password_hash == "hashed-value"
    assert created.google_sub is None

    found = storage_service.get_user_by_email(email)
    assert found == created


def test_create_user_with_password_returns_none_on_duplicate_email(email):
    first = storage_service.create_user_with_password(email, "Test User", "hash-1")
    assert first is not None
    second = storage_service.create_user_with_password(email, "Someone Else", "hash-2")
    assert second is None

    # Đăng ký trùng không được ghi đè mật khẩu của tài khoản đã có.
    unchanged = storage_service.get_user_by_email(email)
    assert unchanged.password_hash == "hash-1"


def test_get_user_by_email_returns_none_when_missing():
    assert storage_service.get_user_by_email(f"missing-{uuid4().hex}@example.com") is None


def test_link_google_account_sets_google_sub_and_is_findable(email):
    created = storage_service.create_user_with_password(email, "Test User", "hash")
    google_sub = f"sub-{uuid4().hex}"

    linked = storage_service.link_google_account(created.id, google_sub)
    assert linked.google_sub == google_sub

    found = storage_service.get_user_by_google_sub(google_sub)
    assert found.id == created.id


def test_get_user_by_google_sub_returns_none_when_missing():
    assert storage_service.get_user_by_google_sub(f"missing-sub-{uuid4().hex}") is None


def test_set_user_password_updates_hash(email):
    created = storage_service.create_user_with_password(email, "Test User", "old-hash")
    updated = storage_service.set_user_password(created.id, "new-hash")
    assert updated.password_hash == "new-hash"
