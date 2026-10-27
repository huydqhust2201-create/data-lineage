from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from fastapi import HTTPException

from src.services import storage_service, user_service
from src.services.user_service import User


@dataclass(frozen=True)
class Database:
    id: int
    owner_id: int
    name: str
    created_at: datetime


@dataclass(frozen=True)
class Member:
    user_id: int
    email: str
    display_name: str | None
    role: Literal["engineer", "viewer"]


def _database(record: storage_service.DatabaseRecord) -> Database:
    return Database(id=record.id, owner_id=record.owner_id, name=record.name, created_at=record.created_at)


def _member(record: storage_service.MemberRecord) -> Member:
    return Member(user_id=record.user_id, email=record.email, display_name=record.display_name, role=record.role)


def create_database(owner_id: int, name: str) -> Database | None:
    record = storage_service.create_database(owner_id, name)
    return _database(record) if record is not None else None


def get_database_for_owner_and_name(owner_id: int, name: str) -> Database | None:
    record = storage_service.get_database_by_owner_and_name(owner_id, name)
    return _database(record) if record is not None else None


def get_database(database_id: int) -> Database | None:
    record = storage_service.get_database_by_id(database_id)
    return _database(record) if record is not None else None


def list_databases_for_user(user_id: int) -> list[tuple[Database, Literal["engineer", "viewer"]]]:
    return [(_database(database), role) for database, role in storage_service.list_databases_for_user(user_id)]


def role_of(user: User, database_id: int) -> Literal["engineer", "viewer"] | None:
    database = storage_service.get_database_by_id(database_id)
    if database is None:
        return None
    if database.owner_id == user.id:
        return "engineer"
    return storage_service.get_member_role(database_id, user.id)


def ensure_database_owner(database_id: int, user: User) -> Database:
    record = storage_service.get_database_by_id(database_id)
    if record is None:
        raise HTTPException(status_code=404, detail="database not found")
    database = _database(record)
    if database.owner_id != user.id:
        raise HTTPException(status_code=403, detail="database owner required")
    return database


def list_members(database_id: int) -> list[Member]:
    return [_member(record) for record in storage_service.list_database_members(database_id)]


def upsert_member(database_id: int, user_id: int, role: Literal["engineer", "viewer"]) -> Member:
    database = storage_service.get_database_by_id(database_id)
    if database is None:
        raise HTTPException(status_code=404, detail="database not found")
    if database.owner_id == user_id:
        raise HTTPException(status_code=409, detail="database owner is already an engineer")
    if user_service.get_by_id(user_id) is None:
        raise HTTPException(status_code=404, detail="user not found")
    return _member(storage_service.upsert_database_member(database_id, user_id, role))


def remove_member(database_id: int, user_id: int) -> None:
    if not storage_service.delete_database_member(database_id, user_id):
        raise HTTPException(status_code=404, detail="database member not found")
