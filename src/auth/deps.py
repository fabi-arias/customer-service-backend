# src/auth/deps.py
from fastapi import Depends, HTTPException, status, Request
from typing import Dict, Any
import os
from .cognito import verify_id_token, extract_groups, is_allowed_email, ALLOWED_GROUPS
from database.db_utils import get_db_connection

COOKIE_NAME = "id_token"  # simple: usamos el id_token
# (en producción, considera access_token + introspección para APIs de recursos)

def _read_token_from_request(req: Request) -> str:
    # 1) Header Authorization: Bearer <token> (opcional)
    auth = req.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    # 2) Cookie HttpOnly
    token = req.cookies.get(COOKIE_NAME)
    if token:
        return token
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

def _check_allowlist(email: str, expected_role: str | None = None) -> None:
    conn = get_db_connection()
    with conn, conn.cursor() as cur:
        cur.execute("""
            SELECT role, status
            FROM invited_users
            WHERE email = %s
            """, (email,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=403, detail="Not invited")
        role, status = row
        if status != "active":
            raise HTTPException(status_code=403, detail=f"Invitation status: {status}")
        if expected_role and role != expected_role:
            # Permitimos Supervisor acceder a rutas Agent
            if expected_role == "Agent" and role == "Supervisor":
                return
            raise HTTPException(status_code=403, detail=f"Role mismatch: {role} vs {expected_role}")

def current_user(req: Request) -> Dict[str, Any]:
    token = _read_token_from_request(req)
    claims = verify_id_token(token)
    email = (claims.get("email") or "").lower()
    if not email or not is_allowed_email(email):
        raise HTTPException(status_code=403, detail="Email domain not allowed")
    groups = set(extract_groups(claims))
    if not (groups & ALLOWED_GROUPS):
        raise HTTPException(status_code=403, detail="Required group not present")
    # allowlist DB
    _check_allowlist(email)
    return {"email": email, "groups": list(groups), "claims": claims}

def require_agent(user = Depends(current_user)):
    g = set(user["groups"])
    if not ({"Agent","Supervisor"} & g):
        raise HTTPException(status_code=403, detail="Agent role required")
    return user

def require_supervisor(user = Depends(current_user)):
    if "Supervisor" not in set(user["groups"]):
        raise HTTPException(status_code=403, detail="Supervisor role required")
    # allowlist con rol
    _check_allowlist(user["email"], expected_role="Supervisor")
    return user
