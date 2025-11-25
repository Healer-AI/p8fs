"""Configuration settings for P8FS API."""


from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Server Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    reload: bool = False
    debug: bool = False
    
    # CORS Configuration
    cors_origins: list[str] = ["*"]
    cors_credentials: bool = True
    cors_methods: list[str] = ["*"]
    cors_headers: list[str] = ["*"]
    
    # Authentication
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60
    
    # External Services
    auth_service_url: str = "http://localhost:8001"
    core_service_url: str = "http://localhost:8002"  
    node_service_url: str = "http://localhost:8003"
    
    # Request Configuration
    max_upload_size: int = 100 * 1024 * 1024  # 100MB
    request_timeout: int = 30
    
    # Observability
    enable_metrics: bool = True
    enable_tracing: bool = True
    log_level: str = "INFO"
    
    # Rate Limiting
    rate_limit_enabled: bool = True
    default_rate_limit: str = "100/minute"


# Global settings instance
settings = Settings()