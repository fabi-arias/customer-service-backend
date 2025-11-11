# src/auth/accept_api.py
from fastapi import APIRouter, HTTPException, Query
from database.db_utils import get_db_connection
import logging
import datetime as dt
from datetime import timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/accept")
def accept_invite(token: str = Query(..., description="Token de invitación")):
    """
    Consume un token de invitación y activa la cuenta del usuario.
    Después de activar, el usuario debe hacer login con Google via Cognito.
    
    Reglas de idempotencia:
    - Token válido: cambia status a 'active', limpia token y token_expires_at
    - Token ya consumido o expirado: 400
    - Si usuario ya está active: idempotente, devuelve 200 (limpia token si existe)
    """
    if not token or not token.strip():
        raise HTTPException(status_code=400, detail="Token requerido")
    
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            # Verificar token y obtener email
            cur.execute("""
                SELECT email, status, token_expires_at 
                FROM invited_users 
                WHERE token = %s
            """, (token,))
            row = cur.fetchone()
            
            if not row:
                raise HTTPException(status_code=400, detail="Token inválido o expirado")
            
            email, current_status, token_expires_at = row
            
            # Verificar si el token está expirado
            # ✅ usar datetime aware para comparar con TIMESTAMPTZ
            if token_expires_at and token_expires_at < dt.datetime.now(dt.timezone.utc):
                raise HTTPException(status_code=400, detail="Token expirado")
            
            # Si ya está active, es idempotente (limpia token pero no cambia estado)
            if current_status == "active":
                cur.execute("""
                    UPDATE invited_users 
                    SET token = NULL, 
                        token_expires_at = NULL,
                        updated_at = NOW()
                    WHERE email = %s
                """, (email,))
                conn.commit()
                logger.info(f"Token limpiado para usuario ya activo: {email}")
            else:
                # Activar invitación: cambiar a active y limpiar token
                cur.execute("""
                    UPDATE invited_users 
                    SET status = 'active',
                        token = NULL,
                        token_expires_at = NULL,
                        updated_at = NOW()
                    WHERE email = %s AND token = %s
                """, (email, token))
                
                if cur.rowcount == 0:
                    raise HTTPException(status_code=400, detail="Token inválido o ya consumido")
                
                conn.commit()
                logger.info(f"Invitación activada para {email}")
            
    except HTTPException:
        raise
    except Exception as e:
        # Log interno con stacktrace; no filtrar detalles al cliente.
        logger.error("Error al consumir token", exc_info=True)
        error_msg = str(e)
        # Normaliza para cotejar con y sin acentos.
        try:
            import unicodedata
            msg_norm = unicodedata.normalize("NFKD", error_msg).encode("ascii", "ignore").decode().lower()
        except Exception:
            msg_norm = error_msg.lower()

        if "expired" in msg_norm or "expirado" in msg_norm:
            raise HTTPException(status_code=400, detail="Token expirado")
        elif "invalid" in msg_norm or "invalido" in msg_norm:
            raise HTTPException(status_code=400, detail="Token inválido")
        else:
            # Mensaje neutro para evitar fugas de información.
            raise HTTPException(status_code=500, detail="Error al procesar invitación") from None

    return {
        "ok": True,
        "email": str(email),
        "message": "Invitación activada correctamente. Ahora puedes iniciar sesión."
    }

