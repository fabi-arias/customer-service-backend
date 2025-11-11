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
    r = requests.get(JWKS_URL, timeout=5)
    r.raise_for_status()
    return r.json()


def _get_key(kid: str) -> Dict[str, Any]:
    jwks = _fetch_jwks()
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return k
    raise HTTPException(status_code=401, detail="JWKS key not found")


def _client_secret_hash(username: str) -> str:
    # Para public client, no uses esto. Solo si tu app client tiene secret.
    if not CLIENT_SECRET:
        return ""
    message = bytes(username + CLIENT_ID, "utf-8")
    key = bytes(CLIENT_SECRET, "utf-8")
    secret_hash = base64.b64encode(hmac.new(key, message, digestmod=hashlib.sha256).digest()).decode()
    return secret_hash


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

    r = requests.post(token_url, data=data, headers=headers, timeout=10)
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail=f"Token exchange failed: {r.text}")
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
            # Si no hay exp, usar default de 1 hora
            return 3600
        
        current_time = int(time.time())
        remaining = exp - current_time
        
        # Si ya expiró o queda menos de 60 segundos, retornar 0
        # (60 segundos de margen para evitar problemas de sincronización de reloj)
        return max(0, remaining - 60)
    except Exception:
        # Si hay error al decodificar, usar default de 1 hora
        return 3600


def extract_groups(claims: Dict[str, Any]) -> List[str]:
    # Cognito suele usar "cognito:groups"
    g = claims.get("cognito:groups") or []
    return g if isinstance(g, list) else []


def is_allowed_email(email: str) -> bool:
    return email.lower().endswith(f"@{ALLOWED_DOMAIN}")
