from fastapi import APIRouter, Depends, HTTPException

from src.api.deps import current_user
from src.models.schemas import GoogleLoginRequest, LoginRequest, RegisterRequest, TokenResponse, UserPublic
from src.services import auth_service, user_service
from src.services.user_service import User

router = APIRouter()


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=auth_service.create_access_token(user.id),
        user=UserPublic(id=user.id, email=user.email, display_name=user.display_name),
    )


@router.get("/users", response_model=list[User])
def list_users(user: User = Depends(current_user)) -> list[User]:
    return user_service.list_users()


@router.get("/auth/me", response_model=User)
def get_current_user(user: User = Depends(current_user)) -> User:
    return user


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest) -> TokenResponse:
    user = user_service.register(body.email, body.display_name, auth_service.hash_password(body.password))
    if user is None:
        raise HTTPException(status_code=409, detail="email already registered")
    return _token_response(user)


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    record = user_service.get_by_email_with_credentials(body.email)
    if record is None or record.password_hash is None or not auth_service.verify_password(body.password, record.password_hash):
        raise HTTPException(status_code=401, detail="invalid email or password")
    return _token_response(User(id=record.id, email=record.email, display_name=record.display_name))


@router.post("/auth/google", response_model=TokenResponse)
def google_login(body: GoogleLoginRequest) -> TokenResponse:
    try:
        email, name, google_sub = auth_service.verify_google_id_token(body.id_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid google token") from exc

    record = user_service.get_by_google_sub(google_sub)
    if record is not None:
        return _token_response(User(id=record.id, email=record.email, display_name=record.display_name))

    existing = user_service.get_by_email_with_credentials(email)
    if existing is not None:
        user = user_service.link_google(existing.id, google_sub)
    else:
        created = user_service.ensure_user(email, name)
        user = user_service.link_google(created.id, google_sub)
    return _token_response(user)
