# src/auth/accept_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, constr
from database.db_utils import get_db_connection
import logging
import datetime as dt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

class AcceptInviteBody(BaseModel):
    token: constr(min_length=1)

@router.post("/accept")
def accept_invite(body: AcceptInviteBody):
    """
    Consume un token de invitación y activa la cuenta del usuario.
    Después de activar, el usuario debe hacer login con Google via Cognito.
    """
    token = body.token.strip()

    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT email, status, token_expires_at 
                FROM invited_users 
                WHERE token = %s
            """, (token,))
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=400, detail="Token inválido o expirado")

            email, current_status, token_expires_at = row

            # Comparar con now UTC (TIMESTAMPTZ)
            if token_expires_at and token_expires_at < dt.datetime.now(dt.timezone.utc):
                raise HTTPException(status_code=400, detail="Token expirado")

            if current_status == "active":
                cur.execute("""
                    UPDATE invited_users 
                    SET token = NULL, token_expires_at = NULL, updated_at = NOW()
                    WHERE email = %s
                """, (email,))
                conn.commit()
                logger.info("Token limpiado para usuario ya activo")
            else:
                cur.execute("""
                    UPDATE invited_users 
                    SET status = 'active', token = NULL, token_expires_at = NULL, updated_at = NOW()
                    WHERE email = %s AND token = %s
                """, (email, token))
                if cur.rowcount == 0:
                    raise HTTPException(status_code=400, detail="Token inválido o ya consumido")
                conn.commit()
                logger.info("Invitación activada")

    except HTTPException:
        raise
    except Exception:
        logger.error("Error al consumir token", exc_info=True)
        raise HTTPException(status_code=500, detail="Error al procesar invitación") from None

    return {"ok": True, "email": str(email), "message": "Invitación activada correctamente. Ahora puedes iniciar sesión."}
