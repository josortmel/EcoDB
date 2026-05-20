"""Auth core — JWT + API keys + dependency get_current_user.

Modelo de roles cerrado en sesion 2026-05-07 durante construccion de 
- Superuser: users.is_super=true, platform owner.
- CEO            (dueño empresa cliente): users.is_ceo=true + organizations.ceo_user_id.
- Admin / Lead   (jefe departamento): workspace_leads.user_id.
- Usuario        (empleado): project_members.user_id.

JWT payload (claims):
- sub                : user_id
- email              : email usado en el login (uno de los user_emails del user)
- is_super           : bool
- is_ceo             : bool
- organization_id    : id de la org si is_ceo=true, sino None
- lead_workspaces    : lista de workspace_id donde el user es lead
- iat / exp          : timestamps estandar JWT

API key format: `ecodb_<32-bytes-base64url>` (~44 chars).
- Hash en DB: SHA-256(API_KEY_PEPPER + key) hex (64 chars).
- Sin salt por key (lookup O(1) por hash).
- Pepper en env var → resistencia adicional a DB dumps.
- API keys son secrets aleatorios largos → preimage attack ~imposible.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status

import settings
from db import get_pool


# ---------------------------------------------------------------------------
# API key generation + hashing
# ---------------------------------------------------------------------------

def generate_api_key() -> tuple[str, str]:
    """Genera una API key nueva. Devuelve (key_plain, key_hash).

    El plain SOLO se devuelve UNA vez al user. El hash es lo que va a la DB.
    """
    raw = secrets.token_bytes(32)
    suffix = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    key_plain = f"{settings.API_KEY_PREFIX}{suffix}"
    key_hash = hash_api_key(key_plain)
    return key_plain, key_hash


def hash_api_key(key: str) -> str:
    """SHA-256 con pepper. Hex (64 chars). Determinista — lookup O(1)."""
    h = hashlib.sha256()
    h.update(settings.API_KEY_PEPPER.encode("utf-8"))
    h.update(key.encode("utf-8"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

async def build_jwt_payload(user_id: int, email: str) -> dict:
    """Construye el payload del JWT consultando la DB para roles + scopes."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, name, is_super, is_ceo, active FROM users WHERE id = $1",
            user_id,
        )
        if user is None or not user["active"]:
            raise HTTPException(status_code=401, detail="user not found or inactive")

        organization_id = None
        if user["is_ceo"]:
            org = await conn.fetchrow(
                "SELECT id FROM organizations WHERE ceo_user_id = $1",
                user_id,
            )
            organization_id = org["id"] if org else None

        lead_rows = await conn.fetch(
            "SELECT workspace_id FROM workspace_leads WHERE user_id = $1",
            user_id,
        )
        lead_workspaces = [r["workspace_id"] for r in lead_rows]

    # NO incluir `name` en JWT payload. Reduce PII expuesta
    # en el token (que es base64url, no encriptado). El name se resuelve
    # on-demand desde DB en /auth/me. El email se mantiene porque es practico
    # como subject identifier para clientes; pero conviene auditar logs para
    # que nunca se filtre un JWT plain.
    now = int(time.time())
    return {
        "sub": str(user_id),
        "email": email,
        "is_super": user["is_super"],
        "is_ceo": user["is_ceo"],
        "organization_id": organization_id,
        "lead_workspaces": lead_workspaces,
        "iat": now,
        "exp": now + settings.JWT_TTL_SECONDS,
    }


def encode_jwt(payload: dict) -> str:
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token")


# ---------------------------------------------------------------------------
# Dependency: resolver user actual desde Authorization header
# ---------------------------------------------------------------------------

async def resolve_user_from_api_key(key: str) -> dict:
    """Valida una API key contra la DB y devuelve el JWT-shaped payload.

    OBS-3 (verificador L1): combinada en una sola query con JOIN a user_emails
    (en lugar de dos `pool.acquire()` separados). Una sola conexion del pool.
    """
    key_hash = hash_api_key(key)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ak.user_id, ak.expires_at, ak.active,
                   u.active AS user_active,
                   ue.email AS primary_email
            FROM api_keys ak
            JOIN users u ON u.id = ak.user_id
            LEFT JOIN user_emails ue ON ue.user_id = u.id AND ue.is_primary = true
            WHERE ak.key_hash = $1
            """,
            key_hash,
        )
    if row is None or not row["active"] or not row["user_active"]:
        raise HTTPException(status_code=401, detail="invalid api key")
    if row["expires_at"] is not None and row["expires_at"].timestamp() < time.time():
        raise HTTPException(status_code=401, detail="api key expired")

    primary_email = row["primary_email"] or f"user-{row['user_id']}@unknown"
    return await build_jwt_payload(row["user_id"], primary_email)


async def get_current_user(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> dict:
    """Resuelve el user actual desde:
       - `Authorization: Bearer <jwt>` o
       - `Authorization: Bearer <ecodb_api_key>` o
       - `Authorization: ApiKey <ecodb_api_key>`

    Devuelve el dict de claims del JWT (con el shape de build_jwt_payload).
    Lanza 401 si falta o es invalido.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")

    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=401, detail="malformed Authorization header")

    scheme, token = parts[0].lower(), parts[1].strip()

    # Si el token empieza con el prefijo de API keys, tratarlo como tal aunque
    # venga con scheme "Bearer" (compat con clientes MCP que solo soportan Bearer).
    if token.startswith(settings.API_KEY_PREFIX) or scheme == "apikey":
        return await resolve_user_from_api_key(token)
    if scheme == "bearer":
        return decode_jwt(token)

    raise HTTPException(status_code=401, detail="unsupported auth scheme")


