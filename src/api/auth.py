# src/api/auth.py
import os
import json
import time
import requests
from typing import List, Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.utils import base64url_decode

COGNITO_REGION = os.getenv("COGNITO_REGION", "us-east-1")
USER_POOL_ID   = os.getenv("COGNITO_USER_POOL_ID")
CLIENT_ID      = os.getenv("COGNITO_CLIENT_ID")
JWKS_URL       = os.getenv("COGNITO_JWKS_URL")

if not (USER_POOL_ID and JWKS_URL):
    raise RuntimeError("Faltan variables COGNITO_USER_POOL_ID o COGNITO_JWKS_URL")

bearer_scheme = HTTPBearer(auto_error=True)

# cache simple para JWKS
_JWKS: Optional[Dict[str, Any]] = None
_JWKS_TS: float = 0.0

def _get_jwks() -> Dict[str, Any]:
    global _JWKS, _JWKS_TS
    now = time.time()
    if not _JWKS or (now - _JWKS_TS) > 3600:
        resp = requests.get(JWKS_URL, timeout=5)
        resp.raise_for_status()
        _JWKS = resp.json()
        _JWKS_TS = now
    return _JWKS

def _get_kid(token: str) -> str:
    # leer header del JWT para obtener kid
    try:
        header_b64 = token.split(".")[0]
        # Agregar padding si es necesario (base64url no siempre tiene padding)
        padding = 4 - len(header_b64) % 4
        if padding != 4:
            header_b64 += "=" * padding
        header = json.loads(base64url_decode(header_b64))
        kid = header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="JWT header missing 'kid'")
        return kid
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid JWT format: {str(e)}")

def verify_jwt_and_get_claims(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    token = credentials.credentials
    jwks = _get_jwks()
    kid = _get_kid(token)
    key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
    if not key:
        raise HTTPException(status_code=401, detail="JWT key not found")

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=key.get("alg", "RS256"),
            audience=CLIENT_ID,                                  # valida aud si lo pones
            issuer=f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{USER_POOL_ID}",
            options={"verify_aud": bool(CLIENT_ID)},
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

    return claims

def require_role(allowed: List[str]):
    def _dep(claims: dict = Depends(verify_jwt_and_get_claims)) -> dict:
        groups = claims.get("cognito:groups") or []
        if not isinstance(groups, list):
            groups = [groups] if groups else []
        if not any(g in allowed for g in groups):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return claims
    return _dep

