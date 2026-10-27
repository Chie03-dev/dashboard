import logging
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import (
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_REFRESH_TOKEN_EXPIRE_DAYS,
    JWT_SECRET_KEY,
)

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

current_tenant_id_var: ContextVar[Optional[str]] = ContextVar("current_tenant_id", default=None)
current_user_id_var: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning("Token decode failed: %s", e)
        return None


def create_token_pair(user_id: str, tenant_id: str, email: str, role: str) -> dict:
    access_token = create_access_token({"sub": user_id, "tenant_id": tenant_id, "email": email, "role": role})
    refresh_token = create_refresh_token({"sub": user_id, "tenant_id": tenant_id, "email": email, "role": role})
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def refresh_access_token(refresh_token: str) -> Optional[dict]:
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        return None
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    email = payload.get("email")
    role = payload.get("role")
    if not all([user_id, tenant_id, email, role]):
        return None
    return create_token_pair(user_id, tenant_id, email, role)


def get_tenant_id_from_token(token: str) -> Optional[str]:
    payload = decode_token(token)
    if payload:
        return payload.get("tenant_id")
    return None


async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    set_tenant_context(payload.get("tenant_id"), payload.get("sub"))
    return payload


async def get_current_tenant(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload.get("tenant_id")


def set_tenant_context(tenant_id: str, user_id: Optional[str] = None):
    current_tenant_id_var.set(tenant_id)
    if user_id:
        current_user_id_var.set(user_id)


def clear_tenant_context():
    current_tenant_id_var.set(None)
    current_user_id_var.set(None)