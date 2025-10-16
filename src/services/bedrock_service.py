# src/services/bedrock_service.py
import boto3
import uuid
import sys
import time
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional
from botocore.config import Config
from botocore.exceptions import ClientError, ReadTimeoutError, ConnectTimeoutError

# Agregar el directorio src al path para imports (manteniendo tu patrón actual)
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from config.settings import bedrock_config


def _extract_plain_answer_from_trace(trace_events):
    """
    Busca en orchestrationTrace.modelInvocationOutput.rawResponse.content el bloque
    AgentCommunication__sendMessage → input.content y devuelve el texto tal como está.
    """
    try:
        for ev in trace_events or []:
            otrace = ev.get("trace", {}).get("orchestrationTrace", {})
            mio = otrace.get("modelInvocationOutput", {})
            raw = mio.get("rawResponse", {})
            content_str = raw.get("content")
            if not content_str:
                continue

            # 'content' es un JSON serializado en str → lo cargamos
            payload = json.loads(content_str)
            blocks = payload.get("output", {}).get("message", {}).get("content", [])

            for b in blocks:
                tool = b.get("toolUse")
                if tool and tool.get("name") == "AgentCommunication__sendMessage":
                    inner = (tool.get("input") or {}).get("content", "")
                    if inner:
                        # Solo normalizar escapes básicos, mantener el formato original
                        inner = inner.replace("\\n", "\n").replace("\\t", "\t")
                        return inner.strip() or None
    except Exception:
        pass
    return None


