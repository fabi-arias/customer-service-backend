# main.py - FastAPI Backend
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import sys
from pathlib import Path

# Agregar el directorio src al path para imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from services.bedrock_service import bedrock_service
from database.db_utils import execute_query, test_connection

app = FastAPI(
    title="Customer Service Chat API",
    description="API para el chat de servicio al cliente con Bedrock Agent",
    version="1.0.0"
)

# Configurar CORS para el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],  # React dev server
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
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint principal para el chat con el agente de Bedrock.
    """
    try:
        print(f"🚀 [API] Mensaje: {request.message[:50]}...")
        
        response = bedrock_service.invoke_agent(
            user_input=request.message,
            session_id=request.session_id
        )
        
        print(f"📤 [API] Respuesta: {response.get('response_source', 'unknown')} ({len(response.get('response', '')) if response.get('response') else 0} chars)")
        
        return ChatResponse(
            success=response.get("success", False),
            response=response.get("response"),
            session_id=response.get("session_id"),
            error=response.get("error"),
            trace=response.get("trace")
        )
        
    except Exception as e:
        print(f"❌ [API] Error: {str(e)}")
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)


