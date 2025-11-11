# src/auth/invite_api.py
import secrets
import datetime as dt
from datetime import timezone
import json
import urllib.request
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from database.db_utils import get_db_connection
from auth.deps import current_user
from config.secrets import get_secret
import boto3
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

INVITE_EXP_DAYS = int(get_secret("INVITE_EXP_DAYS", "7") or "7")
FRONTEND_ACCEPT_URL = get_secret("FRONTEND_ACCEPT_URL", "http://localhost:3000/invite/accept") or "http://localhost:3000/invite/accept"

# n8n configuration
N8N_MAIL_WEBHOOK_URL = get_secret("N8N_MAIL_WEBHOOK_URL")
N8N_MAIL_API_KEY = get_secret("N8N_MAIL_API_KEY")  # opcional si luego agregas Auth en n8n

# SES configuration (mantenido como fallback opcional)
SES_REGION = get_secret("SES_REGION", "us-east-1") or "us-east-1"
SES_SENDER = get_secret("SES_SENDER", "no-reply@musclepoints.com") or "no-reply@musclepoints.com"


class InviteBody(BaseModel):
    email: EmailStr
    role: str  # "Agent" | "Supervisor"


def _send_email_via_n8n(
    to_email: str,
    invite_url: str,
    role: str,
    invited_by: str,
    expires_at_iso: str,
) -> None:
    """
    Dispara el flujo de n8n para enviar el correo de invitación.
    Lanza excepción si n8n responde != 2xx.
    """
    if not N8N_MAIL_WEBHOOK_URL:
        raise RuntimeError("N8N_MAIL_WEBHOOK_URL no está configurada")

    payload = {
        "template": "spot_invite_v1",
        "to_email": to_email,
        "role": role,
        "invite_url": invite_url,
        "expires_at": expires_at_iso,
        "invited_by": invited_by,
        "product": "SPOT",
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(N8N_MAIL_WEBHOOK_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if N8N_MAIL_API_KEY:  # solo si decides usar header auth en n8n
        req.add_header("X-API-Key", N8N_MAIL_API_KEY)

    with urllib.request.urlopen(req, timeout=8) as resp:
        # 2xx OK, cualquier otro status -> error
        if resp.status // 100 != 2:
            body = resp.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"n8n respondió {resp.status}: {body}")


def _send_email(email: str, url: str):
    """Envía email de invitación usando Amazon SES (fallback opcional)."""
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
        logger.info(f"Email de invitación enviado a {email} vía SES")
    except Exception as e:
        logger.error(f"Error enviando email a {email} vía SES: {str(e)}")
        raise


@router.post("/invite")
def invite_user(body: InviteBody, me=Depends(current_user)):
    """
    Crea o renueva una invitación para un usuario.
    TODO: Agregar validación de Supervisor cuando se implemente el nuevo sistema de scopes.
    
    Reglas de idempotencia:
    - Si no existe: crea fila pending con role y token
    - Si existe pending: regenera token (renueva expiración)
    - Si existe active: regenera token (permite reenvío)
    - Si existe revoked: cambia a pending y genera token (rehabilita)
    """
    # Validación temporal: verificar que el usuario tenga grupo Supervisor
    groups = set(me.get("groups", []))
    if "Supervisor" not in groups:
        raise HTTPException(status_code=403, detail="Supervisor role required")
    if body.role not in ("Agent", "Supervisor"):
        raise HTTPException(status_code=400, detail="Rol inválido. Debe ser 'Agent' o 'Supervisor'")
    
    # Validar que el email sea del dominio permitido
    if not body.email.lower().endswith("@musclepoints.com"):
        raise HTTPException(
            status_code=400,
            detail="El email debe ser del dominio @musclepoints.com"
        )
    
    email_lower = body.email.lower()
    token = secrets.token_urlsafe(32)
    # ✅ zona horaria explícita (aware)
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=INVITE_EXP_DAYS)
    
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            # Verificar estado actual
            cur.execute(
                "SELECT status, role FROM invited_users WHERE email = %s",
                (email_lower,)
            )
            existing = cur.fetchone()
            
            if existing:
                current_status, current_role = existing
                
                # Si está revoked, cambiar a pending
                if current_status == "revoked":
                    cur.execute("""
                        UPDATE invited_users 
                        SET status = 'pending', 
                            role = %s,
                            token = %s,
                            token_expires_at = %s,
                            invited_by = %s,
                            updated_at = NOW()
                        WHERE email = %s
                    """, (body.role, token, exp, me["email"], email_lower))
                    final_status = "pending"
                # Si está pending o active, regenerar token (idempotente)
                else:
                    cur.execute("""
                        UPDATE invited_users 
                        SET role = %s,
                            token = %s,
                            token_expires_at = %s,
                            invited_by = %s,
                            updated_at = NOW()
                        WHERE email = %s
                    """, (body.role, token, exp, me["email"], email_lower))
                    final_status = current_status  # Mantiene el estado actual
            else:
                # Crear nueva invitación
                cur.execute("""
                    INSERT INTO invited_users 
                    (email, role, status, invited_by, token, token_expires_at, created_at, updated_at)
                    VALUES (%s, %s, 'pending', %s, %s, %s, NOW(), NOW())
                """, (email_lower, body.role, me["email"], token, exp))
                final_status = "pending"
            
            conn.commit()
            logger.info(f"Invitación {'creada' if not existing else 'renovada'} para {email_lower}, status={final_status}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creando invitación", exc_info=True)
        raise HTTPException(status_code=500, detail="Error al crear invitación") from None
    
    invite_url = f"{FRONTEND_ACCEPT_URL}?token={token}"
    
    # --- Enviar correo vía n8n ---
    email_sent = False
    try:
        _send_email_via_n8n(
            to_email=body.email,
            invite_url=invite_url,
            role=body.role,
            invited_by=me["email"],
            expires_at_iso=exp.isoformat(),
        )
        email_sent = True
        logger.info(f"Email de invitación enviado a {body.email} vía n8n")
    except Exception as e:
        logger.warning(f"No se pudo enviar email a {body.email} vía n8n: {str(e)}")
        # Opcional: fallback a SES si n8n falla
        # try:
        #     _send_email(body.email, invite_url)
        #     email_sent = True
        #     logger.info(f"Email enviado vía SES como fallback para {body.email}")
        # except Exception as ses_error:
        #     logger.error(f"Fallback SES también falló para {body.email}: {str(ses_error)}")
    
    return {
        "ok": True,
        "email": body.email,
        "role": body.role,
        "status": final_status,
        "invite_url": invite_url,  # ← siempre devolvemos el link por si quieren copiar/pegar
        "expires_at": exp.isoformat(),
        "email_sent": email_sent
    }

