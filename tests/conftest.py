from unittest.mock import AsyncMock
from uuid import uuid4

import psycopg2
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.config import get_settings
from src.main import app
from src.services import auth_service, chat_service, database_service, storage_service, user_service


@pytest.fixture(autouse=True)
def isolate_chat_traces(monkeypatch, tmp_path):
    """Keep runtime chat traces out of the repository during every test."""
    monkeypatch.setattr(chat_service, "CHAT_TRACE_DIR", tmp_path / "chat-traces")


def _bearer_headers(user_id: int) -> dict[str, str]:
    """Mint 1 JWT test thật qua auth_service — dùng đúng path production thay
    vì tự chế header X-User-Id (bỏ hẳn từ khi current_user() chỉ còn chấp
    nhận Authorization: Bearer <jwt>)."""
    return {"Authorization": f"Bearer {auth_service.create_access_token(user_id)}"}


@pytest_asyncio.fixture
async def seed_user(monkeypatch):
    user = user_service.User(id=1, email="engineer@example.com", display_name="Engineer")
    monkeypatch.setattr(user_service, "get_by_id", lambda user_id: user if user_id == user.id else None)
    monkeypatch.setattr(user_service, "list_users", lambda: [user])
    monkeypatch.setattr(database_service, "get_database", lambda _database_id: object())
    monkeypatch.setattr(database_service, "role_of", lambda candidate, _database_id: "engineer" if candidate.id == user.id else None)
    return user


@pytest_asyncio.fixture
async def client(seed_user):
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=_bearer_headers(seed_user.id),
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def anon_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def tenant():
    """Real Postgres tenant used by the Phase-2 organization API tests."""
    suffix = uuid4().hex
    owner = user_service.ensure_user(f"owner-{suffix}@example.com", "Owner")
    invited_engineer = user_service.ensure_user(f"engineer-{suffix}@example.com", "Engineer")
    viewer = user_service.ensure_user(f"viewer-{suffix}@example.com", "Viewer")
    outsider = user_service.ensure_user(f"outsider-{suffix}@example.com", "Outsider")
    other_owner = user_service.ensure_user(f"other-{suffix}@example.com", "Other owner")

    database = database_service.create_database(owner.id, "analytics")
    assert database is not None
    database_service.upsert_member(database.id, invited_engineer.id, "engineer")
    database_service.upsert_member(database.id, viewer.id, "viewer")

    other_database = database_service.create_database(other_owner.id, "analytics")
    assert other_database is not None

    result = {
        "owner": owner,
        "invited_engineer": invited_engineer,
        "viewer": viewer,
        "outsider": outsider,
        "other_owner": other_owner,
        "database": database,
        "other_database": other_database,
    }
    yield result

    with storage_service.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM users WHERE id = ANY(%s)",
                ([user.id for user in (owner, invited_engineer, viewer, outsider, other_owner)],),
        )


@pytest.fixture
def database_id() -> int:
    """Return the seeded engineer's default database, regardless of other users' databases."""
    try:
        conn = psycopg2.connect(get_settings().database_url)
    except psycopg2.OperationalError:
        return 1
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.id FROM databases d JOIN users u ON u.id = d.owner_id "
                "WHERE u.email = %s AND d.name = %s",
                ("engineer@example.com", "default"),
            )
            row = cur.fetchone()
        assert row is not None, "Seeded engineer default database is required for tests"
        return int(row[0])
    finally:
        conn.close()


@pytest_asyncio.fixture
async def engineer_client(tenant):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=_bearer_headers(tenant["owner"].id),
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def viewer_client(tenant):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=_bearer_headers(tenant["viewer"].id),
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def outsider_client(tenant):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=_bearer_headers(tenant["outsider"].id),
    ) as ac:
        yield ac


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock
