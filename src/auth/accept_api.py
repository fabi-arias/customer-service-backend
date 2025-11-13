# src/auth/accept_api.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from database.db_utils import get_db_connection
import logging
import datetime as dt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

class AcceptInviteBody(BaseModel):
    token: str = Field(min_length=1)

    @field_validator('token')
    @classmethod
    def strip_token(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            # evita tokens solo con espacios
            raise ValueError('Token cannot be empty or whitespace')
        return stripped

@router.post("/accept")
def accept_invite(body: AcceptInviteBody):
    """
    Consume un token de invitación y activa la cuenta del usuario.
    Después de activar, el usuario debe hacer login con Google via Cognito.
    """
    token = body.token  # ya viene saneado por el validador

    conn = get_db_connection()
    try:
        # usamos solo cursor como context manager y cerramos conn en finally
        with conn.cursor() as cur:
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
                    WHERE email = %s AND token = %s
                """, (email, token))
                if cur.rowcount == 0:
                    raise HTTPException(status_code=400, detail="Token inválido o ya consumido")
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
    finally:
        # 🔒 cerrar conexión siempre para no dejar sockets abiertos
        try:
            conn.close()
        except Exception:
            pass

    return {
        "ok": True,
        "email": str(email),
        "message": "Invitación activada correctamente. Ahora puedes iniciar sesión."
    }
