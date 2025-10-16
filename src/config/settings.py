# src/config/settings.py
import os
import dotenv

dotenv.load_dotenv()

class Settings:
    """Configuración general de la aplicación."""
    
    @property
    def app_name(self) -> str:
        """Nombre de la aplicación."""
        return "ChatMuscle"

class HubSpotConfig:
    """Configuración para la API de HubSpot."""
    
    @property
    def token(self) -> str:
        """Token de autenticación de HubSpot."""
        token = os.getenv("HUBSPOT_TOKEN")
        if not token:
            raise ValueError("HUBSPOT_TOKEN no está configurado en las variables de entorno")
        return token
    
    @property
    def base_url(self) -> str:
        """URL base de la API de HubSpot."""
        return os.getenv("HUBSPOT_BASE_URL", "https://api.hubapi.com")

class BedrockConfig:
    """Configuración para Amazon Bedrock Agent."""
    
    @property
    def aws_access_key_id(self) -> str:
        """AWS Access Key ID."""
        key = os.getenv("AWS_ACCESS_KEY_ID")
        if not key:
            raise ValueError("AWS_ACCESS_KEY_ID no está configurado en las variables de entorno")
        return key
    
    @property
    def aws_secret_access_key(self) -> str:
        """AWS Secret Access Key."""
        key = os.getenv("AWS_SECRET_ACCESS_KEY")
        if not key:
            raise ValueError("AWS_SECRET_ACCESS_KEY no está configurado en las variables de entorno")
        return key
    
    @property
    def region_name(self) -> str:
        """Región de AWS."""
        return os.getenv("AWS_REGION", "us-east-1")
    
    @property
    def agent_id(self) -> str:
        """ID del agente de Bedrock."""
        return os.getenv("BEDROCK_AGENT_ID", "PJSUJU8ACS")
    
    @property
    def agent_alias_id(self) -> str:
        """ID del alias del agente."""
        return os.getenv("BEDROCK_AGENT_ALIAS_ID", "customer-service")
    
    @property
    def agent_arn(self) -> str:
        """ARN completo del agente."""
        return os.getenv("BEDROCK_AGENT_ARN", "arn:aws:bedrock:us-east-1:792655899277:agent/PJSUJU8ACS")
    
    @property
    def connect_timeout(self) -> int:
        """Timeout de conexión en segundos."""
        return int(os.getenv("BEDROCK_CONNECT_TIMEOUT", "30"))
    
    @property
    def read_timeout(self) -> int:
        """Timeout de lectura en segundos."""
        return int(os.getenv("BEDROCK_READ_TIMEOUT", "120"))
    
    @property
    def max_retries(self) -> int:
        """Número máximo de reintentos."""
        return int(os.getenv("BEDROCK_MAX_RETRIES", "3"))
    
    @property
    def retry_delay(self) -> float:
        """Delay entre reintentos en segundos."""
        return float(os.getenv("BEDROCK_RETRY_DELAY", "2.0"))

class PostgresConfig:
    """Configuración para Postgres (RDS)."""
    
    @property
    def host(self) -> str:
        return os.getenv("DB_HOST")
    
    @property
    def port(self) -> int:
        return int(os.getenv("DB_PORT", "5432"))
    
    @property
    def name(self) -> str:
        return os.getenv("DB_NAME")
    
    @property
    def user(self) -> str:
        return os.getenv("DB_USER")
    
    @property
    def password(self) -> str:
        return os.getenv("DB_PASSWORD")
    

# Instancias globales de configuración
settings = Settings()
hubspot_config = HubSpotConfig()
bedrock_config = BedrockConfig()
postgres_config = PostgresConfig()