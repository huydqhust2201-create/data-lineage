import time
from uuid import uuid4

import jwt
import psycopg2
import pytest
from httpx import ASGITransport, AsyncClient

from src.config import get_settings
from src.main import app
from src.services import auth_service, storage_service


def _postgres_available() -> bool:
    try:
        conn = psycopg2.connect(get_settings().database_url, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


needs_postgres = pytest.mark.skipif(not _postgres_available(), reason="Postgres không sẵn sàng ở DATABASE_URL")


@pytest.mark.asyncio
async def test_missing_header_returns_401_for_every_existing_api_route(anon_client):
    requests = (
        ("post", "/api/v1/ingest", {"json": {"input_path": "unused"}}),
        ("post", "/api/v1/ingest/upload", {"files": {"files": ("model.sql", "select 1")}}),
        ("get", "/api/v1/pending-review", {}),
        ("post", "/api/v1/pending-review/missing/confirm", {}),
        ("post", "/api/v1/pending-review/missing/reject", {}),
        ("get", "/api/v1/descriptions/pending", {}),
        ("post", "/api/v1/descriptions/1/confirm", {}),
        ("post", "/api/v1/descriptions/1/reject", {}),
        ("put", "/api/v1/descriptions/1", {"json": {"description": "test"}}),
        ("get", "/api/v1/column-descriptions/pending", {}),
        ("post", "/api/v1/column-descriptions/1/id/confirm", {}),
        ("post", "/api/v1/column-descriptions/1/id/reject", {}),
        ("put", "/api/v1/column-descriptions/1/id", {"json": {"description": "test"}}),
        ("get", "/api/v1/impact/orders", {"params": {"direction": "downstream"}}),
        ("post", "/api/v1/chat", {"json": {"question": "lineage?"}}),
        ("get", "/api/v1/graph", {}),
        ("get", "/api/v1/databases", {}),
        ("post", "/api/v1/databases", {"json": {"name": "test"}}),
        ("delete", "/api/v1/graph", {}),
        ("get", "/api/v1/status", {}),
        ("get", "/api/v1/users", {}),
    )

    for method, path, kwargs in requests:
        response = await getattr(anon_client, method)(path, **kwargs)
        assert response.status_code == 401, path


@pytest.mark.asyncio
async def test_malformed_bearer_token_returns_401(anon_client):
    response = await anon_client.get("/api/v1/status", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_non_bearer_authorization_header_returns_401(anon_client):
    response = await anon_client.get("/api/v1/status", headers={"Authorization": "Basic abc"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_returns_401(seed_user):
    token = jwt.encode(
        {"sub": str(seed_user.id), "exp": int(time.time()) - 60},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}) as client:
        response = await client.get("/api/v1/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unknown_user_returns_401(seed_user):
    token = auth_service.create_access_token(999999)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}) as client:
        response = await client.get("/api/v1/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_returns_current_user(client, seed_user):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json() == {"id": seed_user.id, "email": seed_user.email, "display_name": seed_user.display_name}


@pytest.mark.asyncio
async def test_users_returns_only_public_fields(client):
    response = await client.get("/api/v1/users")
    assert response.status_code == 200
    assert response.json() == [{"id": 1, "email": "engineer@example.com", "display_name": "Engineer"}]


@pytest.mark.asyncio
async def test_users_now_requires_auth(anon_client):
    response = await anon_client.get("/api/v1/users")
    assert response.status_code == 401


@needs_postgres
@pytest.mark.asyncio
async def test_register_then_login_round_trip():
    email = f"register-{uuid4().hex}@example.com"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon:
        register = await anon.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password123", "display_name": "New User"},
        )
        assert register.status_code == 201
        body = register.json()
        assert body["user"]["email"] == email
        assert body["access_token"]

        login = await anon.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
        assert login.status_code == 200
        token = login.json()["access_token"]

        me = await anon.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == email

    with storage_service.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE email = %s", (email,))


@needs_postgres
@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409():
    email = f"dup-{uuid4().hex}@example.com"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon:
        first = await anon.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
        assert first.status_code == 201
        second = await anon.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
        assert second.status_code == 409

    with storage_service.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE email = %s", (email,))


@pytest.mark.asyncio
async def test_register_password_too_short_returns_422(anon_client):
    response = await anon_client.post(
        "/api/v1/auth/register",
        json={"email": f"short-{uuid4().hex}@example.com", "password": "short"},
    )
    assert response.status_code == 422


@needs_postgres
@pytest.mark.asyncio
async def test_login_wrong_password_returns_401():
    email = f"wrongpw-{uuid4().hex}@example.com"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon:
        await anon.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
        response = await anon.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
        assert response.status_code == 401

    with storage_service.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE email = %s", (email,))


@needs_postgres
@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(anon_client):
    response = await anon_client.post(
        "/api/v1/auth/login", json={"email": f"nobody-{uuid4().hex}@example.com", "password": "password123"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_google_login_with_invalid_token_returns_401(monkeypatch, anon_client):
    def _raise(_id_token: str):
        raise ValueError("invalid google id token")

    monkeypatch.setattr(auth_service, "verify_google_id_token", _raise)
    response = await anon_client.post("/api/v1/auth/google", json={"id_token": "garbage"})
    assert response.status_code == 401


@needs_postgres
@pytest.mark.asyncio
async def test_google_login_creates_new_user_and_is_idempotent(monkeypatch):
    email = f"google-{uuid4().hex}@example.com"
    google_sub = f"sub-{uuid4().hex}"
    monkeypatch.setattr(auth_service, "verify_google_id_token", lambda _t: (email, "Google User", google_sub))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon:
        first = await anon.post("/api/v1/auth/google", json={"id_token": "stub"})
        assert first.status_code == 200
        assert first.json()["user"]["email"] == email

        second = await anon.post("/api/v1/auth/google", json={"id_token": "stub"})
        assert second.status_code == 200
        assert second.json()["user"]["id"] == first.json()["user"]["id"]

    with storage_service.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE email = %s", (email,))
