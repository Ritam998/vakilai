import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from loguru import logger
from app.core.config import settings
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user,
)
from app.models.schemas import (
    SignupRequest, LoginRequest, TokenResponse,
    RefreshRequest, UserResponse, MessageResponse,
)

_users_db: dict = {}
router = APIRouter(prefix="/auth", tags=["Authentication"])


def _get_user(email: str):
    return _users_db.get(email.lower())


def _make_tokens(user: dict) -> TokenResponse:
    data = {"sub": user["id"], "email": user["email"]}
    return TokenResponse(
        access_token=create_access_token(data),
        refresh_token=create_refresh_token(user["id"]),
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/signup", response_model=TokenResponse, status_code=201)
async def signup(payload: SignupRequest):
    if _get_user(payload.email):
        raise HTTPException(status_code=409, detail="Email already registered.")
    
    # Truncate password to 72 chars (bcrypt limit)
    safe_password = payload.password[:72]
    
    user = {
        "id": str(uuid.uuid4()),
        "email": payload.email.lower(),
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "phone": payload.phone,
        "password_hash": hash_password(safe_password),
        "plan": "free",
        "docs_used": 0,
        "docs_limit": settings.free_tier_docs_per_month,
        "created_at": datetime.utcnow(),
    }
    _users_db[payload.email.lower()] = user
    logger.info(f"New user: {user['email']}")
    return _make_tokens(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    user = _get_user(payload.email)
    safe_password = payload.password[:72]
    if not user or not verify_password(safe_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return _make_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest):
    decoded = decode_token(payload.refresh_token)
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token.")
    user = next((u for u in _users_db.values() if u["id"] == decoded.get("sub")), None)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return _make_tokens(user)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    user = _get_user(current_user.get("email"))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserResponse(**{k: v for k, v in user.items() if k != "password_hash"})


@router.post("/logout", response_model=MessageResponse)
async def logout(current_user: dict = Depends(get_current_user)):
    return MessageResponse(message="Logged out successfully.")