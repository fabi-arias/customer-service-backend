# src/auth/users_api.py
"""
API para gestión de usuarios invitados.
Solo accesible para Supervisores.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from database.db_utils import get_db_connection
from auth.deps import current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class UpdateRoleBody(BaseModel):
    role: str  # "Agent" | "Supervisor"


class UpdateStatusBody(BaseModel):
    status: str  # "pending" | "active" | "revoked"


@router.get("/users")
def list_users(me=Depends(current_user)):
    """
    Lista todos los usuarios invitados.
    TODO: Agregar validación de Supervisor cuando se implemente el nuevo sistema de scopes.
    """
    # Validación temporal: verificar que el usuario tenga grupo Supervisor
    groups = set(me.get("groups", []))
    if "Supervisor" not in groups:
        raise HTTPException(status_code=403, detail="Supervisor role required")
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    email,
                    role,
                    status,
                    invited_by,
                    token_expires_at,
                    created_at,
                    updated_at
                FROM invited_users
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
            
            users = []
            for row in rows:
                email, role, status, invited_by, token_expires_at, created_at, updated_at = row
                users.append({
                    "email": email,
                    "role": role,
                    "status": status,
                    "invited_by": invited_by,
                    "token_expires_at": token_expires_at.isoformat() if token_expires_at else None,
                    "created_at": created_at.isoformat() if created_at else None,
                    "updated_at": updated_at.isoformat() if updated_at else None,
                })
            
            return {
                "ok": True,
                "users": users,
                "count": len(users)
            }
    except Exception as e:
        logger.error(f"Error listando usuarios: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al listar usuarios: {str(e)}")


@router.patch("/users/{email}/role")
def update_user_role(email: str, body: UpdateRoleBody, me=Depends(current_user)):
    """
    Actualiza el rol de un usuario.
    TODO: Agregar validación de Supervisor cuando se implemente el nuevo sistema de scopes.
    """
    # Validación temporal: verificar que el usuario tenga grupo Supervisor
    groups = set(me.get("groups", []))
    if "Supervisor" not in groups:
        raise HTTPException(status_code=403, detail="Supervisor role required")
    if body.role not in ("Agent", "Supervisor"):
        raise HTTPException(status_code=400, detail="Rol inválido. Debe ser 'Agent' o 'Supervisor'")
    
    email_lower = email.lower()
    
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            # Verificar que el usuario existe
            cur.execute("SELECT email FROM invited_users WHERE email = %s", (email_lower,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Usuario no encontrado")
            
            # Actualizar rol
            cur.execute("""
                UPDATE invited_users 
                SET role = %s,
                    updated_at = NOW()
                WHERE email = %s
            """, (body.role, email_lower))
            
            conn.commit()
            logger.info(f"Rol actualizado para {email_lower}: {body.role}")
            
            return {
                "ok": True,
                "email": email_lower,
                "role": body.role,
                "message": "Rol actualizado correctamente"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando rol: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al actualizar rol: {str(e)}")


@router.patch("/users/{email}/status")
def update_user_status(email: str, body: UpdateStatusBody, me=Depends(current_user)):
    """
    Actualiza el estado de un usuario.
    TODO: Agregar validación de Supervisor cuando se implemente el nuevo sistema de scopes.
    
    Estados permitidos: pending, active, revoked
    """
    # Validación temporal: verificar que el usuario tenga grupo Supervisor
    groups = set(me.get("groups", []))
    if "Supervisor" not in groups:
        raise HTTPException(status_code=403, detail="Supervisor role required")
    if body.status not in ("pending", "active", "revoked"):
        raise HTTPException(status_code=400, detail="Estado inválido. Debe ser 'pending', 'active' o 'revoked'")
    
    email_lower = email.lower()
    
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            # Verificar que el usuario existe
            cur.execute("SELECT status FROM invited_users WHERE email = %s", (email_lower,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")
            
            current_status = row[0]
            
            # Si se revoca, limpiar token
            if body.status == "revoked":
                cur.execute("""
                    UPDATE invited_users 
                    SET status = %s,
                        token = NULL,
                        token_expires_at = NULL,
                        updated_at = NOW()
                    WHERE email = %s
                """, (body.status, email_lower))
            else:
                cur.execute("""
                    UPDATE invited_users 
                    SET status = %s,
                        updated_at = NOW()
                    WHERE email = %s
                """, (body.status, email_lower))
            
            conn.commit()
            logger.info(f"Estado actualizado para {email_lower}: {current_status} -> {body.status}")
            
            return {
                "ok": True,
                "email": email_lower,
                "status": body.status,
                "message": f"Estado actualizado a '{body.status}'"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando estado: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al actualizar estado: {str(e)}")

