# src/auth/invite_api.py
import os
import secrets
import datetime as dt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from database.db_utils import get_db_connection
from auth.deps import require_supervisor
import boto3
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

INVITE_EXP_DAYS = int(os.getenv("INVITE_EXP_DAYS", "7"))
FRONTEND_ACCEPT_URL = os.getenv("FRONTEND_ACCEPT_URL", "http://localhost:3000/invite/accept")
SES_REGION = os.getenv("SES_REGION", "us-east-1")
SES_SENDER = os.getenv("SES_SENDER", "no-reply@musclepoints.com")


class InviteBody(BaseModel):
    email: EmailStr
    role: str  # "Agent" | "Supervisor"


def _send_email(email: str, url: str):
    """Envía email de invitación usando Amazon SES."""
    try:
        ses = boto3.client("ses", region_name=SES_REGION)
        ses.send_email(
            Source=SES_SENDER,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": "Invitación a SPOT"},
                "Body": {
                    "Html": {
                        "Data": f"""
                            <html>
                            <body>
                                <h2>Invitación a SPOT</h2>
                                <p>Has sido invitado a SPOT ({email}).</p>
                                <p>Para activar tu acceso, haz clic en el siguiente enlace:</p>
                                <p><a href="{url}">{url}</a></p>
                                <p>Este enlace expira en {INVITE_EXP_DAYS} día(s).</p>
                                <p>Si no solicitaste esta invitación, puedes ignorar este email.</p>
                            </body>
                            </html>
                        """
                    },
                    "Text": {
                        "Data": f"""
                            Invitación a SPOT
                            
                            Has sido invitado a SPOT ({email}).
                            
                            Para activar tu acceso, visita:
                            {url}
                            
                            Este enlace expira en {INVITE_EXP_DAYS} día(s).
                            
                            Si no solicitaste esta invitación, puedes ignorar este email.
                        """
                    }
                },
            },
        )
        logger.info(f"Email de invitación enviado a {email}")
    except Exception as e:
        logger.error(f"Error enviando email a {email}: {str(e)}")
        raise


@router.post("/invite")
def invite_user(body: InviteBody, me=Depends(require_supervisor)):
    """
    Crea una invitación para un nuevo usuario.
    Solo accesible para Supervisores.
    """
    if body.role not in ("Agent", "Supervisor"):
        raise HTTPException(status_code=400, detail="Rol inválido. Debe ser 'Agent' o 'Supervisor'")
    
    # Validar que el email sea del dominio permitido
    if not body.email.lower().endswith("@musclepoints.com"):
        raise HTTPException(
            status_code=400,
            detail="El email debe ser del dominio @musclepoints.com"
        )
    
    token = secrets.token_urlsafe(32)
    exp = dt.datetime.utcnow() + dt.timedelta(days=INVITE_EXP_DAYS)
    
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            # Llamar a la función invite_upsert
            # Parámetros: email, role, invited_by, active, token, expires_at
            cur.execute(
                "SELECT invite_upsert(%s, %s, %s, %s, %s, %s)",
                (body.email.lower(), body.role, me["email"], False, token, exp)
            )
            result = cur.fetchone()
            if result and result[0] is False:
                raise HTTPException(
                    status_code=400,
                    detail="No se pudo crear la invitación. El usuario puede que ya exista."
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creando invitación: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al crear invitación: {str(e)}")
    
    invite_url = f"{FRONTEND_ACCEPT_URL}?token={token}"
    
    # Intentar enviar email (opcional - si falla, la invitación ya está creada)
    try:
        _send_email(body.email, invite_url)
        email_sent = True
    except Exception as e:
        logger.warning(f"No se pudo enviar email a {body.email}: {str(e)}")
        email_sent = False
    
    return {
        "ok": True,
        "email": body.email,
        "role": body.role,
        "invite_url": invite_url,
        "expires_at": exp.isoformat(),
        "email_sent": email_sent
    }

