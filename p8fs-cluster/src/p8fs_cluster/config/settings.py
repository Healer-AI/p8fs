"""Centralized P8FS configuration using Pydantic Settings."""

import os

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ..utils.env import get_env_list, get_env_port, parse_port


class P8FSConfig(BaseSettings):
    """Centralized configuration for all P8FS services."""

    model_config = SettingsConfigDict(
        env_prefix="P8FS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application Settings
    debug: bool = False
    environment: str = "development"
    log_level: str = "INFO"
    default_tenant_id: str = "tenant-test"

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: str | int = Field(default=8000)
    api_workers: int = 1
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    max_connections: int = 1000
    query_timeout: int = 30
    cache_size: str = "512MB"
    worker_threads: int = 8

    # Authentication & Security
    encryption_enabled: bool = True
    mobile_auth_enabled: bool = True
    auth_disabled: bool = False  # WARNING: Only for local testing - disables JWT validation
    tenant_id: str = "default"
    token_expiry: str = "24h"
    refresh_token_expiry: str = "7d"
    base_url: str = "http://localhost:8000"

    # JWT Configuration
    jwt_secret: str = "dev-secret-change-in-production"
    # JWT Configuration
    jwt_algorithm: str = "ES256"  # Using ES256 for ECDSA
    jwt_expiration: int = 3600
    jwt_key_data: str = ""
    jwt_private_key_pem: str = ""
    jwt_public_key_pem: str = ""
    auth_jwt_rotation_days: int = 30
    auth_jwt_issuer: str = "p8fs-auth"
    auth_jwt_audience: str = "p8fs-api"
    auth_access_token_ttl: int = 3600  # 1 hour
    auth_refresh_token_ttl: int = 2592000  # 30 days
    auth_device_code_ttl: int = 600  # 10 minutes
    auth_code_ttl: int = 600  # 10 minutes
    auth_challenge_ttl: int = 300  # 5 minutes
    auth_max_devices_per_email: int = 5

    # Development/Test Settings
    allow_email_reuse: bool = False
    skip_bucket_creation: bool = False
    dev_token_secret: str = "p8fs-dev-dHMZAB_dK8JR6ps-zLBSBTfBeoNdXu2KcpNywjDfD58"

    # OAuth 2.1 Configuration
    oauth_issuer: str = "http://localhost:8000"
    oauth_authorization_endpoint: str = "http://localhost:8000/api/v1/oauth/authorize"
    oauth_token_endpoint: str = "http://localhost:8000/api/v1/oauth/token"
    oauth_jwks_uri: str = "http://localhost:8000/api/v1/oauth/.well-known/jwks.json"
    oauth_host: str = "http://localhost:8000"

    # TiKV Storage Configuration
    # Cluster FQDNs for both PD replicas (high availability)
    tikv_endpoints: list[str] = Field(default_factory=lambda: [
        "fresh-cluster-pd-0.fresh-cluster-pd-peer.tikv-cluster.svc.cluster.local:2379",
        "fresh-cluster-pd-1.fresh-cluster-pd-peer.tikv-cluster.svc.cluster.local:2379"
    ])
    tikv_timeout: int = 30
    tikv_max_connections: int = 100
    tikv_error_log_ttl: int = 604800  # 7 days in seconds

    # SeaweedFS Configuration
    seaweedfs_master: str = "localhost:9333"
    seaweedfs_filer: str = "localhost:8888"
    seaweedfs_s3_endpoint: str = "https://s3.eepis.ai"
    seaweedfs_access_key: str = "p8fs-admin-access"
    seaweedfs_secret_key: str = "r52xFgeWpX4qnJRW78QtlhlbOt7JghMHTXwaTo2vH/o="
    seaweedfs_bucket: str = "p8fs-data"

    # NATS Configuration
    nats_url: str = "nats://localhost:4222"
    nats_host: str = "localhost"
    nats_port: int = 4222
    nats_username: str = ""
    nats_password: str = ""
    nats_max_reconnect: int = 10
    nats_reconnect_wait: int = 5

    # Monitoring & Observability
    metrics_enabled: bool = True
    metrics_port: int = 9090
    tracing_enabled: bool = Field(
        default=True,
        description="Enable OpenTelemetry tracing (auto-disabled locally, see OTEL_EXPORTER_OTLP_ENDPOINT)"
    )
    otel_export_interval: int = 30000

    # OpenTelemetry Configuration (using standard OTEL env vars)
    # Traces endpoint (gRPC) - defaults to Kubernetes cluster service
    # For local development with port forwarding: kubectl port-forward -n observability svc/otel-collector 4317:4317
    # Then set: OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317
    otel_exporter_otlp_endpoint: str = Field(
        default="otel-collector.observability.svc.cluster.local:4317",
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT",
        description="OTLP gRPC endpoint for traces (disabled locally unless explicitly set)"
    )

    # Metrics endpoint (HTTP)
    otel_exporter_otlp_metrics_endpoint: str = Field(
        default="http://localhost:4318/v1/metrics",
        validation_alias="OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    )

    # Service identification
    otel_service_name: str = Field(default="p8fs-api", validation_alias="OTEL_SERVICE_NAME")
    otel_service_version: str = Field(default="0.1.0", validation_alias="OTEL_SERVICE_VERSION")
    otel_service_namespace: str = Field(
        default="p8fs",
        validation_alias="OTEL_SERVICE_NAMESPACE",
        description="Service namespace for grouping related services"
    )

    # Deployment environment
    deployment_environment: str = Field(
        default="kubernetes", validation_alias="DEPLOYMENT_ENVIRONMENT"
    )

    # Export intervals
    otel_metric_export_interval: int = Field(
        default=30000, validation_alias="OTEL_METRIC_EXPORT_INTERVAL"
    )
    otel_trace_export_interval: int = Field(
        default=5000,
        validation_alias="OTEL_TRACE_EXPORT_INTERVAL",
        description="Interval in milliseconds for exporting traces"
    )

    # Connection settings
    otel_insecure: bool = Field(
        default=True,
        validation_alias="OTEL_EXPORTER_OTLP_INSECURE",
        description="Use insecure connection (true for internal cluster communication)"
    )

    # Encryption
    encryption_key: str = ""

    # AI/ML Configuration
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    embedding_batch_size: int = 32
    embedding_gpu_enabled: bool = False
    embedding_model_cache_dir: str = "/tmp/models"
    default_embedding_provider: str = Field(
        default="all-MiniLM-L6-v2", validation_alias="P8FS_DEFAULT_EMBEDDING_PROVIDER"
    )

    # API Keys - Accept both P8FS_* (preferred) and standard env vars as fallback
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    cerebras_api_key: str = ""

    # LLM Configuration
    default_model: str = "gpt-4.1"
    llm_provider: str = "openai"  # openai, anthropic, google, cerebras
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    # Query Engine LLM Configuration (for REM query planning)
    # Cerebras is recommended for fast query planning (~500ms vs Claude ~1800ms)
    # Note: Cerebras Qwen models provide excellent speed/quality tradeoff for query planning
    #   - Use cerebras:qwen-2.5-72b for fast, high-quality query generation
    #   - Requires CEREBRAS_API_KEY environment variable
    query_engine_provider: str = "openai"  # cerebras, anthropic, openai
    query_engine_model: str = "gpt-4.1-nano"  # openai: gpt-4.1-nano, cerebras: qwen-2.5-72b, anthropic: claude-sonnet-4-5
    query_engine_temperature: float = 0.1  # Lower temperature for more consistent query planning

    # Dreaming Worker Configuration
    dreaming_enabled: bool = True
    dreaming_lookback_hours: int = 24
    dreaming_batch_size: int = 50
    dreaming_affinity_enabled: bool = True
    dreaming_affinity_use_llm: bool = True
    dreaming_affinity_basic_batch_size: int = 50
    dreaming_affinity_llm_batch_size: int = 10
    dreaming_affinity_similarity_threshold: float = -0.5

    # Storage Provider Configuration
    storage_provider: str = "postgresql"  # postgresql, tidb, rocksdb

    # PostgreSQL Configuration
    pg_host: str = "localhost"
    pg_port: int = 5438
    pg_user: str = "postgres"
    pg_password: str = "postgres"
    pg_database: str = "app"

    # TiDB Configuration
    tidb_host: str = "localhost"
    tidb_port: int = 4000
    tidb_user: str = "root"
    tidb_password: str = ""
    tidb_database: str = "public"
    tikv_use_http_proxy: bool = True  # Use HTTP proxy for TiKV operations
    tikv_http_proxy_url: str = "https://p8fs.percolationlabs.ai"

    # Connection Pool Configuration (TiDB/MySQL)
    db_pool_enabled: bool = True
    db_pool_max_connections: int = 10
    db_pool_max_usage: int = 100  # Recycle connection after N queries
    db_pool_max_lifetime: int = 3600  # Recycle connection after N seconds (1 hour)
    db_pool_ping: int = 1  # Test connection before use (0=never, 1=always, 2=if idle)

    # RocksDB Configuration
    rocksdb_host: str = "localhost"
    rocksdb_port: int = 20160

    # Processing Settings
    max_file_size: int = 5368709120  # 5GB in bytes
    processing_timeout: int = 600  # 10 minutes

    # Worker Configuration
    local_worker_enabled: bool = False
    local_worker_thread_count: int = 2

    # Scheduler Configuration
    scheduler_enabled: bool = True
    scheduler_timezone: str = "UTC"
    scheduler_discovery_package: str = "p8fs.workers.scheduler.tasks"
    scheduler_force_inline: bool = False
    scheduler_default_worker_type: str = "default_worker"
    scheduler_default_memory: str = "256Mi"

    # MCP Server Settings
    mcp_enabled: bool = True
    mcp_server_name: str = "p8fs-mcp"
    mcp_server_version: str = "1.0.0"
    mcp_server_description: str = (
        "P8FS Model Context Protocol server for AI assistant integration"
    )
    mcp_server_instructions: str = (
        "═══════════════════════════════════════════════════════════════════════════\n"
        "EEPIS - Ever Evolving Personal Information System\n"
        "═══════════════════════════════════════════════════════════════════════════\n"
        "\n"
        "P8FS (Percolate File System) is an EEPIS - a smart memory system that grows\n"
        "and evolves with you. Unlike traditional storage that just saves files, EEPIS\n"
        "actively understands, connects, and contextualizes your information over time.\n"
        "\n"
        "**How EEPIS Works:**\n"
        "\n"
        "1. **Ingest**: You upload files, documents, voice recordings, conversations\n"
        "2. **Extract**: AI agents extract entities, relationships, and temporal context\n"
        "3. **Connect**: The system builds a semantic knowledge graph linking related content\n"
        "4. **Evolve**: As you add more data, connections strengthen and new insights emerge\n"
        "5. **Recall**: Query your memory using natural language or structured queries\n"
        "\n"
        "**Core Philosophy:**\n"
        "- Your memory should grow smarter over time, not just bigger\n"
        "- Related information should surface automatically, not require manual tags\n"
        "- Context should emerge from relationships, not predefined categories\n"
        "- Your personal knowledge graph is unique to you and evolves with your thinking\n"
        "\n"
        "═══════════════════════════════════════════════════════════════════════════\n"
        "REM - Resources, Entities, Moments (The Memory Model)\n"
        "═══════════════════════════════════════════════════════════════════════════\n"
        "\n"
        "EEPIS organizes information using the REM model - three interconnected layers:\n"
        "\n"
        "**1. RESOURCES - Raw Content**\n"
        "   - Files, documents, notes, conversations, recordings\n"
        "   - The actual content you've saved or created\n"
        "   - Immutable (never changes once stored)\n"
        "   - Tagged with entities and metadata\n"
        "\n"
        "   Example: A meeting transcript, a PDF document, a diary entry\n"
        "\n"
        "**2. ENTITIES - The \"Who\" and \"What\"**\n"
        "   - People (sarah-chen, mike-johnson)\n"
        "   - Projects (project-alpha, database-migration)\n"
        "   - Technologies (tidb, postgresql, kubernetes)\n"
        "   - Concepts (performance-optimization, authentication)\n"
        "   - Automatically extracted from resources\n"
        "   - Form the nodes of your knowledge graph\n"
        "\n"
        "   Example: From a meeting transcript, we extract entities:\n"
        "   - People: sarah-chen, mike-johnson\n"
        "   - Topics: tidb, database-migration, performance\n"
        "\n"
        "**3. MOMENTS - Temporal Context**\n"
        "   - Time-bounded events (meetings, work sessions, conversations)\n"
        "   - Who was present, what was discussed, when it happened\n"
        "   - Emotional context (emotion_tags: excited, concerned)\n"
        "   - Topics discussed (topic_tags: database-migration, api-performance)\n"
        "   - Connect resources to temporal narrative\n"
        "\n"
        "   Example: A 2-hour meeting on Nov 15, 2025\n"
        "   - present_persons: [sarah-chen, mike-johnson]\n"
        "   - topic_tags: [database-migration, tidb]\n"
        "   - emotion_tags: [optimistic, focused]\n"
        "\n"
        "**How REM Layers Work Together:**\n"
        "\n"
        "Resources → Entities → Moments → Knowledge Graph\n"
        "\n"
        "1. You upload a meeting transcript (RESOURCE)\n"
        "2. AI extracts people, topics, concepts (ENTITIES)\n"
        "3. AI creates temporal context (MOMENT)\n"
        "4. System builds connections to related resources\n"
        "5. Your knowledge graph grows and becomes queryable\n"
        "\n"
        "**Query Progression:**\n"
        "\n"
        "Stage 1 (Just Resources): \"Find files with 'Sarah'\"\n"
        "Stage 2 (With Entities): \"Show all documents Sarah worked on\"\n"
        "Stage 3 (With Moments): \"What meetings involved Sarah and Mike?\"\n"
        "Stage 4 (Full Graph): \"Show the timeline of decisions leading to TiDB migration\"\n"
        "\n"
        "═══════════════════════════════════════════════════════════════════════════\n"
        "REM QUERY EXAMPLES\n"
        "═══════════════════════════════════════════════════════════════════════════\n"
        "\n"
        "**LOOKUP - Entity-based queries**\n"
        "\n"
        "  LOOKUP \"Sarah\"              # Find all resources with entity 'Sarah'\n"
        "  LOOKUP \"project-alpha\"      # Find resources tagged with this project\n"
        "  LOOKUP \"TiDB\"               # Case-insensitive entity search\n"
        "\n"
        "═══════════════════════════════════════════════════════════════════════════\n"
    )
    mcp_auth_provider: str = "dummy"
    mcp_mount_path: str = "/mcp"

    # Email Configuration
    email_enabled: bool = True
    email_provider: str = "gmail"  # mock, gmail, sendgrid, ses
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_use_tls: bool = True
    email_username: str = "saoirse@dreamingbridge.io"
    email_password: str = ""
    email_sender_name: str = "EEPIS Moments"

    # Slack Configuration
    slack_enabled: bool = False
    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_signing_secret: str = ""

    # External Service URLs
    api_base_url: str = "https://p8fs.percolationlabs.ai"
    login_url: str = "https://auth.p8fs.io/login"
    s3_endpoint: str = "https://s3.p8fs.io"
    grpc_endpoint: str = "grpc.p8fs.io:443"
    websocket_endpoint: str = "wss://ws.p8fs.io"

    # AWS Configuration (for compatibility)
    aws_default_region: str = Field(default="us-east-1", validation_alias="AWS_DEFAULT_REGION")
    aws_region: str = Field(default="us-east-1", validation_alias="AWS_REGION")

    # Admin/Secret Configuration
    admin_token: str = ""

    @field_validator("api_port", mode="before")
    @classmethod
    def validate_api_port(cls, v):
        """Validate and parse API port, handling Kubernetes format."""
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            return parse_port(v, 8000)
        return 8000

    def __init__(self, **kwargs):
        """Initialize with environment variable parsing support."""
        super().__init__(**kwargs)

        # Parse special environment variables that need custom handling
        self._parse_special_env_vars()

    def _parse_special_env_vars(self):
        """Parse environment variables that need special handling."""
        # Parse list-type environment variables
        self.tikv_endpoints = get_env_list("P8FS_TIKV_ENDPOINTS", self.tikv_endpoints)
        self.cors_origins = get_env_list("P8FS_CORS_ORIGINS", self.cors_origins)

        # Port parsing is now handled by field validator

        # Handle compatibility environment variables (without P8FS_ prefix)
        seaweed_access = os.getenv("SEAWEEDFS_ACCESS_KEY")
        if seaweed_access and not os.getenv("P8FS_SEAWEEDFS_ACCESS_KEY"):
            self.seaweedfs_access_key = seaweed_access

        seaweed_secret = os.getenv("SEAWEEDFS_SECRET_KEY")
        if seaweed_secret and not os.getenv("P8FS_SEAWEEDFS_SECRET_KEY"):
            self.seaweedfs_secret_key = seaweed_secret

        # Handle HF_HOME for model caching
        hf_home = os.getenv("HF_HOME")
        if hf_home:
            self.embedding_model_cache_dir = hf_home

        # Handle API keys (use standard env var names if P8FS_ prefixed versions not set)
        if not os.getenv("P8FS_OPENAI_API_KEY"):
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                self.openai_api_key = openai_key

        if not os.getenv("P8FS_ANTHROPIC_API_KEY"):
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")
            if anthropic_key:
                self.anthropic_api_key = anthropic_key

        if not os.getenv("P8FS_GOOGLE_API_KEY"):
            google_key = os.getenv("GOOGLE_API_KEY")
            if google_key:
                self.google_api_key = google_key

        # Handle Slack tokens (use standard env var names if P8FS_ prefixed versions not set)
        if not os.getenv("P8FS_SLACK_BOT_TOKEN"):
            slack_bot = os.getenv("SLACK_BOT_TOKEN")
            if slack_bot:
                self.slack_bot_token = slack_bot

        if not os.getenv("P8FS_SLACK_APP_TOKEN"):
            slack_app = os.getenv("SLACK_APP_TOKEN")
            if slack_app:
                self.slack_app_token = slack_app

        if not os.getenv("P8FS_SLACK_SIGNING_SECRET"):
            slack_secret = os.getenv("SLACK_SIGNING_SECRET")
            if slack_secret:
                self.slack_signing_secret = slack_secret

    @property
    def pg_connection_string(self) -> str:
        """Build PostgreSQL connection string from individual parameters."""
        if self.pg_password:
            return f"postgresql://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        else:
            return f"postgresql://{self.pg_user}@{self.pg_host}:{self.pg_port}/{self.pg_database}"

    @property
    def pg_async_connection_string(self) -> str:
        """Build async PostgreSQL connection string."""
        if self.pg_password:
            return f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        else:
            return f"postgresql+asyncpg://{self.pg_user}@{self.pg_host}:{self.pg_port}/{self.pg_database}"

    @property
    def tidb_connection_string(self) -> str:
        """Build TiDB connection string from individual parameters."""
        if self.tidb_password:
            return f"mysql://{self.tidb_user}:{self.tidb_password}@{self.tidb_host}:{self.tidb_port}/{self.tidb_database}"
        else:
            return f"mysql://{self.tidb_user}@{self.tidb_host}:{self.tidb_port}/{self.tidb_database}"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() in ("production", "prod")

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() in ("development", "dev")

    @property
    def is_testing(self) -> bool:
        """Check if running in test environment."""
        return self.environment.lower() in ("test", "testing")

    def parse_model_spec(self, model_spec: str | None = None) -> tuple[str | None, str]:
        """Parse model specification with optional provider prefix.

        Supports 'provider:model' syntax to explicitly override provider inference.
        Examples:
            'gpt-4.1' -> (None, 'gpt-4.1')  # Provider inferred from model name
            'openai:gpt-4.1' -> ('openai', 'gpt-4.1')  # Explicit provider
            'anthropic:claude-sonnet-4-5' -> ('anthropic', 'claude-sonnet-4-5')

        Args:
            model_spec: Model specification string. If None, uses query_engine_model.

        Returns:
            Tuple of (provider, model_name). Provider is None if not explicitly specified.
        """
        spec = model_spec or self.query_engine_model

        if ":" in spec:
            provider, model_name = spec.split(":", 1)
            return (provider, model_name)

        return (None, spec)


# Global configuration instance
config = P8FSConfig()
