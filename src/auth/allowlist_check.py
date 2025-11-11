# src/auth/allowlist_check.py
"""
Endpoint interno para verificar allowlist.
Usado por Lambdas de Cognito (Pre Sign-up, Post Confirmation).
Protegido con API key.
"""
from fastapi import APIRouter, HTTPException, Query, Header
from database.db_utils import get_db_connection
from config.settings import appauth_config
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

API_KEY = appauth_config.ingest_api_key


@router.get("/allowlist/check")
def allowlist_check(email: str = Query(..., description="Email a verificar"), x_api_key: str | None = Header(None, alias="X-API-Key")):
    """
    Verifica si un email está en la allowlist y activo.
    
    Usado por Lambdas de Cognito para validar usuarios antes de permitir el sign-up.
    
    Headers:
        X-API-Key: API key para autenticación (INTERNAL_API_KEY)
    
    Returns:
        {
            "allowed": bool,
            "role": str | None  # "Agent" | "Supervisor" | None
        }
    """
    # Verificar API key
    if not API_KEY:
        logger.error("INGEST_API_KEY no está configurada")
        raise HTTPException(status_code=500, detail="API key not configured")
    
    if not x_api_key or x_api_key != API_KEY:
        api_key_preview = x_api_key[:10] + "..." if x_api_key else "None"
        logger.warning(f"Intento de acceso no autorizado con API key: {api_key_preview}")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Normalizar email
    email_lower = email.lower().strip()
    
    if not email_lower or "@" not in email_lower:
        raise HTTPException(status_code=400, detail="Email inválido")
    
    # Verificar en base de datos
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT role, status FROM invited_users WHERE email = %s",
                (email_lower,)
            )
            row = cur.fetchone()
            
            if not row:
                logger.info(f"Email {email_lower} no encontrado en allowlist")
                return {"allowed": False, "role": None}
            
            role, status = row
            allowed = status == "active"
            
            logger.info(f"Email {email_lower}: allowed={allowed}, role={role}, status={status}")
            
            return {
                "allowed": allowed,
                "role": role
            }
    except Exception as e:
        logger.error(f"Error verificando allowlist para {email_lower}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

