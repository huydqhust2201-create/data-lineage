from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query

from src.services import auth_service, database_service, user_service
from src.services.user_service import User


def current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> User:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    user_id = auth_service.decode_access_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    user = user_service.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    return user


def ensure_database_role(database_id: int, user: User, allowed: set[str]) -> None:
    if database_service.get_database(database_id) is None:
        raise HTTPException(status_code=404, detail="database not found")
    role = database_service.role_of(user, database_id)
    if role is None:
        raise HTTPException(status_code=403, detail="database role required")
    if role not in allowed:
        raise HTTPException(status_code=403, detail="database role required")


def require_database_role_query(*allowed: str):
    def dependency(
        database_id: int = Query(...),
        user: User = Depends(current_user),
    ) -> User:
        ensure_database_role(database_id, user, set(allowed))
        return user

    return dependency


def require_database_role_path(*allowed: str):
    def dependency(database_id: int, user: User = Depends(current_user)) -> User:
        ensure_database_role(database_id, user, set(allowed))
        return user

    return dependency


def require_database_owner_path():
    def dependency(database_id: int, user: User = Depends(current_user)) -> database_service.Database:
        return database_service.ensure_database_owner(database_id, user)

    return dependency
