"""Hash mật khẩu, phát/kiểm JWT phiên đăng nhập, và xác minh Google ID token.

Nơi duy nhất chứa logic bảo mật của auth — không tự viết logic verify chữ ký
JWKS của Google, dùng thư viện `google-auth` chính chủ cho việc đó vì đây là
loại code sai một chút là mất an toàn ngay.
"""

from __future__ import annotations

import time

import bcrypt
import jwt
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from src.config import get_settings

_JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "exp": int(time.time()) + settings.jwt_expires_minutes * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[_JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def verify_google_id_token(id_token_str: str) -> tuple[str, str | None, str]:
    """Xác minh chữ ký/aud/iss/exp của Google ID token. Trả (email, name, google_sub).

    Raise ValueError nếu token không hợp lệ.
    """
    try:
        claims = google_id_token.verify_oauth2_token(
            id_token_str, google_requests.Request(), audience=get_settings().google_client_id
        )
    except (GoogleAuthError, ValueError) as exc:
        raise ValueError("invalid google id token") from exc

    email = claims.get("email")
    google_sub = claims.get("sub")
    if not email or not google_sub:
        raise ValueError("google id token missing email/sub")
    if not claims.get("email_verified", False):
        raise ValueError("google email not verified")
    return email, claims.get("name"), google_sub
