import json
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

from app.auth import (
    create_access_token,
    create_token_pair,
    decode_token,
    get_tenant_id_from_token,
    hash_password,
    refresh_access_token,
    set_tenant_context,
    verify_password,
)
from app.db import get_conn, _use_postgres

router = APIRouter(tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# SQL placeholder style
PH = "%s" if _use_postgres else "?"


def _parse_settings(settings):
    """Parse settings from database (JSON string in SQLite, dict in Postgres)."""
    if settings is None:
        return {}
    if isinstance(settings, str):
        try:
            return json.loads(settings)
        except json.JSONDecodeError:
            return {}
    return settings


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class TokenRefresh(BaseModel):
    refresh_token: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: Optional[str] = None
    tenant_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TenantCreate(BaseModel):
    name: str
    slug: str


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    settings: dict
    created_at: str


class UserResponse(BaseModel):
    id: str
    tenant_id: str
    email: str
    role: str
    created_at: str


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


@router.post("/register", response_model=Token)
def register(user_data: UserCreate):
    """Register a new user and optionally create a tenant."""
    with get_conn() as conn:
        cur = conn.cursor()

        # Determine tenant
        if user_data.tenant_slug and user_data.tenant_name:
            # Create new tenant
            try:
                cur.execute(
                    f"INSERT INTO tenants (name, slug) VALUES ({PH}, {PH}) RETURNING id",
                    (user_data.tenant_name, user_data.tenant_slug),
                )
                tenant_id = cur.fetchone()[0]
            except Exception:
                raise HTTPException(status_code=400, detail="Tenant slug already exists")
        else:
            # Use default tenant
            cur.execute(f"SELECT id FROM tenants WHERE slug = {PH} LIMIT 1", ('default',))
            row = cur.fetchone()
            if not row:
                cur.execute(f"INSERT INTO tenants (name, slug) VALUES ({PH}, {PH}) RETURNING id", ('Default', 'default'))
                tenant_id = cur.fetchone()[0]
            else:
                tenant_id = row[0]

        # Create user
        password_hash = hash_password(user_data.password)
        try:
            cur.execute(
                f"""
                INSERT INTO users (tenant_id, email, password_hash, role)
                VALUES ({PH}, {PH}, {PH}, 'admin')
                RETURNING id
                """,
                (tenant_id, user_data.email, password_hash),
            )
            user_id = cur.fetchone()[0]
        except Exception:
            raise HTTPException(status_code=400, detail="Email already registered in this tenant")

        conn.commit()

    return create_token_pair(user_id, str(tenant_id), user_data.email, "admin")


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login with email and password."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, tenant_id, email, password_hash, role FROM users WHERE email = {PH}",
            (form_data.username,),
        )
        user = cur.fetchone()

    if not user or not verify_password(form_data.password, user[3]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return create_token_pair(str(user[0]), str(user[1]), user[2], user[4])


@router.post("/refresh", response_model=Token)
def refresh(token_data: TokenRefresh):
    """Refresh access token using refresh token."""
    tokens = refresh_access_token(token_data.refresh_token)
    if not tokens:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    return tokens


@router.get("/me", response_model=UserResponse)
def me(user: dict = Depends(get_current_user)):
    """Get current user info."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, tenant_id, email, role, created_at FROM users WHERE id = {PH}",
            (user["sub"],),
        )
        u = cur.fetchone()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(id=str(u[0]), tenant_id=str(u[1]), email=u[2], role=u[3], created_at=str(u[4]))


@router.post("/tenants", response_model=TenantResponse)
def create_tenant(tenant_data: TenantCreate, user: dict = Depends(get_current_user)):
    """Create a new tenant (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                f"INSERT INTO tenants (name, slug) VALUES ({PH}, {PH}) RETURNING id, name, slug, settings, created_at",
                (tenant_data.name, tenant_data.slug),
            )
            t = cur.fetchone()
            conn.commit()
        except Exception:
            raise HTTPException(status_code=400, detail="Tenant slug already exists")
    return TenantResponse(id=str(t[0]), name=t[1], slug=t[2], settings=_parse_settings(t[3]), created_at=str(t[4]))


@router.get("/tenants", response_model=list[TenantResponse])
def list_tenants(user: dict = Depends(get_current_user)):
    """List all tenants (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, slug, settings, created_at FROM tenants ORDER BY created_at DESC")
        tenants = cur.fetchall()
    return [TenantResponse(id=str(t[0]), name=t[1], slug=t[2], settings=_parse_settings(t[3]), created_at=str(t[4])) for t in tenants]


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: str, user: dict = Depends(get_current_user)):
    """Get tenant by ID (admin or same tenant)."""
    if user.get("role") != "admin" and user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT id, name, slug, settings, created_at FROM tenants WHERE id = {PH}", (tenant_id,))
        t = cur.fetchone()
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantResponse(id=str(t[0]), name=t[1], slug=t[2], settings=_parse_settings(t[3]), created_at=str(t[4]))


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
def update_tenant(tenant_id: str, name: str, settings: dict, user: dict = Depends(get_current_user)):
    """Update tenant (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE tenants SET name = {PH}, settings = {PH} WHERE id = {PH} RETURNING id, name, slug, settings, created_at",
            (name, json.dumps(settings), tenant_id),
        )
        t = cur.fetchone()
        conn.commit()
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantResponse(id=str(t[0]), name=t[1], slug=t[2], settings=_parse_settings(t[3]), created_at=str(t[4]))