# src/auth/cognito.py
import json
import time
import base64
import hmac
import hashlib
from typing import Dict, Any, List, Optional
import requests
from jose import jwt
from jose.utils import base64url_decode
from fastapi import HTTPException, status, Request
from functools import lru_cache
from config.settings import cognito_config
import logging

logger = logging.getLogger(__name__)

REGION = cognito_config.region
USER_POOL_ID = cognito_config.user_pool_id
CLIENT_ID = cognito_config.client_id
CLIENT_SECRET = cognito_config.client_secret  # opcional
DOMAIN = cognito_config.domain
REDIRECT_URI = cognito_config.redirect_uri

ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

ALLOWED_GROUPS = {"Agent", "Supervisor"}
ALLOWED_DOMAIN = "musclepoints.com"


@lru_cache(maxsize=1)
def _fetch_jwks() -> Dict[str, Any]:
    """Obtiene y cachea las claves públicas (JWKS) de Cognito."""
    try:
        r = requests.get(JWKS_URL, timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to fetch JWKS from Cognito", exc_info=True)
        raise HTTPException(status_code=502, detail="Error fetching JWKS from Cognito") from exc



def _get_key(kid: str) -> Dict[str, Any]:
    jwks = _fetch_jwks()
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return k

    # 🔁 JWKS may have rotated on Cognito; try refreshing cache once.
    logger.warning(f"JWKS key {kid} not found — refreshing JWKS cache")
    _fetch_jwks.cache_clear()

    try:
        jwks = _fetch_jwks()
    except Exception:
        logger.error("Failed to refresh JWKS", exc_info=True)
        raise HTTPException(status_code=502, detail="Error fetching JWKS from Cognito")

    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return k

    # If still not found, return 401 — key may truly be invalid.
    raise HTTPException(status_code=401, detail="JWKS key not found")

def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    token_url = f"{DOMAIN}/oauth2/token"
    auth = None
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    # Si usas secret, usa Authorization: Basic
    if CLIENT_SECRET:
        joined = f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
        auth = base64.b64encode(joined).decode()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth}",
        }
    else:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        r = requests.post(token_url, data=data, headers=headers, timeout=10)
    except requests.exceptions.RequestException as exc:
        logger.error("Token exchange request to Cognito failed", exc_info=True)
        raise HTTPException(status_code=502, detail="Token exchange failed") from exc

    if r.status_code != 200:
        logger.warning(f"Token exchange failed with status {r.status_code}: {r.text}")
        raise HTTPException(status_code=401, detail="Token exchange failed")
    return r.json()


def verify_id_token(id_token: str) -> Dict[str, Any]:
    """
    Verifica y decodifica el id_token de Cognito.
    Valida: firma, audiencia, issuer, y expiración (exp).
    """
    headers = jwt.get_unverified_header(id_token)
    key = _get_key(headers["kid"])
    claims = jwt.decode(
        id_token,
        key,
        algorithms=["RS256"],
        audience=CLIENT_ID,     # aud debe ser tu client_id
        issuer=ISSUER,
        options={
            "verify_at_hash": False,
            "verify_exp": True,  # CRÍTICO: Validar expiración explícitamente
        },
    )
    return claims


def get_token_expiration_seconds(id_token: str) -> int:
    """
    Obtiene los segundos hasta la expiración del token.
    Retorna el tiempo restante en segundos, o 0 si ya expiró.
    """
    try:
        # Decodificar sin verificar para obtener claims
        unverified_claims = jwt.get_unverified_claims(id_token)
        exp = unverified_claims.get("exp")
        if not exp:
            logger.warning("Token missing expiration claim, using default")
            # Si no hay exp, usar default de 1 hora
            return 3600
        
        current_time = int(time.time())
        remaining = exp - current_time
        
        # Si ya expiró o queda menos de 60 segundos, retornar 0
        # (60 segundos de margen para evitar problemas de sincronización de reloj)
        return max(0, remaining - 60)
    except Exception:
        logger.warning("Failed to parse token expiration, using default", exc_info=True)
        # Si hay error al decodificar, usar default de 1 hora
        return 3600


def extract_groups(claims: Dict[str, Any]) -> List[str]:
    # Cognito suele usar "cognito:groups"
    g = claims.get("cognito:groups") or []
    return g if isinstance(g, list) else []


def is_allowed_email(email: str) -> bool:
    return email.lower().endswith(f"@{ALLOWED_DOMAIN}")
