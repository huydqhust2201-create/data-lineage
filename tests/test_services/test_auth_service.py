import time

import jwt
import pytest

from src.config import get_settings
from src.services import auth_service


def test_hash_password_round_trip():
    password_hash = auth_service.hash_password("correct-horse")
    assert auth_service.verify_password("correct-horse", password_hash)


def test_verify_password_rejects_wrong_password():
    password_hash = auth_service.hash_password("correct-horse")
    assert not auth_service.verify_password("wrong-password", password_hash)


def test_create_and_decode_access_token_round_trip():
    token = auth_service.create_access_token(42)
    assert auth_service.decode_access_token(token) == 42


def test_decode_access_token_rejects_garbage():
    assert auth_service.decode_access_token("not-a-jwt") is None


def test_decode_access_token_rejects_expired_token():
    token = jwt.encode(
        {"sub": "1", "exp": int(time.time()) - 60},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    assert auth_service.decode_access_token(token) is None


def test_decode_access_token_rejects_tampered_signature():
    token = jwt.encode(
        {"sub": "1", "exp": int(time.time()) + 3600},
        "a-different-secret-entirely",
        algorithm="HS256",
    )
    assert auth_service.decode_access_token(token) is None


def test_verify_google_id_token_raises_on_invalid_token(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise ValueError("bad token")

    monkeypatch.setattr(auth_service.google_id_token, "verify_oauth2_token", _raise)
    with pytest.raises(ValueError):
        auth_service.verify_google_id_token("garbage")


def test_verify_google_id_token_returns_email_name_sub(monkeypatch):
    claims = {"email": "user@example.com", "name": "A User", "sub": "google-sub-123", "email_verified": True}
    monkeypatch.setattr(auth_service.google_id_token, "verify_oauth2_token", lambda *_a, **_k: claims)
    email, name, google_sub = auth_service.verify_google_id_token("stub-token")
    assert email == "user@example.com"
    assert name == "A User"
    assert google_sub == "google-sub-123"


def test_verify_google_id_token_rejects_unverified_email(monkeypatch):
    claims = {"email": "user@example.com", "name": "A User", "sub": "google-sub-123", "email_verified": False}
    monkeypatch.setattr(auth_service.google_id_token, "verify_oauth2_token", lambda *_a, **_k: claims)
    with pytest.raises(ValueError):
        auth_service.verify_google_id_token("stub-token")
