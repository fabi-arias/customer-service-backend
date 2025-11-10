# src/config/secrets.py

import os
import json
import threading
import time
import logging
from pathlib import Path

from typing import Optional, Dict

import boto3
from botocore.exceptions import ClientError

# Cargar variables de entorno desde .env si existe (para desarrollo local)
try:
    from dotenv import load_dotenv
    # Buscar .env en el directorio raíz del proyecto (dos niveles arriba desde src/config/)
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # python-dotenv no está instalado, continuar sin él
    pass

logger = logging.getLogger(__name__)

DEFAULT_REGION = os.getenv("AWS_REGION", "us-east-1")
SECRET_ID = os.getenv("SECRETS_MANAGER_ID", "sot-env")
REFRESH_SECONDS = int(os.getenv("SECRETS_REFRESH_SECONDS", "300"))


class SecretsStore:
    def __init__(self, secret_id: str = SECRET_ID, region: str = DEFAULT_REGION, auto_refresh: bool = True):
        self._secret_id = secret_id
        self._region = region
        self._data: Dict[str, str] = {}
        self._loaded = False
        self._load_error = False
        self._lock = threading.RLock()
        self._client = None

        # Intentar inicializar el cliente, pero no fallar si no hay credenciales
        try:
            self._client = boto3.client("secretsmanager", region_name=region)
        except Exception as e:
            logger.warning(f"No se pudo inicializar cliente de Secrets Manager: {e}. Se usarán variables de entorno y valores por defecto.")

        if auto_refresh and self._client:
            threading.Thread(target=self._refresher, daemon=True).start()

    def _fetch(self) -> Dict[str, str]:
        if not self._client:
            raise RuntimeError("Cliente de Secrets Manager no disponible")
        r = self._client.get_secret_value(SecretId=self._secret_id)
        raw = r.get("SecretString") or r.get("SecretBinary")
        txt = raw if isinstance(raw, str) else raw.decode("utf-8")
        data = json.loads(txt)
        return {k: (str(v) if v is not None else "") for k, v in data.items()}

    def load(self):
        """Intenta cargar secrets, pero no falla si no puede conectarse."""
        if not self._client:
            return
        try:
            with self._lock:
                self._data = self._fetch()
                self._loaded = True
                self._load_error = False
        except Exception as e:
            logger.debug(f"No se pudo cargar secret desde AWS Secrets Manager: {e}")
            self._load_error = True
            # No lanzar excepción, permitir que continúe con valores por defecto

    def refresh(self):
        """Intenta refrescar secrets, pero no falla si no puede conectarse."""
        if not self._client:
            return
        try:
            new_data = self._fetch()
            with self._lock:
                self._data = new_data
                self._loaded = True
                self._load_error = False
        except Exception as e:
            logger.debug(f"No se pudo refrescar secret desde AWS Secrets Manager: {e}")
            # No lanzar excepción, mantener datos existentes

    def _refresher(self):
        """Thread que refresca secrets periódicamente."""
        if not self._client:
            return
        backoff = 2
        while not self._loaded and not self._load_error:
            try:
                self.load()
                break
            except Exception:
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)

        while True:
            time.sleep(REFRESH_SECONDS)
            self.refresh()

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        # ENV (override) > secreto > default
        v = os.getenv(key)
        if v is not None:
            return v

        # Si no hay cliente, retornar default inmediatamente
        if not self._client:
            return default

        # Intentar cargar si no está cargado, pero no fallar si no puede
        with self._lock:
            if not self._loaded and not self._load_error:
                try:
                    self.load()
                except Exception:
                    # Si falla, marcar como error y continuar con default
                    self._load_error = True
                    return default
            
            # Si está cargado, buscar en los datos
            if self._loaded:
                return self._data.get(key, default)
            else:
                # Si no se pudo cargar, retornar default
                return default


secrets = SecretsStore()


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    return secrets.get(key, default)

