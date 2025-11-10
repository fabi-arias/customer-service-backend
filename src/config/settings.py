# src/config/settings.py
from config.secrets import get_secret


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
        v = get_secret("HUBSPOT_TOKEN")
        if not v:
            raise ValueError("HUBSPOT_TOKEN no está configurado")
        return v
    
    @property
    def base_url(self) -> str:
        """URL base de la API de HubSpot."""
        return get_secret("HUBSPOT_BASE_URL", "https://api.hubapi.com") or "https://api.hubapi.com"


class BedrockConfig:
    """Configuración para Amazon Bedrock Agent."""
    
    
    #@property
    #def aws_access_key_id(self) -> str:
    #    """AWS Access Key ID."""
    #    key = get_secret("AWS_ACCESS_KEY_ID")
    #    if not key:
    #        raise ValueError("AWS_ACCESS_KEY_ID no está configurado")
    #    return key
    
    #@property
    #def aws_secret_access_key(self) -> str:
    #    """AWS Secret Access Key."""
    #    key = get_secret("AWS_SECRET_ACCESS_KEY")
    #    if not key:
    #        raise ValueError("AWS_SECRET_ACCESS_KEY no está configurado")
    #    return key
    
    @property
    def region_name(self) -> str:
        """Región de AWS."""
        return get_secret("AWS_REGION", "us-east-1") or "us-east-1"
    
    @property
    def agent_id(self) -> str:
        """ID del agente de Bedrock."""
        return get_secret("BEDROCK_AGENT_ID", "PJSUJU8ACS") or "PJSUJU8ACS"
    
    @property
    def agent_alias_id(self) -> str:
        """ID del alias del agente."""
        return get_secret("BEDROCK_AGENT_ALIAS_ID", "customer-service") or "customer-service"
    
    @property
    def agent_arn(self) -> str:
        """ARN completo del agente."""
        return get_secret("BEDROCK_AGENT_ARN", "arn:aws:bedrock:us-east-1:792655899277:agent/PJSUJU8ACS") or "arn:aws:bedrock:us-east-1:792655899277:agent/PJSUJU8ACS"
    
    @property
    def connect_timeout(self) -> int:
        """Timeout de conexión en segundos."""
        return int(get_secret("BEDROCK_CONNECT_TIMEOUT", "30") or "30")
    
    @property
    def read_timeout(self) -> int:
        """Timeout de lectura en segundos."""
        return int(get_secret("BEDROCK_READ_TIMEOUT", "120") or "120")
    
    @property
    def max_retries(self) -> int:
        """Número máximo de reintentos."""
        return int(get_secret("BEDROCK_MAX_RETRIES", "3") or "3")
    
    @property
    def retry_delay(self) -> float:
        """Delay entre reintentos en segundos."""
        return float(get_secret("BEDROCK_RETRY_DELAY", "2.0") or "2.0")


class PostgresConfig:
    """Configuración para Postgres (RDS)."""
    
    @property
    def host(self) -> str:
        return get_secret("DB_HOST", "") or ""
    
    @property
    def port(self) -> int:
        return int(get_secret("DB_PORT", "5432") or "5432")
    
    @property
    def name(self) -> str:
        return get_secret("DB_NAME", "") or ""
    
    @property
    def user(self) -> str:
        return get_secret("DB_USER", "") or ""
    
    @property
    def password(self) -> str:
        return get_secret("DB_PASSWORD", "") or ""


class AppAuthConfig:
    """Configuración para autenticación de API."""
    
    @property
    def ingest_api_key(self) -> str:
        return get_secret("INGEST_API_KEY", "") or ""
    
    @property
    def ui_hint_secret(self) -> str:
        return get_secret("UI_HINT_SECRET", "") or ""


class CognitoConfig:
    """Configuración para Amazon Cognito."""
    
    @property
    def region(self) -> str:
        return get_secret("COGNITO_REGION", "us-east-1") or "us-east-1"
    
    @property
    def user_pool_id(self) -> str:
        return get_secret("COGNITO_USER_POOL_ID", "") or ""
    
    @property
    def client_id(self) -> str:
        return get_secret("COGNITO_CLIENT_ID", "") or ""
    
    @property
    def client_secret(self) -> str:
        return get_secret("COGNITO_CLIENT_SECRET", "") or ""
    
    @property
    def domain(self) -> str:
        return get_secret("COGNITO_DOMAIN", "") or ""
    
    @property
    def redirect_uri(self) -> str:
        return get_secret("OAUTH_REDIRECT_URI", "") or ""


# Instancias globales de configuración
settings = Settings()
hubspot_config = HubSpotConfig()
bedrock_config = BedrockConfig()
postgres_config = PostgresConfig()
appauth_config = AppAuthConfig()
cognito_config = CognitoConfig()