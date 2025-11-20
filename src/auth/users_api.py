# src/auth/users_api.py
"""
API para gestión de usuarios invitados.
Solo accesible para Supervisores.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from database.db_utils import get_db_connection
from auth.deps import current_user
from services.role_sync_service import promote_or_demote, Role
from auth.cognito_admin import find_cognito_username_by_email, get_cognito_groups, disable_cognito_user, enable_cognito_user, global_sign_out
from config.settings import cognito_config
from contextlib import closing
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

    try:
        with closing(get_db_connection()) as conn:
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
    except Exception:
        logger.error("Error listando usuarios", exc_info=True)
        raise HTTPException(status_code=500, detail="Error al listar usuarios") from None


@router.patch("/users/{email}/role")
def update_user_role(email: str, body: UpdateRoleBody, me=Depends(current_user)):
    """
    Actualiza el rol de un usuario en DB y sincroniza con Cognito.
    Devuelve información detallada sobre los cambios aplicados.
    """
    groups = set(me.get("groups", []))
    if "Supervisor" not in groups:
        raise HTTPException(status_code=403, detail="Supervisor role required")
    if body.role not in ("Agent", "Supervisor"):
        raise HTTPException(status_code=400, detail="Rol inválido. Debe ser 'Agent' o 'Supervisor'")

    email_lower = email.lower()
    target_role = body.role  # type: ignore

    try:
        # Obtener estado antes del cambio para reporte
        pool = cognito_config.user_pool_id
        username_before = find_cognito_username_by_email(pool, email_lower)
        cognito_before = get_cognito_groups(pool, username_before) if username_before else []

        # Usar el servicio de sincronización que maneja DB + Cognito
        result = promote_or_demote(
            admin_email=me["email"],
            target_email=email_lower,
            target_role=target_role,
            force_logout=True  # Forzar logout para efecto inmediato
        )

        # Obtener estado después del cambio
        username_after = find_cognito_username_by_email(pool, email_lower)
        cognito_after = get_cognito_groups(pool, username_after) if username_after else []

        logger.info(f"Rol actualizado para {email_lower}: {target_role} (DB changed: {result['db_changed']}, Cognito changed: {result['cognito_changed']})")

        return {
            "ok": True,
            "email": email_lower,
            "role": target_role,
            "message": "Rol actualizado correctamente",
            "db_changed": result["db_changed"],
            "cognito_before": cognito_before,
            "cognito_after": cognito_after,
            "tokens_revoked": result["tokens_revoked"],
            "cognito_changed": result["cognito_changed"]
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Error actualizando rol", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al actualizar rol: {str(e)}") from None


@router.patch("/users/{email}/status")
def update_user_status(email: str, body: UpdateStatusBody, me=Depends(current_user)):
    """
    Actualiza el estado de un usuario en DB y sincroniza con Cognito.
    - revoked: deshabilita en Cognito y revoca tokens
    - active/pending: habilita en Cognito (si estaba deshabilitado)
    
    Estados permitidos: pending, active, revoked
    """
    groups = set(me.get("groups", []))
    if "Supervisor" not in groups:
        raise HTTPException(status_code=403, detail="Supervisor role required")
    if body.status not in ("pending", "active", "revoked"):
        raise HTTPException(status_code=400, detail="Estado inválido. Debe ser 'pending', 'active' o 'revoked'")

    email_lower = email.lower()
    pool = cognito_config.user_pool_id

    try:
        with closing(get_db_connection()) as conn:
            with conn, conn.cursor() as cur:
                # Verificar que el usuario existe
                cur.execute("SELECT status FROM invited_users WHERE email = %s", (email_lower,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Usuario no encontrado")

                current_status = row[0]

                # Buscar usuario en Cognito
                username = find_cognito_username_by_email(pool, email_lower)
                cognito_changed = False
                tokens_revoked = False

                # Actualizar status en DB
                if body.status == "revoked":
                    cur.execute("""
                        UPDATE invited_users 
                        SET status = %s,
                            token = NULL,
                            token_expires_at = NULL,
                            updated_at = NOW()
                        WHERE email = %s
                    """, (body.status, email_lower))
                    
                    # Deshabilitar en Cognito si existe
                    if username:
                        try:
                            disable_cognito_user(pool, username)
                            cognito_changed = True
                            logger.info(f"Usuario {email_lower} deshabilitado en Cognito")
                            
                            # Revocar tokens activos
                            try:
                                global_sign_out(pool, username)
                                tokens_revoked = True
                                logger.info(f"Tokens revocados para {email_lower}")
                            except Exception as e:
                                logger.warning(f"No se pudieron revocar tokens para {email_lower}: {e}")
                        except Exception as e:
                            logger.error(f"Error deshabilitando usuario en Cognito: {e}", exc_info=True)
                            # Continuar aunque falle Cognito - el status en DB ya se actualizó
                else:
                    # active o pending: habilitar en Cognito si existe
                    cur.execute("""
                        UPDATE invited_users 
                        SET status = %s,
                            updated_at = NOW()
                        WHERE email = %s
                    """, (body.status, email_lower))
                    
                    if username:
                        try:
                            enable_cognito_user(pool, username)
                            cognito_changed = True
                            logger.info(f"Usuario {email_lower} habilitado en Cognito")
                        except Exception as e:
                            logger.error(f"Error habilitando usuario en Cognito: {e}", exc_info=True)
                            # Continuar aunque falle Cognito - el status en DB ya se actualizó

                conn.commit()
                logger.info(f"Estado actualizado para {email_lower}: {current_status} -> {body.status} (Cognito: {'sincronizado' if cognito_changed else 'sin cambios'})")

                return {
                    "ok": True,
                    "email": email_lower,
                    "status": body.status,
                    "message": f"Estado actualizado a '{body.status}'",
                    "cognito_changed": cognito_changed,
                    "tokens_revoked": tokens_revoked
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error actualizando estado", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al actualizar estado: {str(e)}") from None