def require_super(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_super"):
        raise HTTPException(status_code=403, detail="super role required")
    return user


def require_super_or_ceo(user: dict = Depends(get_current_user)) -> dict:
    if not (user.get("is_super") or user.get("is_ceo")):
        raise HTTPException(status_code=403, detail="super or ceo role required")
    return user


# ---------------------------------------------------------------------------
# Router con los endpoints del plan v3 §2.1
# ---------------------------------------------------------------------------
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    api_key: str = Field(..., description="API key con prefijo ecodb_")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(BaseModel):
    user_id: int
    email: str
    name: str
    is_super: bool
    is_ceo: bool
    organization_id: Optional[int]
    lead_workspaces: list[int]


class ApiKeyCreateRequest(BaseModel):
    user_id: int = Field(..., description="ID del user al que pertenece la nueva API key")
    name: str = Field(..., min_length=1, max_length=200, description="Nombre legible (ej: 'agent-eco-mcp')")
    expires_at: Optional[datetime] = Field(None, description="Opcional. None = key permanente.")


class ApiKeyCreateResponse(BaseModel):
    id: int
    user_id: int
    name: str
    api_key: str = Field(..., description="Plain key — solo se devuelve UNA vez. Guardarla.")
    expires_at: Optional[datetime]


@router.post("/token", response_model=TokenResponse)
async def auth_token(payload: TokenRequest) -> TokenResponse:
    """Intercambia una API key por un JWT con TTL definido en settings.JWT_TTL_SECONDS."""
    claims = await resolve_user_from_api_key(payload.api_key)
    token = encode_jwt(claims)
    return TokenResponse(access_token=token, expires_in=settings.JWT_TTL_SECONDS)


@router.get("/me", response_model=MeResponse)
async def auth_me(user: dict = Depends(get_current_user)) -> MeResponse:
    """Devuelve los claims del JWT/API key actual + el name del user (resuelto
    desde DB porque tras VS4 el name ya no esta en el JWT payload — reduce PII
    en el token).
    """
    # VS4: name se resuelve desde DB en lugar de venir del JWT payload.
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name FROM users WHERE id = $1", int(user["sub"])
        )
    name = row["name"] if row else f"user-{user['sub']}"
    return MeResponse(
        user_id=int(user["sub"]),
        email=user["email"],
        name=name,
        is_super=user["is_super"],
        is_ceo=user["is_ceo"],
        organization_id=user.get("organization_id"),
        lead_workspaces=user.get("lead_workspaces", []),
    )


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=201)
async def auth_create_api_key(
    body: ApiKeyCreateRequest,
    actor: dict = Depends(require_super_or_ceo),
) -> ApiKeyCreateResponse:
    """Crea una API key para el user indicado. Solo super o CEO pueden.

    no permitir que un CEO cree keys para super
    users — escalada vertical. Solo super puede crear keys para super.
    """
    # OBS-1 (verificador L1): rechazar expires_at en el pasado, evita crear
    # keys inmediatamente inutiles que el usuario cree validas.
    if body.expires_at is not None:
        now = datetime.now(timezone.utc)
        # Si expires_at viene naive, asumir UTC para la comparacion.
        target_exp = body.expires_at if body.expires_at.tzinfo else body.expires_at.replace(tzinfo=timezone.utc)
        if target_exp <= now:
            raise HTTPException(status_code=400, detail="expires_at must be in the future")

    pool = await get_pool()
    async with pool.acquire() as conn:
        target = await conn.fetchrow(
            "SELECT id, name, active, is_super FROM users WHERE id = $1", body.user_id
        )
        if target is None:
            raise HTTPException(status_code=404, detail="target user not found")
        if not target["active"]:
            raise HTTPException(status_code=400, detail="target user is inactive")

        # solo super puede crear keys para super. CEO con conocimiento
        # del user_id=1 no puede escalarse a super pidiendo una API key para the platform owner.
        if target["is_super"] and not actor.get("is_super"):
            raise HTTPException(
                status_code=403,
                detail="only super can create api keys for super users",
            )

        # CEO org-scoping: CEO can only create keys for users in their own org.
        if actor.get("is_ceo") and not actor.get("is_super"):
            actor_org = actor.get("organization_id")
            if actor_org is None:
                raise HTTPException(403, "CEO organization not resolved")
            target_in_org = await conn.fetchval("""
                SELECT 1 FROM project_members pm
                JOIN projects p ON p.id = pm.project_id
                JOIN workspaces w ON w.id = p.workspace_id
                WHERE pm.user_id = $1 AND w.organization_id = $2
                LIMIT 1
            """, body.user_id, actor_org)
            if not target_in_org:
                raise HTTPException(403, "CEO can only create API keys for users in their organization")

        key_plain, key_hash = generate_api_key()
        row = await conn.fetchrow(
            """
            INSERT INTO api_keys (key_hash, name, user_id, expires_at, active)
            VALUES ($1, $2, $3, $4, true)
            RETURNING id, expires_at
            """,
            key_hash, body.name, body.user_id, body.expires_at,
        )

    return ApiKeyCreateResponse(
        id=row["id"],
        user_id=body.user_id,
        name=body.name,
        api_key=key_plain,
        expires_at=row["expires_at"],
    )
