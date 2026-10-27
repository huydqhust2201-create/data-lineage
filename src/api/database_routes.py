from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status

from src.api.deps import current_user, require_database_owner_path
from src.models.schemas import (
    DatabaseCreateRequest,
    DatabaseResponse,
    MemberResponse,
    MemberUpsertRequest,
)
from src.services import database_service
from src.services.user_service import User

router = APIRouter()


def _database_response(
    database: database_service.Database, role: Literal["engineer", "viewer"]
) -> DatabaseResponse:
    return DatabaseResponse(**database.__dict__, role=role)


def _member_response(member: database_service.Member) -> MemberResponse:
    return MemberResponse(**member.__dict__)


@router.get("/databases", response_model=list[DatabaseResponse])
def list_databases(user: User = Depends(current_user)) -> list[DatabaseResponse]:
    return [_database_response(database, role) for database, role in database_service.list_databases_for_user(user.id)]


@router.post(
    "/databases",
    response_model=DatabaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_database(
    request: DatabaseCreateRequest,
    user: User = Depends(current_user),
) -> DatabaseResponse:
    database = database_service.create_database(user.id, request.name)
    if database is None:
        raise HTTPException(status_code=409, detail="database name already exists for user")
    return _database_response(database, "engineer")


@router.get("/databases/{database_id}/members", response_model=list[MemberResponse])
def list_members(database: database_service.Database = Depends(require_database_owner_path())) -> list[MemberResponse]:
    return [_member_response(member) for member in database_service.list_members(database.id)]


@router.post("/databases/{database_id}/members", response_model=MemberResponse)
def upsert_member(
    request: MemberUpsertRequest,
    database: database_service.Database = Depends(require_database_owner_path()),
) -> MemberResponse:
    return _member_response(database_service.upsert_member(database.id, request.user_id, request.role))


@router.delete("/databases/{database_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    user_id: int,
    database: database_service.Database = Depends(require_database_owner_path()),
) -> Response:
    database_service.remove_member(database.id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
