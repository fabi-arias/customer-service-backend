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
            raise HTTPException(status_code=403, detail="Usuario no está autorizado")
        role, status = row
        if status != "active":
            # Mensaje genérico para todos los casos de status no activo
            raise HTTPException(status_code=403, detail="Usuario no está autorizado")
        if expected_role and role != expected_role:
            # Permitimos Supervisor acceder a rutas Agent
            if expected_role == "Agent" and role == "Supervisor":
                return
            raise HTTPException(status_code=403, detail=f"Role mismatch: {role} vs {expected_role}")

def check_user_status(email: str) -> tuple[str, str]:
    """
    Verifica el status del usuario en la DB.
    Retorna (role, status) o lanza HTTPException si no existe o está revocado/pending.
    """
    conn = get_db_connection()
    with conn, conn.cursor() as cur:
        cur.execute("""
            SELECT role, status
            FROM invited_users
            WHERE email = %s
            """, (email,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=403, detail="Usuario no está autorizado")
        role, status = row
        if status != "active":
            # Mensaje genérico para todos los casos de status no activo
            raise HTTPException(status_code=403, detail="Usuario no está autorizado")
        return role, status

def current_user(req: Request) -> Dict[str, Any]:
    token = _read_token_from_request(req)
    claims = verify_id_token(token)
    email = (claims.get("email") or "").lower()
    if not email or not is_allowed_email(email):
        raise HTTPException(status_code=403, detail="Email domain not allowed")
    
    groups_list = extract_groups(claims)          # <- lista intacta, orden estable
    groups_set = set(groups_list)                 # <- para checks
    
    if not (groups_set & ALLOWED_GROUPS):
        raise HTTPException(status_code=403, detail="Required group not present")
    
    _check_allowlist(email)
    return {"email": email, "groups": groups_list, "claims": claims}   # <- devuelve lista

def require_supervisor(req: Request) -> Dict[str, Any]:
    """Dependency que requiere que el usuario sea Supervisor."""
    user = current_user(req)
    groups_set = set(user["groups"])
    if "Supervisor" not in groups_set:
        raise HTTPException(status_code=403, detail="Supervisor role required")
    return user

