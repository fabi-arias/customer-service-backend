# main.py - FastAPI Backend
from fastapi import FastAPI, HTTPException, Response, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import sys
import json
from pathlib import Path
from urllib.parse import urlparse

# Agregar el directorio src al path para imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from services.bedrock_service import bedrock_service
from database.db_utils import execute_query, test_connection
from database.data_management_api import data_app
from auth.cognito import exchange_code_for_tokens, verify_id_token, get_token_expiration_seconds
from auth.deps import current_user
from auth.invite_api import router as invite_router
from auth.accept_api import router as accept_router
from auth.allowlist_check import router as allowlist_router
from auth.users_api import router as users_router
from auth.admin_roles_api import router as admin_roles_router
from config.secrets import get_secret
from config.settings import cognito_config

app = FastAPI(
    title="Customer Service Chat API",
    description="API completa para chat de servicio al cliente con Bedrock Agent e ingest de datos",
    version="1.0.0"
)

# Montar FastAPI de gestión de datos
app.mount("/data", data_app)

# Configuración de cookies
COOKIE_DOMAIN = get_secret("COOKIE_DOMAIN", "localhost") or "localhost"
COOKIE_SECURE = (get_secret("COOKIE_SECURE", "false") or "false").lower() == "true"
COOKIE_SAMESITE = get_secret("COOKIE_SAMESITE", "lax") or "lax"

# Configurar CORS para el frontend (dinámico desde secrets)
# Orígenes de desarrollo local (siempre incluidos)
LOCAL_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]

# Inicializar con orígenes locales
allowed_origins = LOCAL_ORIGINS.copy()

# Obtener dominio del backend desde COOKIE_DOMAIN (si está configurado)
backend_domain = get_secret("COOKIE_DOMAIN", "")
if backend_domain and backend_domain != "localhost":
    # Construir URL completa del backend
    backend_url = f"https://{backend_domain}"
    if backend_url not in allowed_origins:
        allowed_origins.append(backend_url)

# Obtener dominio del frontend desde OAUTH_REDIRECT_URI (si está configurado)
oauth_redirect_uri = get_secret("OAUTH_REDIRECT_URI", "")
if oauth_redirect_uri:
    # Extraer el dominio base del redirect URI (ej: https://muscle.d36x6ebk3crti5.amplifyapp.com/login/callback -> https://muscle.d36x6ebk3crti5.amplifyapp.com)
    try:
        parsed = urlparse(oauth_redirect_uri)
        frontend_url = f"{parsed.scheme}://{parsed.netloc}"
        if frontend_url not in allowed_origins:
            allowed_origins.append(frontend_url)
    except Exception:
        pass  # Si falla el parsing, continuar sin agregar

# Obtener allowed origins adicionales desde variable de entorno (para API Gateway u otros)
CORS_ORIGINS_STR = get_secret("CORS_ORIGINS", "")
if CORS_ORIGINS_STR:
    # Si está configurado, agregar a la lista (sin duplicados)
    additional_origins = [origin.strip() for origin in CORS_ORIGINS_STR.split(",") if origin.strip()]
    for origin in additional_origins:
        if origin not in allowed_origins:
            allowed_origins.append(origin)

# Agregar también el dominio del frontend si está configurado explícitamente
FRONTEND_URL = get_secret("FRONTEND_URL", "")
if FRONTEND_URL and FRONTEND_URL not in allowed_origins:
    allowed_origins.append(FRONTEND_URL)

