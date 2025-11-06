# main.py - FastAPI Backend
from fastapi import FastAPI, HTTPException, Response, Request, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import sys
import json
import os
from pathlib import Path

# Agregar el directorio src al path para imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from services.bedrock_service import bedrock_service
from database.db_utils import execute_query, test_connection
from database.data_management_api import data_app
from auth.cognito import exchange_code_for_tokens, verify_id_token
from auth.deps import current_user, require_agent, require_supervisor
from auth.invite_api import router as invite_router
from auth.accept_api import router as accept_router
from auth.allowlist_check import router as allowlist_router

app = FastAPI(
    title="Customer Service Chat API",
    description="API completa para chat de servicio al cliente con Bedrock Agent e ingest de datos",
    version="1.0.0"
)

# Montar FastAPI de gestión de datos
app.mount("/data", data_app)

# Configurar CORS para el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de cookies
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", "localhost")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")

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
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint principal para el chat con el agente de Bedrock.
    """
    try:
        response = bedrock_service.invoke_agent(
            user_input=request.message,
            session_id=request.session_id
        )
        
        return ChatResponse(
            success=response.get("success", False),
            response=response.get("response"),
            session_id=response.get("session_id"),
            error=response.get("error"),
            trace=response.get("trace")
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )

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

        resp = {"ok": True, "email": email}
        response = Response(content=json.dumps(resp), media_type="application/json")
        # Cookie HttpOnly
        response.set_cookie(
            key="id_token",
            value=id_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,  # "lax" en local
            domain=None if COOKIE_DOMAIN == "localhost" else COOKIE_DOMAIN,
            max_age=3600,  # 1h
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
    response = Response(content=json.dumps({"ok": True}), media_type="application/json")
    response.delete_cookie("id_token", path="/")
    return response


@app.get("/auth/me")
async def auth_me(user=Depends(current_user)):
    return {"email": user["email"], "groups": user["groups"]}


@app.get("/auth/health")
async def auth_health():
    """
    Health check para el sistema de autenticación.
    Verifica que las variables de entorno estén configuradas.
    """
    import os
    checks = {
        "cognito_configured": bool(os.getenv("COGNITO_USER_POOL_ID") and os.getenv("COGNITO_CLIENT_ID")),
        "domain_configured": bool(os.getenv("COGNITO_DOMAIN")),
        "redirect_uri_configured": bool(os.getenv("OAUTH_REDIRECT_URI")),
    }
    all_ok = all(checks.values())
    return {
        "status": "healthy" if all_ok else "misconfigured",
        "checks": checks
    }


# Ejemplos protegidos
@app.get("/secure/agent")
async def secure_agent(_=Depends(require_agent)):
    return {"ok": True, "scope": "agent"}


@app.get("/secure/supervisor")
async def secure_supervisor(_=Depends(require_supervisor)):
    return {"ok": True, "scope": "supervisor"}

# Registrar routers de invitación
app.include_router(invite_router)
app.include_router(accept_router)
app.include_router(allowlist_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)