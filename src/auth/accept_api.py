# src/auth/accept_api.py
from fastapi import APIRouter, HTTPException, Query
from database.db_utils import get_db_connection
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/accept")
def accept_invite(token: str = Query(..., description="Token de invitación")):
    """
    Consume un token de invitación y activa la cuenta del usuario.
    Después de activar, el usuario debe hacer login con Google via Cognito.
    """
    if not token or not token.strip():
        raise HTTPException(status_code=400, detail="Token requerido")
    
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            # Llamar a la función invitation_consume_token
            cur.execute("SELECT invitation_consume_token(%s)", (token,))
            result = cur.fetchone()
            
            if not result or result[0] is None:
                raise HTTPException(
                    status_code=400,
                    detail="Token inválido o expirado"
                )
            
            email = result[0]
            logger.info(f"Invitación activada para {email}")
            
    except HTTPException:
        raise
    except Exception as e:
            logger.error(f"Error al consumir token: {str(e)}", exc_info=True)
            # Intentar obtener el mensaje de error de PostgreSQL
            error_msg = str(e)
            if "expired" in error_msg.lower() or "expirado" in error_msg.lower():
                raise HTTPException(status_code=400, detail="Token expirado")
            elif "invalid" in error_msg.lower() or "inválido" in error_msg.lower():
                raise HTTPException(status_code=400, detail="Token inválido")
            else:
                raise HTTPException(status_code=500, detail=f"Error al procesar invitación: {error_msg}")
    
    return {
        "ok": True,
        "email": str(email),
        "message": "Invitación activada correctamente. Ahora puedes iniciar sesión."
    }

