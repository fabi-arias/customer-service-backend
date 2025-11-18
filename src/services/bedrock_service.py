# src/services/bedrock_service.py
import boto3
import uuid
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
from botocore.config import Config
from botocore.exceptions import ClientError, ReadTimeoutError, ConnectTimeoutError

# Agregar el directorio src al path para imports (manteniendo tu patrón actual)
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from config.settings import bedrock_config


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
            # aws_access_key_id=self.config.aws_access_key_id,
            # aws_secret_access_key=self.config.aws_secret_access_key,
            region_name=self.config.region_name,
            config=config
        )
        self.agent_id = self.config.agent_id
        self.agent_alias_id = self.config.agent_alias_id

    def invoke_agent(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        enable_trace: bool = False,
        session_attributes: Optional[Dict[str, str]] = None,
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

        params = {
            "agentId": self.agent_id,
            "agentAliasId": self.agent_alias_id,
            "sessionId": session_id,
            "inputText": user_input,
            "enableTrace": enable_trace,
        }

        if session_attributes:
            # Bedrock Agents espera este shape para compartir contexto
            params["sessionState"] = {
                "sessionAttributes": {k: str(v) for k, v in session_attributes.items()}
            }

        print("\n🟣 [DEBUG] Parámetros de invoke_agent enviados a Bedrock:")
        print(f"   sessionId: {session_id}")
        preview = user_input if len(user_input) < 300 else user_input[:300] + "…"
        print(f"   inputText: {preview}")
        if "sessionState" in params:
            print(f"   sessionState.sessionAttributes:")
            for k, v in params["sessionState"]["sessionAttributes"].items():
                print(f"      {k}: {v}")
        else:
            print("   (sin sessionState)")

        # Lógica de reintentos
        last_error = None
        for attempt in range(self.config.max_retries + 1):
            try:
                # Invocar el agente (respuesta por event stream)
                response = self.client.invoke_agent(**params)
                
                # Procesar la respuesta (pasar session_id para devolverlo)
                return self._process_response(response, session_id)

            except (ReadTimeoutError, ConnectTimeoutError) as e:
                last_error = e
                error_type = (
                    "timeout de lectura"
                    if isinstance(e, ReadTimeoutError)
                    else "timeout de conexión"
                )
                
                if attempt < self.config.max_retries:
                    wait_time = self.config.retry_delay * (2 ** attempt)  # Backoff exponencial
                    print(
                        f"⚠️  Intento {attempt + 1} falló por {error_type}. "
                        f"Reintentando en {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                else:
                    return {
                        "success": False,
                        "error": f"Timeout después de {self.config.max_retries + 1} intentos: {str(e)}",
                        "message": f"El agente tardó demasiado en responder. Último error: {error_type}",
                        "session_id": session_id,
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
                        "error_code": error_code,
                        "session_id": session_id,
                    }
                
                last_error = e
                if attempt < self.config.max_retries:
                    wait_time = self.config.retry_delay * (2 ** attempt)
                    print(
                        f"⚠️  Intento {attempt + 1} falló con error AWS: {error_code}. "
                        f"Reintentando en {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                else:
                    return {
                        "success": False,
                        "error": (
                            f"Error AWS después de {self.config.max_retries + 1} intentos: "
                            f"{error_code} - {error_message}"
                        ),
                        "message": f"Error del servicio AWS: {error_code}",
                        "error_code": error_code,
                        "session_id": session_id,
                        "retry_info": {
                            "attempts": self.config.max_retries + 1,
                            "last_error_type": "ClientError"
                        }
                    }

            except Exception as e:
                last_error = e
                if attempt < self.config.max_retries:
                    wait_time = self.config.retry_delay * (2 ** attempt)
                    print(
                        f"⚠️  Intento {attempt + 1} falló con error inesperado "
                        f"({type(e).__name__}). Reintentando en {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                else:
                    return {
                        "success": False,
                        "error": (
                            f"Error inesperado después de {self.config.max_retries + 1} intentos: "
                            f"{str(e)}"
                        ),
                        "message": "Error inesperado al invocar el agente de Bedrock",
                        "session_id": session_id,
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
            "session_id": session_id,
        }

    def _process_response(self, response: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """
        Procesa la respuesta del agente de Bedrock (event stream -> texto) y
        extrae/imprime trazas útiles para depuración.
        
        Args:
            response: Respuesta del cliente de Bedrock (event stream)
            session_id: ID de sesión usado en la invocación (Bedrock no lo devuelve en el stream)
        """
        try:
            completion_text = ""
            raw_traces = []
            trace_summary = {
                "routed_agent": None,          # p.ej. SpotMetrics / SpotTransactional / SpotKnowledge
                "last_action_group": None,     # p.ej. "Analytics"
                "last_api_path": None,         # p.ej. "/analytics/closed_volume"
                "tool_invocations": [],        # lista de objetos {"actionGroup":..., "apiPath":..., "httpMethod":..., "status":...}
                "notes": []                    # strings breves con hints detectados
            }

            for event in response.get("completion", []):
                # chunks de texto
                if "chunk" in event:
                    chunk = event["chunk"]
                    if "bytes" in chunk:
                        completion_text += chunk["bytes"].decode("utf-8", errors="ignore")

                # trazas
                if "trace" in event:
                    t = event["trace"]
                    raw_traces.append(t)

                    # ---- Heurísticas genéricas (no dependen de un schema estricto) ----
                    # 1) ¿Viene info del enrutador/orquestador?
                    joined_keys = " ".join(t.keys())
                    if "route" in joined_keys or "orchestrat" in joined_keys:
                        trace_summary["notes"].append("orchestrator_trace_detected")

                    # 2) ¿Se invocó un Action Group? (p.ej. SpotMetrics/OpenAPI)
                    action_group = (
                        t.get("actionGroup")
                        or t.get("action_group")
                        or t.get("toolName")
                        or t.get("name")
                    )
                    api_path = t.get("apiPath") or t.get("path") or t.get("endpoint")
                    http_method = t.get("httpMethod") or t.get("method")
                    status = (
                        t.get("httpStatusCode")
                        or t.get("statusCode")
                        or t.get("status")
                    )

                    # Si parece un tool/action invocation, lo agregamos
                    if action_group or api_path or http_method or status:
                        trace_summary["tool_invocations"].append({
                            "actionGroup": action_group,
                            "apiPath": api_path,
                            "httpMethod": http_method,
                            "status": status
                        })
                        if action_group and not trace_summary["last_action_group"]:
                            trace_summary["last_action_group"] = action_group
                        if api_path:
                            trace_summary["last_api_path"] = api_path

                    # 3) ¿Podemos inferir el sub-agente?
                    if action_group == "Analytics":
                        trace_summary["routed_agent"] = (
                            trace_summary["routed_agent"] or "SpotMetrics"
                        )

                    # 4) Pistas del orquestador (si usa etiquetas de agente)
                    for k, v in t.items():
                        if isinstance(v, str) and v in (
                            "SpotMetrics",
                            "SpotTransactional",
                            "SpotKnowledge",
                        ):
                            trace_summary["routed_agent"] = v
                            break

            # ---- PRINTS de DEBUG (bonitos) ----
            print("🟣 [DEBUG] Bedrock _process_response → resumen de trazas:")
            print(f"   routed_agent: {trace_summary['routed_agent']}")
            print(f"   last_action_group: {trace_summary['last_action_group']}")
            print(f"   last_api_path: {trace_summary['last_api_path']}")
            if trace_summary["tool_invocations"]:
                print("   tool_invocations:")
                for i, inv in enumerate(trace_summary["tool_invocations"], 1):
                    print(
                        f"     #{i} AG={inv.get('actionGroup')} "
                        f"{inv.get('httpMethod')} {inv.get('apiPath')} → {inv.get('status')}"
                    )
            else:
                print("   tool_invocations: (none)")

            print("\n🟣 [DEBUG FRONTEND] === Respuesta completa procesada ===")
            print("🟣 session_id devuelto:", session_id)

            print("🟣 Texto generado por el agente:")
            preview = (
                completion_text[:500] + "..."
                if len(completion_text) > 500
                else completion_text
            )
            print(preview)

            print("\n🟣 RAW TRACES:")
            for i, t in enumerate(raw_traces, 1):
                print(f"--- Trace #{i} ---")
                print(t)

            print("\n🟣 TRACE SUMMARY:")
            print(trace_summary)

            return {
                "success": True,
                "response": completion_text.strip(),
                "session_id": session_id,
                "trace": raw_traces,
                "trace_summary": trace_summary,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Error al procesar la respuesta del agente",
                "session_id": session_id,
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
                text = test_response.get("response", "") or ""
                return {
                    "success": True,
                    "message": "✅ Conexión e invocación correctas",
                    "agent_info": self.get_agent_info(),
                    "test_response": (
                        text[:100] + "..." if len(text) > 100 else text
                    ),
                }
            else:
                error_msg = test_response.get("error", "Error desconocido")
                retry_info = test_response.get("retry_info", {})
                
                if retry_info:
                    return {
                        "success": False,
                        "message": (
                            f"❌ La invocación falló después de "
                            f"{retry_info.get('attempts', '?')} intentos"
                        ),
                        "error": error_msg,
                        "retry_info": retry_info,
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
                "error": str(e),
            }


# Instancia global del servicio
bedrock_service = BedrockAgentService()