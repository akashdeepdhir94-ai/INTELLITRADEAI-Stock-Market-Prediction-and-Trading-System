"""
Authentication API
──────────────────
POST /api/v1/auth/register  — create account
POST /api/v1/auth/login     — get access + refresh tokens
POST /api/v1/auth/refresh   — exchange refresh token for new access token
GET  /api/v1/auth/me        — get current user profile
POST /api/v1/auth/logout    — client-side: just discard tokens (stateless JWT)
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from database import get_db
from models import User
from middleware.jwt_utils import create_access_token, create_refresh_token, decode_token
from middleware.dependencies import get_current_user

logger = logging.getLogger("intellitrade.auth")
router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Schemas ───────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters.")
        if len(v) > 64:
            raise ValueError("Username must be at most 64 characters.")
        if not re.match(r"^[A-Za-z0-9_.-]+$", v):
            raise ValueError("Username may only contain letters, numbers, _, -, and .")
        return v

    @field_validator("password")
    @classmethod
    def password_strong(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash(password: str) -> str:
    return pwd_context.hash(password)

def _verify(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    new_user = User(
        username=user.username,
        email=user.email,
        password=_hash(user.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    logger.info("New user registered: %s", new_user.email)
    return {
        "message": "Account created successfully.",
        "username": new_user.username,
        "email": new_user.email,
    }


@router.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    # Constant-time check even when user doesn't exist
    if not db_user or not _verify(user.password, db_user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not db_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact support.",
        )
    token_data = {"sub": db_user.email}
    access_token  = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    logger.info("User logged in: %s", db_user.email)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "username": db_user.username,
        "email": db_user.email,
    }


@router.post("/refresh")
def refresh(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type for refresh.",
        )
    new_access = create_access_token({"sub": payload["sub"]})
    return {"access_token": new_access, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