class BedrockAgentService:
    """Servicio para interactuar con Amazon Bedrock Agent."""

    def __init__(self):
        """Inicializa el cliente de Bedrock Agent."""
        self.config = bedrock_config
        
        # Configurar timeouts y reintentos
        config = Config(
            connect_timeout=self.config.connect_timeout,
            read_timeout=self.config.read_timeout,
            retries={'max_attempts': 0}  # Deshabilitamos los reintentos automáticos de boto3
        )
        
        self.client = boto3.client(
            "bedrock-agent-runtime",
            aws_access_key_id=self.config.aws_access_key_id,
            aws_secret_access_key=self.config.aws_secret_access_key,
            region_name=self.config.region_name,
            config=config
        )
        self.agent_id = self.config.agent_id
        self.agent_alias_id = self.config.agent_alias_id

    def invoke_agent(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        enable_trace: bool = True,  # Cambiar a True por defecto para debugging
    ) -> Dict[str, Any]:
        """
        Invoca el agente de Bedrock con el input del usuario con lógica de reintentos.

        Args:
            user_input: El mensaje del usuario.
            session_id: ID de sesión para mantener contexto (opcional).
            enable_trace: Si habilitar el trace para debugging.

        Returns:
            Dict con la respuesta del agente.
        """
        # Generar session_id si no se proporciona
        if not session_id:
            session_id = str(uuid.uuid4())

        print(f"🔍 [DEBUG] Invocando agente con:")
        print(f"   - Input: {user_input}")
        print(f"   - Session ID: {session_id}")
        print(f"   - Enable Trace: {enable_trace}")

        params = {
            "agentId": self.agent_id,
            "agentAliasId": self.agent_alias_id,
            "sessionId": session_id,
            "inputText": user_input,
            "enableTrace": enable_trace,
        }

        # Lógica de reintentos
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                # Invocar el agente (respuesta por event stream)
                response = self.client.invoke_agent(**params)
                
                # Procesar la respuesta
                return self._process_response(response)

            except (ReadTimeoutError, ConnectTimeoutError) as e:
                last_error = e
                error_type = "timeout de lectura" if isinstance(e, ReadTimeoutError) else "timeout de conexión"
                
                if attempt < self.config.max_retries:
                    wait_time = self.config.retry_delay * (2 ** attempt)  # Backoff exponencial
                    print(f"⚠️  Intento {attempt + 1} falló por {error_type}. Reintentando en {wait_time:.1f}s...")
                    time.sleep(wait_time)
                else:
                    return {
                        "success": False,
                        "error": f"Timeout después de {self.config.max_retries + 1} intentos: {str(e)}",
                        "message": f"El agente tardó demasiado en responder. Último error: {error_type}",
                        "retry_info": {
                            "attempts": self.config.max_retries + 1,
                            "last_error_type": error_type
                        }
                    }

            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                error_message = e.response.get('Error', {}).get('Message', str(e))
                
                # Algunos errores no deben reintentarse
                if error_code in ['ValidationException', 'AccessDeniedException', 'ResourceNotFoundException']:
                    return {
                        "success": False,
                        "error": f"Error de cliente AWS: {error_code} - {error_message}",
                        "message": "Error de configuración o permisos. No se reintentará.",
                        "error_code": error_code
                    }
                
                last_error = e
                if attempt < self.config.max_retries:
                    wait_time = self.config.retry_delay * (2 ** attempt)
                    print(f"⚠️  Intento {attempt + 1} falló con error AWS: {error_code}. Reintentando en {wait_time:.1f}s...")
                    time.sleep(wait_time)
                else:
                    return {
                        "success": False,
                        "error": f"Error AWS después de {self.config.max_retries + 1} intentos: {error_code} - {error_message}",
                        "message": f"Error del servicio AWS: {error_code}",
                        "error_code": error_code,
                        "retry_info": {
                            "attempts": self.config.max_retries + 1,
                            "last_error_type": "ClientError"
                        }
                    }

            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries:
                    wait_time = self.config.retry_delay * (2 ** attempt)
                    print(f"⚠️  Intento {attempt + 1} falló con error inesperado. Reintentando en {wait_time:.1f}s...")
                    time.sleep(wait_time)
                else:
                    return {
                        "success": False,
                        "error": f"Error inesperado después de {self.config.max_retries + 1} intentos: {str(e)}",
                        "message": "Error inesperado al invocar el agente de Bedrock",
                        "retry_info": {
                            "attempts": self.config.max_retries + 1,
                            "last_error_type": type(e).__name__
                        }
                    }

        # Este punto no debería alcanzarse, pero por seguridad
        return {
            "success": False,
            "error": f"Error después de todos los reintentos: {str(last_error)}",
            "message": "Error al invocar el agente de Bedrock después de múltiples intentos",
        }

    def _process_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Procesa la respuesta del agente de Bedrock (event stream -> texto).
        Si el chunk final es corto (prefacio), busca la respuesta completa en el trace.

        Args:
            response: Respuesta cruda del cliente de Bedrock.

        Returns:
            Dict procesado con la respuesta.
        """
        try:
            completion = ""
            trace_data = []

            print(f"🔍 [DEBUG] Procesando respuesta del agente...")

            # Leer el stream de respuesta
            for event in response.get("completion", []):
                if "chunk" in event:
                    chunk = event["chunk"]
                    if "bytes" in chunk:
                        chunk_text = chunk["bytes"].decode("utf-8", errors="ignore")
                        completion += chunk_text
                        print(f"📝 [DEBUG] Chunk recibido: {chunk_text[:100]}...")

                if "trace" in event:
                    trace_data.append(event["trace"])
                    print(f"🔍 [DEBUG] Trace recibido: {str(event['trace'])[:200]}...")

            # Determinar la respuesta final
            final_response = completion.strip()
            response_source = "unknown"
            
            # Si el chunk final es corto (prefacio), buscar la respuesta completa en el trace
            if len(completion.strip()) < 200:  # Umbral para detectar prefacio
                print(f"🔍 [DEBUG] Chunk final corto detectado ({len(completion.strip())} chars), buscando respuesta completa en trace...")
                
                # Buscar respuesta completa en el trace usando la función proporcionada
                trace_answer = _extract_plain_answer_from_trace(trace_data)
                if trace_answer:
                    final_response = trace_answer
                    response_source = "knowledge_base"
                    print(f"✅ [DEBUG] Respuesta completa encontrada en trace: {final_response[:200]}...")
                else:
                    print(f"⚠️ [DEBUG] No se encontró respuesta completa en trace, usando completion")
            else:
                print(f"✅ [DEBUG] Chunk final largo, usando completion directamente")

            print(f"🎯 [DEBUG] Respuesta final determinada:")
            print(f"   - Fuente: {response_source}")
            print(f"   - Longitud: {len(final_response) if final_response else 0}")
            print(f"   - Preview: {final_response[:200] if final_response else 'None'}...")

            return {
                "success": True,
                "response": final_response,
                "session_id": response.get("sessionId"),
                "trace": trace_data if trace_data else None,
                "response_source": response_source,
                "debug_info": {
                    "completion_length": len(completion),
                    "trace_count": len(trace_data),
                    "is_short_completion": len(completion.strip()) < 200
                }
            }

        except Exception as e:
            print(f"❌ [DEBUG] Error procesando respuesta: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "Error al procesar la respuesta del agente",
            }

    def get_agent_info(self) -> Dict[str, Any]:
        """
        Obtiene información sobre el agente configurado.

        Returns:
            Dict con información del agente.
        """
        return {
            "agent_id": self.agent_id,
            "agent_alias_id": self.agent_alias_id,
            "region": self.config.region_name,
            "arn": getattr(self.config, "agent_arn", None),
        }

    def test_connection(self) -> Dict[str, Any]:
        """
        Prueba sencilla de conexión invocando el agente con un mensaje corto.
        (No se usa automáticamente al cargar la UI; la UI lo llama solo si haces clic en el botón.)

        Returns:
            Dict con el resultado de la prueba.
        """
        try:
            print("🔍 Probando conexión con Bedrock Agent...")
            test_response = self.invoke_agent("Hola, ¿puedes ayudarme?")
            
            if test_response["success"]:
                return {
                    "success": True,
                    "message": "✅ Conexión e invocación correctas",
                    "agent_info": self.get_agent_info(),
                    "test_response": test_response.get("response", "")[:100] + "..." if len(test_response.get("response", "")) > 100 else test_response.get("response", "")
                }
            else:
                error_msg = test_response.get("error", "Error desconocido")
                retry_info = test_response.get("retry_info", {})
                
                if retry_info:
                    return {
                        "success": False,
                        "message": f"❌ La invocación falló después de {retry_info.get('attempts', '?')} intentos",
                        "error": error_msg,
                        "retry_info": retry_info
                    }
                else:
                    return {
                        "success": False,
                        "message": "❌ La invocación no fue exitosa",
                        "error": error_msg,
                    }
        except Exception as e:
            return {
                "success": False, 
                "message": "❌ Error al probar la conexión", 
                "error": str(e)
            }


# Instancia global del servicio
bedrock_service = BedrockAgentService()
