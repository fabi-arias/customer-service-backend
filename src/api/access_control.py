# src/api/access_control.py

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, EmailStr
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import hashlib
import os
import sys
from pathlib import Path

# Importar utilidad de DB
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))
from database.db_utils import get_db_connection
from api.auth import require_role

router = APIRouter(prefix="/access", tags=["access-control"])

# ========= Config/const =========
INTERNAL_TRIGGER_KEY = os.getenv("COGNITO_TRIGGER_KEY", "")           # clave que usará la Lambda
APP_BASE_URL         = os.getenv("APP_BASE_URL", "http://localhost:3000")
INVITE_TTL_DAYS      = int(os.getenv("INVITE_TTL_DAYS", "7"))

# ======== Modelos pydantic ========
class InviteCreate(BaseModel):
    email: EmailStr
    role: str  # 'Supervisor' | 'Agent'

class InviteResponse(BaseModel):
    success: bool
    invite_url: str
    expires_at: str

class AllowlistItem(BaseModel):
    email: EmailStr
    role: str
    enabled: bool
    invited_by: EmailStr | None = None
    created_at: str
    updated_at: str

class AllowlistCheckResponse(BaseModel):
    allowed: bool
    role: str | None = None

# ======== Helper: auth de supervisor ========
require_supervisor = require_role(["Supervisor"])

# ======== INVITAR (solo Supervisores) ========
@router.post("/invites", response_model=InviteResponse)
def create_invite(body: InviteCreate, claims=Depends(require_supervisor)):
    email = body.email.lower()
    role  = body.role
    if role not in ("Supervisor", "Agent"):
        raise HTTPException(400, "Rol inválido")

    token_plain = uuid4().hex + uuid4().hex  # 64 chars
    token_hash  = hashlib.sha256(token_plain.encode()).hexdigest()
    expires_at  = datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)

    conn = get_db_connection()
    with conn, conn.cursor() as cur:
        # crea invitación (si ya había pending, falla por unique)
        cur.execute("""
            INSERT INTO user_invites (id, email, role, status, invited_by, expires_at, token_hash)
            VALUES (%s, %s, %s, 'pending', %s, %s, %s)
            RETURNING id
        """, (str(uuid4()), email, role, None, expires_at, token_hash))
        # upsert en allowlist (habilitado)
        cur.execute("""
            INSERT INTO user_allowlist (email, role, enabled)
            VALUES (%s, %s, true)
            ON CONFLICT (email) DO UPDATE
              SET role=EXCLUDED.role, enabled=true, updated_at=now()
        """, (email, role))
        conn.commit()

    invite_url = f"{APP_BASE_URL}/invite?token={token_plain}&email={email}"
    return InviteResponse(success=True, invite_url=invite_url, expires_at=expires_at.isoformat())

# ======== Revocar invitación (solo Supervisores) ========
@router.post("/invites/revoke")
def revoke_invite(email: EmailStr, claims=Depends(require_supervisor)):
    conn = get_db_connection()
    with conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE user_invites SET status='revoked'
            WHERE email=%s AND status='pending'
        """, (email.lower(),))
        conn.commit()
    return {"success": True}

# ======== Listar allowlist (solo Supervisores) ========
@router.get("/allowlist", response_model=list[AllowlistItem])
def list_allowlist(claims=Depends(require_supervisor)):
    conn = get_db_connection()
    with conn, conn.cursor() as cur:
        cur.execute("""
            SELECT email, role::text, enabled, invited_by, created_at, updated_at
            FROM user_allowlist ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
    return [
        AllowlistItem(
            email=r[0], role=r[1], enabled=r[2],
            invited_by=r[3], created_at=r[4].isoformat(), updated_at=r[5].isoformat()
        ) for r in rows
    ]

# ======== Cambiar rol/estado (solo Supervisores) ========
@router.post("/allowlist/upsert")
def upsert_allow(email: EmailStr, role: str = Query(..., pattern="^(Supervisor|Agent)$"), enabled: bool = True, claims=Depends(require_supervisor)):
    conn = get_db_connection()
    with conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO user_allowlist (email, role, enabled)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE
              SET role=EXCLUDED.role, enabled=EXCLUDED.enabled, updated_at=now()
        """, (email.lower(), role, enabled))
        conn.commit()
    return {"success": True}

# ======== Endpoint para la LAMBDA (Trigger) ========
# Cognito Pre Sign-Up consultará aquí si el email está permitido
@router.get("/trigger/allowlist/check", response_model=AllowlistCheckResponse)
def allowlist_check(email: EmailStr, x_internal_key: str = Header(None)):
    if not INTERNAL_TRIGGER_KEY or x_internal_key != INTERNAL_TRIGGER_KEY:
        raise HTTPException(401, "Unauthorized")
    conn = get_db_connection()
    with conn, conn.cursor() as cur:
        cur.execute("SELECT role::text, enabled FROM user_allowlist WHERE email=%s", (email.lower(),))
        row = cur.fetchone()
    if not row or not row[1]:
        return AllowlistCheckResponse(allowed=False)
    return AllowlistCheckResponse(allowed=True, role=row[0])