# También agregar variantes HTTPS si hay HTTP
for origin in allowed_origins[:]:  # Copia de la lista para iterar
    if origin.startswith("http://"):
        https_version = origin.replace("http://", "https://", 1)
        if https_version not in allowed_origins:
            allowed_origins.append(https_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Modelos Pydantic
# =========================
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    success: bool
    response: Optional[str] = None
    session_id: Optional[str] = None
    error: Optional[str] = None
    trace: Optional[List[Dict[str, Any]]] = None

class AgentInfo(BaseModel):
    agent_id: str
    agent_alias_id: str
    region: str
    arn: Optional[str] = None

class ConnectionTest(BaseModel):
    success: bool
    message: str
    error: Optional[str] = None
    agent_info: Optional[AgentInfo] = None

# =========================
# Endpoints
# =========================
@app.get("/")
async def root():
    """Endpoint raíz de la API."""
    return {
        "message": "Customer Service Chat API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check de la API."""
    return {"status": "healthy", "service": "customer-service-chat-api"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, me=Depends(current_user)):
    """
    Endpoint principal para el chat con el agente de Bedrock.
    - Inyecta atributos de sesión (role, email, etc.) para que:
      * El orquestador decida si puede invocar SpotMetrics
      * La Lambda de SpotMetrics reciba el mismo contexto
    """
    try:
        groups = set(me.get("groups", []))
        role = "Supervisor" if "Supervisor" in groups else "Agent"

        session_attrs = {
            "role": role,
            "user_email": me["email"],
            "user_id": me["claims"].get("sub", ""),
            "groups": ",".join(groups)
        }

        response = bedrock_service.invoke_agent(
            user_input=request.message,
            session_id=request.session_id,
            enable_trace=True,
            session_attributes=session_attrs,  # ← clave
        )

        return ChatResponse(
            success=response.get("success", False),
            response=response.get("response"),
            session_id=response.get("session_id"),
            error=response.get("error"),
            trace=response.get("trace")
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")


@app.get("/api/agent/info", response_model=AgentInfo)
async def get_agent_info():
    """
    Obtiene información del agente de Bedrock configurado.
    """
    try:
        info = bedrock_service.get_agent_info()
        return AgentInfo(**info)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener información del agente: {str(e)}"
        )

@app.post("/api/agent/test-connection", response_model=ConnectionTest)
async def test_agent_connection():
    """
    Prueba la conexión con el agente de Bedrock.
    """
    try:
        result = bedrock_service.test_connection()
        
        agent_info = None
        if result.get("success") and result.get("agent_info"):
            agent_info = AgentInfo(**result["agent_info"])
        
        return ConnectionTest(
            success=result.get("success", False),
            message=result.get("message", ""),
            error=result.get("error"),
            agent_info=agent_info
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al probar la conexión: {str(e)}"
        )

@app.get("/api/database/health")
async def database_health():
    """
    Verifica el estado de la base de datos.
    """
    try:
        is_healthy = test_connection()
        return {
            "success": is_healthy,
            "message": "Base de datos conectada" if is_healthy else "Error de conexión a la base de datos"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error al verificar la base de datos: {str(e)}"
        }

@app.get("/api/database/stats")
async def get_database_stats():
    """
    Obtiene estadísticas básicas de la base de datos.
    """
    try:
        # Usar tu lógica actual de ingest_api.py
        result = execute_query("SELECT COUNT(*) FROM resolved_tickets")
        
        if result.get("success"):
            total_tickets = result["rows"][0][0] if result["rows"] else 0
            
            # Obtener categorías
            categories_result = execute_query("""
                SELECT category, COUNT(*) as count 
                FROM resolved_tickets 
                WHERE category IS NOT NULL 
                GROUP BY category 
                ORDER BY count DESC
                LIMIT 10
            """)
            
            categories = []
            if categories_result.get("success"):
                categories = [
                    {"category": row[0], "count": row[1]} 
                    for row in categories_result["rows"]
                ]
            
            return {
                "success": True,
                "total_tickets": total_tickets,
                "categories": categories
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Error desconocido")
            }
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener estadísticas: {str(e)}"
        )

# =========================
# Auth Endpoints
# =========================
@app.post("/auth/exchange")
async def auth_exchange(code: str = Form(...)):
    """
    Intercambia el 'code' por tokens con Cognito. Devuelve cookie HttpOnly.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Intercambiando código por tokens...")
        tokens = exchange_code_for_tokens(code)
        id_token = tokens.get("id_token")
        if not id_token:
            logger.error("No id_token returned from Cognito")
            raise HTTPException(status_code=401, detail="No id_token returned")

        # Validar inmediatamente (falla temprano)
        logger.info("Validando id_token...")
        claims = verify_id_token(id_token)
        email = (claims.get("email") or "").lower()
        logger.info(f"Token validado para email: {email}")

        # Verificar status del usuario en DB antes de crear sesión
        from auth.deps import check_user_status
        try:
            role, status = check_user_status(email)
            logger.info(f"Usuario {email} tiene status {status} y rol {role}")
        except HTTPException:
            # Re-lanzar el HTTPException con el mensaje apropiado
            raise

        # Obtener expiración real del token para sincronizar cookie
        token_max_age = get_token_expiration_seconds(id_token)
        logger.info(f"Token expira en {token_max_age} segundos")

        resp = {"ok": True, "email": email}
        response = Response(content=json.dumps(resp), media_type="application/json")
        # Cookie HttpOnly con expiración sincronizada con el token JWT
        response.set_cookie(
            key="id_token",
            value=id_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,  # "lax" en local
            domain=None if COOKIE_DOMAIN == "localhost" else COOKIE_DOMAIN,
            max_age=token_max_age,  # Sincronizado con expiración real del JWT
            path="/",
        )
        logger.info(f"Sesión iniciada exitosamente para {email}")
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en auth_exchange: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@app.post("/auth/logout")
async def auth_logout():
    """
    Cierra sesión completamente:
    1. Elimina la cookie id_token del backend
    2. El frontend redirige a Cognito /logout para cerrar sesión de Cognito
    """
    response = Response(content=json.dumps({"ok": True}), media_type="application/json")
    # Eliminar cookie con los mismos parámetros que se usaron para establecerla
    response.delete_cookie(
        key="id_token",
        path="/",
        domain=None if COOKIE_DOMAIN == "localhost" else COOKIE_DOMAIN,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        httponly=True,
    )
    return response


@app.get("/auth/me")
async def auth_me(user=Depends(current_user)):
    claims = user.get("claims", {})
    return {
        "email": user["email"],
        "groups": user["groups"],
        "given_name": claims.get("given_name"),
        "family_name": claims.get("family_name"),
    }


@app.get("/auth/health")
async def auth_health():
    """
    Health check para el sistema de autenticación.
    Verifica que las configuraciones de Cognito estén configuradas.
    """
    checks = {
        "cognito_configured": bool(cognito_config.user_pool_id and cognito_config.client_id),
        "domain_configured": bool(cognito_config.domain),
        "redirect_uri_configured": bool(cognito_config.redirect_uri),
    }
    all_ok = all(checks.values())
    return {
        "status": "healthy" if all_ok else "misconfigured",
        "checks": checks
    }


# Ejemplos protegidos (comentados - se eliminarán para empezar desde cero)
# @app.get("/secure/agent")
# async def secure_agent(_=Depends(require_agent)):
#     return {"ok": True, "scope": "agent"}


# @app.get("/secure/supervisor")
# async def secure_supervisor(_=Depends(require_supervisor)):
#     return {"ok": True, "scope": "supervisor"}

# Registrar routers de invitación
app.include_router(invite_router)
app.include_router(accept_router)
app.include_router(allowlist_router)
app.include_router(users_router)
app.include_router(admin_roles_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)