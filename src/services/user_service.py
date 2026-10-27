from dataclasses import dataclass

from src.services import storage_service


@dataclass(frozen=True)
class User:
    id: int
    email: str
    display_name: str | None


@dataclass(frozen=True)
class UserWithCredentials:
    """Dùng nội bộ cho auth_service — KHÔNG dùng làm response model của route
    nào (khác User, dataclass này mang password_hash)."""

    id: int
    email: str
    display_name: str | None
    password_hash: str | None
    google_sub: str | None


def _to_user(record: storage_service.UserRecord) -> User:
    return User(id=record.id, email=record.email, display_name=record.display_name)


def _to_user_with_credentials(record: storage_service.UserRecord) -> UserWithCredentials:
    return UserWithCredentials(
        id=record.id,
        email=record.email,
        display_name=record.display_name,
        password_hash=record.password_hash,
        google_sub=record.google_sub,
    )


def get_by_id(user_id: int) -> User | None:
    record = storage_service.get_user_by_id(user_id)
    return _to_user(record) if record is not None else None


def list_users() -> list[User]:
    return [_to_user(record) for record in storage_service.list_users()]


def ensure_user(email: str, display_name: str | None) -> User:
    return _to_user(storage_service.upsert_user(email, display_name))


def get_by_email_with_credentials(email: str) -> UserWithCredentials | None:
    record = storage_service.get_user_by_email(email)
    return _to_user_with_credentials(record) if record is not None else None


def get_by_google_sub(google_sub: str) -> UserWithCredentials | None:
    record = storage_service.get_user_by_google_sub(google_sub)
    return _to_user_with_credentials(record) if record is not None else None


def register(email: str, display_name: str | None, password_hash: str) -> User | None:
    record = storage_service.create_user_with_password(email, display_name, password_hash)
    return _to_user(record) if record is not None else None


def link_google(user_id: int, google_sub: str) -> User:
    return _to_user(storage_service.link_google_account(user_id, google_sub))


def set_password(user_id: int, password_hash: str) -> User:
    return _to_user(storage_service.set_user_password(user_id, password_hash))
