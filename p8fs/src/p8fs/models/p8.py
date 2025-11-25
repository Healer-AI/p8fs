"""P8FS core model types ported from original P8FS implementation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from .base import AbstractEntityModel, AbstractModel
from .fields import DefaultEmbeddingField

from uuid import uuid4

# Enums
class JobStatus(str, Enum):
    """Job execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRY = "retry"


class JobType(str, Enum):
    """Type of job to be executed."""

    BATCH_COMPLETION = "batch_completion"
    EMBEDDING_GENERATION = "embedding_generation"
    DATA_PROCESSING = "data_processing"
    ANALYSIS = "analysis"
    SYNC = "sync"


class SessionType(str, Enum):
    """Type of user session."""

    CHAT = "chat"
    API = "api"
    BATCH = "batch"
    ANALYSIS = "analysis"
    DREAMING = "dreaming"
    ASSISTANT_CHAT_RESPONSE = "assistant-chat-response"


class EncryptionKeyOwner(str, Enum):
    """Who owns/manages the encryption key for a resource."""

    USER = "USER"  # User-managed encryption (client-side keys)
    SYSTEM = "SYSTEM"  # System-managed encryption (server-side keys)
    NONE = "NONE"  # No encryption


class ChannelType(str, Enum):
    """Communication channel type."""

    SLACK = "slack"
    WEB = "web"
    API = "api"
    EMAIL = "email"
    MOBILE = "mobile"


# Core Models
class Function(AbstractEntityModel):
    """External tools/functions available to agents."""

    key: str | None = Field(None, description="Function identifier key")
    name: str = Field(..., description="Function name")
    verb: str | None = Field(None, description="HTTP verb if applicable")
    endpoint: str | None = Field(None, description="API endpoint")
    description: str | None = Field(None, description="Function description")
    function_spec: dict[str, Any] | None = Field(
        None, description="OpenAPI function specification"
    )
    proxy_uri: str | None = Field(None, description="Proxy URI namespace")

    model_config = {
        "key_field": "key",
        "table_name": "functions",
        "description": "External tools and functions for agent execution",
    }

    @model_validator(mode="before")
    @classmethod
    def generate_function_id(cls, values):
        """Generate ID from name and proxy_uri if not provided."""
        # Implementation stub - should generate ID from name+proxy_uri
        return values


class ApiProxy(AbstractEntityModel):
    """API proxy configuration with attached functions."""

    name: str | None = Field(None, description="Proxy display name")
    proxy_uri: str = Field(..., description="Base URI for the proxy")
    token: str | None = Field(None, description="Authentication token")

    model_config = {
        "key_field": "proxy_uri",
        "table_name": "api_proxies",
        "description": "API endpoint proxies with function registration",
    }

    @model_validator(mode="before")
    @classmethod
    def generate_proxy_defaults(cls, values):
        """Generate name and ID from proxy_uri if not provided."""
        # Implementation stub - should auto-generate from proxy_uri
        return values


class LanguageModelApi(AbstractEntityModel):
    """Language model API configuration."""

    name: str = Field(..., description="API provider name")
    model: str | None = Field(None, description="Model identifier")
    scheme: str | None = Field("https", description="URI scheme")
    completions_uri: str = Field(..., description="Completions endpoint URI")
    token_env_key: str | None = Field(
        None, description="Environment variable for token"
    )
    token: str | None = Field(None, description="Direct token value")

    model_config = {
        "key_field": "name",
        "table_name": "language_model_apis",
        "description": "Language model API configurations",
    }

    @field_validator("model")
    @classmethod
    def default_model_to_name(cls, v, info):
        """Default model to name if not provided."""
        # Implementation stub - should default model to name
        return v


class Agent(AbstractEntityModel):
    """AI agent configuration with system prompts and capabilities."""
    name: str = Field(..., description="Agent name")
    category: str | None = Field(None, description="Agent category")
    description: str | None = DefaultEmbeddingField(
        None, description="Agent description for semantic search"
    )
    spec: str | None = Field(None, description="System prompt specification")
    functions: list[Function] | None = Field(
        default_factory=list, description="Available functions"
    )
    metadata: dict[str, Any] | None = Field(
        default_factory=dict, description="Additional metadata"
    )

    model_config = {
        "key_field": "name",
        "table_name": "agents",
        "description": "AI agents with system prompts and capabilities",
    }

    @classmethod
    def get_embedding_column_values(
        cls, entities: list[dict]
    ) -> tuple[list[str], list[dict]]:
        """Extract actual text values to embed and metadata about them."""
        # Get embedding fields from the model schema instead of hardcoding
        embedding_columns = cls.get_embedding_fields()

        values_to_embed = []
        metadata = []  # track which entity/column each value belongs to

        for entity_idx, entity in enumerate(entities):
            for column in embedding_columns:
                if column in entity and entity[column]:
                    values_to_embed.append(entity[column])
                    metadata.append(
                        {
                            "entity_idx": entity_idx,
                            "column_name": column,
                        }
                    )

        return values_to_embed, metadata

    @classmethod
    def build_embedding_records(
        cls,
        entity_ids: list[str],
        column_metadata: list[dict],
        embedding_vectors: list[list[float]],
        tenant_id: str,
        embedding_provider: str = "openai",
    ) -> list[dict]:
        """Build embedding records from metadata and vectors."""
        from ..utils import make_uuid

        records = []

        for i, (metadata, vector) in enumerate(zip(column_metadata, embedding_vectors)):
            entity_idx = metadata["entity_idx"]
            entity_id = entity_ids[entity_idx]

            records.append(
                {
                    "id": make_uuid(
                        f"{entity_id}:{metadata['column_name']}:{embedding_provider}"
                    ),
                    "entity_id": entity_id,
                    "field_name": metadata["column_name"],
                    "embedding_provider": embedding_provider,
                    "embedding_vector": vector,
                    "tenant_id": tenant_id,
                    "vector_dimension": len(vector),
                }
            )

        return records

    @classmethod
    def create_research_agent(cls) -> "Agent":
        """Create a research-focused agent with appropriate capabilities."""
        return cls(
            id=str(uuid4()),
            name="p8-research",
            category="research",
            description="Research agent specialized in information gathering and analysis",
            spec="""You are a research assistant focused on gathering, analyzing, and synthesizing information.
                    Your core capabilities include:
                    - Searching for relevant resources and documents
                    - Analyzing data and extracting key insights
                    - Providing comprehensive research summaries
                    - Identifying trends and patterns in information

                    Always provide well-structured, evidence-based responses with proper citations when available.""",
            functions=[],
            metadata={"type": "research", "version": "1.0"},
        )

    @classmethod
    def create_analysis_agent(cls) -> "Agent":
        """Create an analysis-focused agent with data processing capabilities."""
        return cls(
            id=str(uuid4()),
            name="p8-analysis",
            category="analysis",
            description="Analysis agent specialized in data processing and interpretation",
            spec="""You are an analysis specialist focused on data interpretation and insights generation.
            Your core capabilities include:
            - Processing and analyzing structured and unstructured data
            - Identifying patterns, trends, and anomalies
            - Creating summaries and reports
            - Providing actionable insights and recommendations

            Always provide detailed analysis with clear reasoning and supporting evidence.""",
            functions=[],
            metadata={"type": "analysis", "version": "1.0"},
        )


class TokenUsage(AbstractEntityModel):
    """Token usage tracking for LLM API calls."""

    model_name: str = Field(..., description="Language model identifier")
    tokens: int | None = Field(None, description="Total tokens used")
    tokens_in: int = Field(0, description="Input tokens")
    tokens_out: int = Field(0, description="Output tokens")
    tokens_other: int = Field(0, description="Other tokens (reasoning, etc.)")
    session_id: str | None = Field(None, description="Associated session ID")

    model_config = {
        "key_field": "id",
        "table_name": "token_usage",
        "description": "Token consumption tracking for billing and monitoring",
    }

    @model_validator(mode="before")
    @classmethod
    def calculate_total_tokens(cls, values):
        """Calculate total tokens if not provided."""
        # Implementation stub - should calculate tokens from components
        return values


class Session(AbstractEntityModel):
    """User interaction session tracking."""

    name: str | None = Field(None, description="Session display name")
    query: str | None = DefaultEmbeddingField(
        None, description="Initial user query for semantic search"
    )
    user_rating: int | None = Field(None, description="User satisfaction rating")
    agent: str | None = Field(None, description="Primary agent used")
    parent_session_id: str | None = Field(None, description="Parent session reference")
    thread_id: str | None = Field(None, description="Conversation thread ID")
    channel_id: str | None = Field(None, description="Communication channel ID")
    channel_type: ChannelType | None = Field(
        None, description="Type of communication channel"
    )
    session_type: SessionType | None = Field(
        SessionType.CHAT, description="Session type"
    )
    metadata: dict[str, Any] | None = Field(
        default_factory=dict, description="Session metadata"
    )
    session_completed_at: datetime | None = Field(
        None, description="Session completion timestamp"
    )
    graph_paths: list[str] | None = Field(
        default_factory=list, description="Knowledge graph paths"
    )
    userid: str | None = Field(None, description="User identifier")
    moment_id: str | None = Field(
        None, description="Optional reference to associated Moment entity ID"
    )

    model_config = {
        "key_field": "id",
        "table_name": "sessions",
        "description": "User interaction sessions and conversation tracking",
        "indexed": ["moment_id"],
    }

    @classmethod
    async def summarize_user(
        cls,
        tenant_id: str,
        max_sessions: int = 100,
        max_moments: int = 20,
        max_resources: int = 20,
        max_files: int = 10
    ) -> dict[str, Any]:
        """
        Convenience method to summarize user activity.

        This delegates to the dreaming worker's summarize_user function.

        Args:
            tenant_id: Tenant identifier
            max_sessions: Maximum number of recent chat sessions to analyze
            max_moments: Maximum number of recent moment keys to include
            max_resources: Maximum number of recent resource keys to include
            max_files: Maximum number of recent file uploads to include

        Returns:
            Dictionary with summary results
        """
        from p8fs.workers.dreaming import summarize_user
        return await summarize_user(
            tenant_id=tenant_id,
            max_sessions=max_sessions,
            max_moments=max_moments,
            max_resources=max_resources,
            max_files=max_files
        )


# @deprecate for p8fs - we probably can focus on tenants but lets leave it here for now as it may be useful for user group modelling
class User(AbstractEntityModel):
    """User profile and authentication information."""

    name: str | None = Field(None, description="User display name")
    email: str | None = Field(None, description="Email address")
    slack_id: str | None = Field(None, description="Slack user ID")
    linkedin: str | None = Field(None, description="LinkedIn profile URL")
    twitter: str | None = Field(None, description="Twitter handle")
    description: str | None = DefaultEmbeddingField(
        None, description="User bio/description for personalization"
    )
    recent_threads: list[str] | None = Field(
        default_factory=list, description="Recent conversation threads"
    )
    last_ai_response: str | None = Field(None, description="Last AI response received")
    interesting_entity_keys: list[str] | None = Field(
        default_factory=list, description="Entities of interest"
    )
    token: str | None = Field(None, description="Authentication token")
    token_expiry: datetime | None = Field(None, description="Token expiration time")
    session_id: str | None = Field(None, description="Current session ID")
    last_session_at: datetime | None = Field(None, description="Last session timestamp")
    roles: list[str] | None = Field(default_factory=list, description="User roles")
    role_level: int | None = Field(0, description="User access level")
    graph_paths: list[str] | None = Field(
        default_factory=list, description="Knowledge graph paths"
    )
    metadata: dict[str, Any] | None = Field(
        default_factory=dict, description="User metadata"
    )
    email_subscription_active: bool | None = Field(
        True, description="Email subscription status"
    )
    userid: str | None = Field(None, description="External user ID")

    model_config = {
        "key_field": "email",
        "table_name": "users",
        "description": "User profiles and authentication data",
        "indexed": ["email", "slack_id"],
    }

    def as_memory(self) -> dict[str, Any]:
        """Convert user to memory representation."""
        # Implementation stub - should return memory-safe user representation
        return {}

    @classmethod
    def id_from_email(cls, email: str) -> str:
        """Generate user ID from email address."""
        # Implementation stub - should generate consistent ID from email
        return f"user:{email}"


class InlineEdge(AbstractModel):
    """
    REM knowledge graph edge representation with natural, user-friendly labels.

    Edges connect resources using natural names that match how entities are labeled.
    REM LOOKUP finds ALL entities with matching labels; LLM resolves ambiguity.

    **Key Design Principles:**
    - dst uses natural entity names (e.g., "TiDB Migration Spec", "Sarah Chen")
    - rel_type describes relationship semantics (e.g., "builds-on", "authored_by")
    - weight represents relationship strength (0.0-1.0), not confidence
    - properties stores rich metadata about the relationship

    **Edge Weight Guidelines:**
    - 1.0: Primary/strong relationships (authored_by, owns, part_of)
    - 0.8-0.9: Important relationships (depends_on, reviewed_by, implements)
    - 0.5-0.7: Secondary relationships (references, related_to, inspired_by)
    - 0.3-0.4: Weak relationships (mentions, cites)

    **Entity Type Convention (dst_entity_type):**
    - Format: [table:]<category>[/<subcategory>]
    - Table defaults to "resources" if not specified
    - Examples:
      - "person/supervisor" → resources table, category="person/supervisor"
      - "resource:person/supervisor" → resources table, category="person/supervisor"
      - "moments:reflection" → moments table, category="reflection"
      - "files:image/screenshot" → files table, category="image/screenshot"
    - Used to create orphan nodes when target entity doesn't exist yet

    **Example:**
    ```python
    edge = InlineEdge(
        dst="TiDB Migration Technical Specification",
        rel_type="builds-on",
        weight=0.85,
        properties={
            "dst_name": "TiDB Migration Technical Specification",
            "dst_entity_type": "document/technical-spec",
            "match_type": "semantic-historical",
            "confidence": 0.92,
            "context": "References migration approach from technical spec"
        },
        created_at=datetime.now(timezone.utc)
    )
    ```

    See: /docs/REM/design.md for complete edge documentation
    """

    dst: str = Field(
        ...,
        description=(
            "Natural entity label used in REM LOOKUP (NOT UUID or kebab-case). "
            "Use the same user-friendly name as the target entity (e.g., 'Sarah Chen', 'Q4 Planning Meeting'). "
            "LOOKUP finds all matching entities; LLM resolves ambiguity when multiple matches exist."
        )
    )

    rel_type: str = Field(
        ...,
        description=(
            "Relationship type describing the semantic connection. "
            "Examples: 'authored_by', 'builds-on', 'references', 'contradicts', "
            "'depends_on', 'implements', 'extends'. "
            "Use lowercase with underscores."
        )
    )

    weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Relationship strength (0.0-1.0). NOT confidence - represents "
            "how strong/important the relationship is. "
            "1.0=primary, 0.8-0.9=important, 0.5-0.7=secondary, 0.3-0.4=weak"
        )
    )

    properties: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Rich metadata about the relationship. "
            "Common fields: dst_name (display name), dst_entity_type (schema/category), "
            "confidence (0.0-1.0), context (textual description), match_type, "
            "semantic_similarity, graph_depth, llm_assessed, reasoning"
        )
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this edge was created (UTC timestamp)"
    )

    model_config = {"extra": "forbid"}  # Strict validation - use properties for additional data

    def parse_entity_type(self) -> tuple[str, str]:
        """
        Parse dst_entity_type into (table_name, category).

        Format: [table:]category[/subcategory]
        - "person/supervisor" → ("resources", "person/supervisor")
        - "resource:person/supervisor" → ("resources", "person/supervisor")
        - "moments:reflection" → ("moments", "reflection")
        - "files:image/screenshot" → ("files", "image/screenshot")

        Returns:
            tuple: (table_name, category)
        """
        entity_type = self.properties.get("dst_entity_type", "")

        if not entity_type:
            return ("resources", "")

        # Check if table is specified (contains colon)
        if ":" in entity_type:
            table, category = entity_type.split(":", 1)
            return (table.strip(), category.strip())
        else:
            # No table specified, default to resources
            return ("resources", entity_type.strip())

    def create_node_data(self, tenant_id: str, add_reverse_edge: bool = True, source_name: str = None) -> dict[str, Any]:
        """
        Create lightweight node data for this edge's target entity.

        Creates a minimal entity (resource/moment/etc) that can be "filled in" later
        when more information is available. The node is not orphaned - it has edges
        connecting to it, just minimal content until enriched.

        Args:
            tenant_id: Tenant ID for the node
            add_reverse_edge: If True, adds inverse edge back to source (e.g., inv-managed-by)
            source_name: Name of source entity (required if add_reverse_edge=True)

        Returns:
            dict: Entity data ready to upsert (compatible with Resources/Moment models)
        """
        table_name, category = self.parse_entity_type()

        # Generate stable ID based on tenant + name
        from uuid import NAMESPACE_DNS, uuid5
        entity_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{table_name}:{self.dst}"))

        # Reverse edge if requested
        graph_paths = []
        if add_reverse_edge and source_name:
            reverse_rel = f"inv-{self.rel_type}"
            reverse_edge = {
                "dst": source_name,
                "rel_type": reverse_rel,
                "weight": self.weight,
                "properties": {
                    "dst_name": source_name,
                    "confidence": 1.0,
                    "match_type": "inverse_edge",
                    "inverse_of": self.rel_type
                },
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            graph_paths.append(reverse_edge)

        # Base node data
        node_data = {
            "id": entity_id,
            "tenant_id": tenant_id,
            "name": self.dst,
            "category": category or "reference",
            "content": f"Lightweight node for '{self.dst}'. Will be enriched when full entity is created.",
            "metadata": {
                "is_lightweight": True,
                "created_from_edge": True,
                "edge_rel_type": self.rel_type,
                "dst_entity_type": self.properties.get("dst_entity_type", ""),
            },
            "graph_paths": graph_paths
        }

        # Add table-specific fields for moments
        if table_name == "moments":
            node_data["moment_type"] = category or "reference"
            node_data["emotion_tags"] = []
            node_data["topic_tags"] = []

        return node_data


class Resources(AbstractEntityModel):
    """Generic content resources with metadata."""

    name: str = Field(..., description="Resource name")
    category: str | None = Field(None, description="Resource category")
    content: str | None = DefaultEmbeddingField(
        None, description="Resource content for semantic search"
    )
    summary: str | None = Field(None, description="Content summary for semantic search")
    ordinal: int | None = Field(0, description="Ordering index")
    uri: str | None = Field(None, description="Resource URI")
    metadata: dict[str, Any] | None = Field(
        default_factory=dict, description="Resource metadata"
    )
    graph_paths: list[dict[str, Any]] | None = Field(
        default_factory=list,
        description=(
            "Knowledge graph edges connecting this resource to others. "
            "Stored as JSONB array of InlineEdge objects (serialized as dicts). "
            "Each edge uses human-readable dst keys and includes relationship metadata."
        )
    )
    resource_timestamp: datetime | None = Field(None, description="Resource timestamp")
    userid: str | None = Field(None, description="Associated user ID")

    model_config = {
        "key_field": "name",
        "table_name": "resources",
        "description": "Generic parsed content resources",
    }

    @model_validator(mode="before")
    @classmethod
    def sanitize_graph_paths(cls, values):
        """Clean up graph_paths to handle legacy string format.

        Old data may have graph_paths as strings instead of dicts.
        This validator filters out invalid entries while preserving valid ones.
        """
        graph_paths = values.get("graph_paths")
        if graph_paths is not None:
            # Filter to only keep dict entries, discard strings or other invalid types
            valid_paths = []
            invalid_count = 0
            for item in graph_paths:
                if isinstance(item, dict):
                    valid_paths.append(item)
                else:
                    invalid_count += 1

            if invalid_count > 0:
                from p8fs_cluster.logging import get_logger
                logger = get_logger(__name__)
                logger.debug(
                    f"Filtered out {invalid_count} invalid graph_path entries "
                    f"(kept {len(valid_paths)} valid entries)"
                )

            values["graph_paths"] = valid_paths
        return values

    @model_validator(mode="before")
    @classmethod
    def generate_resource_id(cls, values):
        """Generate ID from URI and ordinal if not already set."""
        if not values.get("id"):
            # Generate ID from tenant_id + uri + ordinal if available
            from uuid import NAMESPACE_DNS, uuid5

            tenant_id = values.get("tenant_id", "default")
            uri = values.get("uri", "")
            ordinal = values.get("ordinal", 0)
            values["id"] = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{uri}:{ordinal}"))
        return values

    @classmethod
    def get_embedding_column_values(
        cls, entities: list[dict]
    ) -> tuple[list[str], list[dict]]:
        """Extract actual text values to embed and metadata about them."""
        # Get embedding fields from the model schema instead of hardcoding
        embedding_columns = cls.get_embedding_fields()

        values_to_embed = []
        metadata = []  # track which entity/column each value belongs to

        for entity_idx, entity in enumerate(entities):
            for column in embedding_columns:
                if column in entity and entity[column]:
                    values_to_embed.append(entity[column])
                    metadata.append(
                        {
                            "entity_idx": entity_idx,
                            "column_name": column,
                        }
                    )

        return values_to_embed, metadata

    @classmethod
    def build_embedding_records(
        cls,
        entity_ids: list[str],
        column_metadata: list[dict],
        embedding_vectors: list[list[float]],
        tenant_id: str,
        embedding_provider: str = "openai",
    ) -> list[dict]:
        """Build embedding records from metadata and vectors."""
        from ..utils import make_uuid

        records = []

        for i, (metadata, vector) in enumerate(zip(column_metadata, embedding_vectors)):
            entity_idx = metadata["entity_idx"]
            entity_id = entity_ids[entity_idx]

            records.append(
                {
                    "id": make_uuid(
                        f"{entity_id}:{metadata['column_name']}:{embedding_provider}"
                    ),
                    "entity_id": entity_id,
                    "field_name": metadata["column_name"],
                    "embedding_provider": embedding_provider,
                    "embedding_vector": vector,
                    "tenant_id": tenant_id,
                    "vector_dimension": len(vector),
                }
            )

        return records


class Project(AbstractEntityModel):
    """Project or goal definition."""

    name: str = Field(..., description="Project name")
    description: str | None = DefaultEmbeddingField(
        None, description="Project description for semantic search"
    )
    target_date: datetime | None = Field(None, description="Target completion date")
    collaborator_ids: list[str] | None = Field(
        default_factory=list, description="Collaborator user IDs"
    )
    status: str | None = Field("active", description="Project status")
    priority: int | None = Field(3, description="Priority level (1-5)")

    model_config = {
        "key_field": "name",
        "table_name": "projects",
        "description": "Projects and goals with collaboration support",
    }


class Task(Project):
    """Task as a specialized project."""

    project_name: str | None = Field(None, description="Parent project name")
    estimated_effort: int | None = Field(None, description="Estimated hours")
    progress: float | None = Field(0.0, description="Completion percentage")

    model_config = {
        "key_field": "id",
        "table_name": "tasks",
        "description": "Tasks as sub-projects with effort tracking",
    }

    @model_validator(mode="before")
    @classmethod
    def generate_task_id(cls, values):
        """Generate ID from name and project_name."""
        # Implementation stub - should generate ID from name+project_name
        return values


class Files(AbstractEntityModel):
    """File metadata and tracking."""

    uri: str = Field(..., description="File URI")
    file_size: int | None = Field(None, description="File size in bytes")
    mime_type: str | None = Field(None, description="MIME type")
    content_hash: str | None = Field(None, description="Content hash for deduplication")
    upload_timestamp: datetime | None = Field(
        default_factory=datetime.utcnow, description="Upload time"
    )
    metadata: dict[str, Any] | None = Field(
        default_factory=dict, description="File metadata"
    )
    parsing_metadata: dict[str, Any] | None = Field(
        None,
        description="Custom parser metadata (e.g., PDF parser uncertainty about pages, actual page count parsed, parsing warnings)",
    )
    derived_attributes: dict[str, Any] | None = Field(
        None,
        description="Machine learning model-derived attributes (e.g., background noise detection in WAV files, arbitrary ML-inferred properties)",
    )
    model_pipeline_run_at: datetime | None = Field(
        None,
        description="Timestamp when advanced model pipeline processing was completed",
    )
    encryption_key_owner: EncryptionKeyOwner | None = Field(
        None, description="Who owns/manages the encryption key (USER|SYSTEM|NONE)"
    )

    model_config = {
        "key_field": "id",
        "table_name": "files",
        "description": "File metadata and tracking system",
        "indexed": ["content_hash", "mime_type", "uri"],
    }

    @classmethod
    def get_recent_uploads_by_user(
        cls,
        tenant_id: str,
        limit: int = 20,
        include_resource_names: bool = True,
    ) -> dict[str, Any]:
        """
        Get recently uploaded files for a tenant with associated resource names.

        This function retrieves files that were recently uploaded, optionally including
        associated resource names from processed content chunks. Entity keys can then
        be looked up for detailed chunk information.

        Args:
            tenant_id: The tenant ID to filter files by
            limit: Maximum number of recent files to return (default: 20)
            include_resource_names: Whether to include resource names collection (default: True)

        Returns:
            Dictionary containing recent upload information including:
            - files: List of file metadata with upload timestamps
            - resource_names: Collection of resource names if requested
            - instructions: How to lookup entity keys for chunk details
        """
        from p8fs.repository import TenantRepository

        try:
            from p8fs.providers import get_provider

            provider = get_provider()
            conn = provider.connect_sync()

            try:
                with conn.cursor() as cur:
                    # Get dialect-specific query from provider
                    files_query = provider.get_recent_uploads_query(limit)

                    cur.execute(files_query, (tenant_id, limit))
                    columns = [desc[0] for desc in cur.description]
                    uploads = [dict(zip(columns, row)) for row in cur.fetchall()]

                    # Parse files from query results
                    files_list = []
                    resource_names = []

                    for upload in uploads:
                        file_data = {
                            "file_id": upload.get("file_id"),
                            "file_name": upload.get("file_name"),
                            "uri": upload.get("uri", ""),
                            "file_size": upload.get("file_size", 0),
                            "mime_type": upload.get("mime_type", "unknown"),
                            "upload_timestamp": upload.get("upload_timestamp"),
                            "chunk_count": upload.get("chunk_count", 0),
                            "entity_key": f"{tenant_id}/entity/Files/{upload.get('file_id', '')}",
                        }
                        files_list.append(file_data)

                        # Collect resource names if requested
                        if include_resource_names:
                            chunk_entities = upload.get("chunk_entity_names", [])
                            if chunk_entities and chunk_entities != [None]:
                                for chunk in chunk_entities:
                                    if chunk and chunk.get("name"):
                                        resource_names.append({
                                            "name": chunk.get("name", ""),
                                            "entity_key": f"{tenant_id}/entity/Resources/{chunk.get('id', '')}",
                                            "category": chunk.get("category", ""),
                                            "ordinal": chunk.get("ordinal", 0),
                                        })
            finally:
                conn.close()

            return {
                "tenant_id": tenant_id,
                "limit": limit,
                "files": files_list,
                "files_count": len(files_list),
                "resource_names": resource_names if include_resource_names else None,
                "resource_names_count": (
                    len(resource_names) if include_resource_names else None
                ),
                "instructions": (
                    "Use entity keys from 'files' or 'resource_names' with get_entities() function "
                    "to lookup detailed chunk information and content."
                ),
            }

        except Exception as e:
            from p8fs_cluster.logging import get_logger

            logger = get_logger(__name__)
            logger.error(f"Error in get_recent_uploads_by_user: {e}")
            return {"error": str(e), "files": [], "resource_names": []}


class FileAttributes(AbstractEntityModel):
    """
    Flexible attribute storage for files from various ML models and processors.

    This table provides a flexible way for any model to add attributes to a file.
    The file_id references a Files entity using a deterministic hash format based on
    uri + tenant_id, allowing stable cross-references.

    Example use cases:
    - Audio analysis models storing noise levels, speech quality metrics
    - Image models storing detected objects, scene classifications
    - Video models storing frame analysis, motion detection results
    - Custom processors storing any arbitrary attributes
    """

    file_id: str = Field(
        ...,
        description="File entity ID (deterministic hash from uri + tenant_id)",
    )
    model: str = Field(
        ..., description="Model or processor name that generated these attributes"
    )
    attributes: dict[str, Any] = Field(
        ..., description="JSON attributes from the model/processor"
    )

    model_config = {
        "key_field": "id",
        "table_name": "file_attributes",
        "description": "Flexible attribute storage for files from ML models and processors",
        "indexed": ["file_id", "model"],
    }


class Error(AbstractEntityModel):
    """Error logging with TTL support."""

    date: datetime = Field(
        default_factory=datetime.utcnow, description="Error timestamp"
    )
    process: str | None = Field(None, description="Process/service name")
    message: str = Field(..., description="Error message")
    stack_trace: str | None = Field(None, description="Stack trace")
    level: str = Field("ERROR", description="Error severity level")
    metadata: dict[str, Any] | None = Field(
        default_factory=dict, description="Error metadata"
    )
    userid: str | None = Field(None, description="Associated user ID")

    model_config = {
        "key_field": "id",
        "table_name": "errors",
        "description": "Error logging and tracking with TTL",
        # TTL support would be implemented in provider
    }


class Job(AbstractEntityModel):
    """Asynchronous job tracking and management."""

    job_type: JobType = Field(..., description="Type of job")
    status: JobStatus = Field(JobStatus.PENDING, description="Current job status")
    priority: int = Field(3, description="Job priority (1-5)")
    tenant_id: str = Field(..., description="Tenant identifier")
    payload: dict[str, Any] | None = Field(
        default_factory=dict, description="Job parameters"
    )
    max_retries: int = Field(3, description="Maximum retry attempts")
    retry_count: int = Field(0, description="Current retry count")
    timeout: int | None = Field(300, description="Timeout in seconds")
    is_batch: bool = Field(False, description="Is this a batch job")
    batch_size: int | None = Field(None, description="Batch size for batch jobs")
    items_processed: int = Field(0, description="Items processed so far")
    result: dict[str, Any] | None = Field(None, description="Job result data")
    error: str | None = Field(None, description="Error message if failed")
    callback_url: str | None = Field(None, description="Callback URL for completion")
    callback_headers: dict[str, str] | None = Field(
        None, description="Callback headers"
    )
    queued_at: datetime = Field(
        default_factory=datetime.utcnow, description="Queue timestamp"
    )
    started_at: datetime | None = Field(None, description="Start timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")
    openai_batch_id: str | None = Field(
        None, description="OpenAI batch ID if applicable"
    )
    openai_batch_status: str | None = Field(None, description="OpenAI batch status")

    model_config = {
        "key_field": "id",
        "table_name": "jobs",
        "description": "Asynchronous job tracking and batch processing",
        "indexed": ["status", "job_type", "priority"],
    }

    def get_job_status(self) -> JobStatus:
        """Get current job status."""
        return self.status

    def is_complete(self) -> bool:
        """Check if job is completed (success or failure)."""
        return self.status in [
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        ]

    @classmethod
    def create_batch_job(
        cls,
        questions: list[str],
        context: "BatchCallingContext",
        tenant_id: str | None = None,
    ) -> "Job":
        """
        Factory method to create a batch job from questions and context.

        Args:
            questions: List of questions to process
            context: BatchCallingContext with all settings
            tenant_id: Optional tenant ID override

        Returns:
            Configured Job instance ready to be saved
        """

        # Use tenant_id from context, parameter, or config default
        from p8fs_cluster.config.settings import config
        
        final_tenant_id = (
            getattr(context, "tenant_id", None) 
            or tenant_id 
            or config.default_tenant_id
        )
        
        return cls(
            id=uuid4(),
            job_type=JobType.BATCH_COMPLETION,
            status=JobStatus.PENDING,
            tenant_id=final_tenant_id,  # Set at top level
            payload={
                "questions": questions,
                "batch_id": context.batch_id,
                "model": context.model,
                "settings": {
                    "temperature": getattr(context, "temperature", 0.7),
                    "max_tokens": getattr(context, "max_tokens", 1024),
                },
                "user_id": getattr(context, "user_id", None),
                "created_by": "MemoryProxy.batch",
            },
            is_batch=True,
            batch_size=len(questions),
            priority=getattr(context, "priority", 3),
        )


# Utility function for model discovery - available for import
def get_all_models() -> dict[str, Any]:
    """Discover all AbstractModel subclasses in this module."""
    import inspect
    import sys

    models = {}

    # Get current module
    current_module = sys.modules[__name__]

    # Iterate through module members
    for name, obj in inspect.getmembers(current_module):
        if (
            inspect.isclass(obj)
            and issubclass(obj, (AbstractModel, AbstractEntityModel))
            and obj not in (AbstractModel, AbstractEntityModel)
            and obj.__module__ == __name__
        ):
            models[name] = obj

    return models


class Tenant(AbstractEntityModel):
    """Tenant model for multi-tenant authentication and storage isolation."""

    tenant_id: str = Field(..., description="Unique tenant identifier")
    email: str = Field(..., description="Primary email associated with tenant")
    public_key: str = Field(
        ..., description="Public key for authentication (Ed25519 base64)"
    )
    device_ids: list[str] | None = Field(
        default_factory=list, description="Associated device IDs"
    )
    storage_bucket: str | None = Field(None, description="Isolated storage bucket name")
    metadata: dict[str, Any] | None = Field(
        default_factory=dict, description="Additional tenant metadata"
    )
    active: bool = Field(True, description="Whether tenant is active")
    security_policy: dict[str, Any] | None = Field(
        None, description="Tenant security policy configuration (JSONB)"
    )
    encryption_wait_time_days: int | None = Field(
        None, description="Days to wait before encrypting data (for user key setup)"
    )

    @field_validator("device_ids", mode="before")
    @classmethod
    def validate_device_ids(cls, v):
        return v if v is not None else []

    @field_validator("metadata", mode="before")
    @classmethod
    def validate_metadata(cls, v):
        return v if v is not None else {}

    model_config = {
        "key_field": "id",
        "table_name": "tenants",
        "description": "Tenant registry for authentication and isolation",
        "indexed": ["email", "tenant_id"],
    }


class KVStorage(AbstractEntityModel):
    """Key-Value storage for temporary data like device authorization flows.

    This model stores temporary data with TTL support, used for:
    - Device authorization pending requests
    - Session tokens
    - Cache data
    - Other temporary key-value storage needs
    """

    key: str = Field(..., description="Storage key (primary key)")
    value: dict[str, Any] = Field(..., description="JSON value stored")
    expires_at: datetime | None = Field(None, description="Expiration timestamp (TTL)")

    model_config = {
        "key_field": "key",
        "table_name": "kv_storage",
        "description": "Temporary key-value storage with TTL support",
        "indexed": ["expires_at"],  # For efficient TTL cleanup
    }


class PresentPerson(AbstractModel):
    """Person present during a moment, identified by fingerprint."""

    fingerprint_id: str = Field(
        ..., description="Unique fingerprint/voice ID for the person"
    )
    user_id: str | None = Field(None, description="User ID if person is identified")
    user_label: str | None = Field(
        None, description="Display name or label for the person"
    )

    model_config = {"extra": "allow"}  # Allow additional fields like confidence scores


class Engram(Resources):
    """
    Engram - A memory structure representation stored as a Resource.

    When an Engram document is uploaded with a summary in its metadata,
    it's stored as this Resource entity. The original Engram document
    structure is preserved in the Resource's content field.
    """

    # Processing tracking
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this engram was processed",
    )
    operation_count: dict[str, int] | None = Field(
        default_factory=dict,
        description="Count of operations performed: {upserts: N, patches: N, associations: N}",
    )

    model_config = {
        "table_name": "engrams",
        "description": "Memory structure representation with K8s-like format for batch entity operations",
    }


class Moment(Resources):
    """
    Moment - A time-bounded segment of experience extracted from temporal data.

    Moments are subclasses of Resources that add temporal boundaries and presence information.
    They're typically extracted from audio/video captures and represent discrete time segments
    with associated context like who was present, what was discussed, and environmental data.

    Note: All base Resource fields are required (tenant_id, content, uri).
    All Moment-specific fields are optional.

    Moments can describe sections of a user data e.d a period of time where they were with others,
    focusing on something, worrying about something, planning something, spending time somewhere etc.
    A moment is a classification of time
    """

    # Temporal boundaries
    resource_ends_timestamp: datetime | None = Field(
        None, description="End time of this moment (resource_timestamp is the start)"
    )

    # Presence information
    present_persons: list[dict[str, Any]] | None = Field(
        None,
        description="People present during this moment. List of PresentPerson objects with id, name, and comment fields",
    )

    # Context information
    location: str | None = Field(
        None, description="GPS coordinates or location description"
    )
    background_sounds: str | None = Field(
        None, description="Description of ambient sounds or environment"
    )

    # Moment-specific metadata
    moment_type: str | None = Field(
        None,
        description="Type of moment (e.g., 'conversation', 'meeting', 'observation', 'reflection')",
    )
    emotion_tags: list[str] | None = Field(
        None,
        description="Emotional context tags (e.g., ['happy', 'focused', 'stressed'])",
    )
    topic_tags: list[str] | None = Field(
        None, description="Topic tags extracted from content"
    )
    images: list[str] | None = Field(
        None,
        description="URIs to representative images associated with this moment (e.g., screenshots, photos, visualizations)",
    )
    speakers: list[dict[str, Any]] | None = Field(
        None,
        description="List of speaker entries with format: {text: str, speaker_identifier: str, timestamp: datetime, emotion: str}",
    )
    key_emotions: list[str] | None = Field(
        None,
        description="Key emotional context tags for the entire moment (e.g., 'collaborative', 'tense', 'enthusiastic')",
    )

    def duration_seconds(self) -> float | None:
        """Calculate duration of the moment in seconds."""
        if self.resource_timestamp and self.resource_ends_timestamp:
            delta = self.resource_ends_timestamp - self.resource_timestamp
            return delta.total_seconds()
        return None

    def get_present_person_ids(self) -> list[str]:
        """Extract list of person IDs present in this moment."""
        if not self.present_persons:
            return []
        return [
            person.get("user_id") or person.get("fingerprint_id") or person.get("id")
            for person in self.present_persons
            if isinstance(person, dict)
        ]

    model_config = {
        "table_name": "moments",
        "description": "Time-bounded memory segments with presence and context information",
    }


class Image(AbstractEntityModel):
    """
    Image - Visual content with CLIP embeddings for semantic search.

    Stores images with multimodal CLIP embeddings allowing semantic search
    across both text and visual content. Supports sample images from sources
    like Unsplash as well as user-uploaded images.
    """

    uri: str = Field(..., description="Image URI (S3, HTTP, or local path)")
    caption: str | None = Field(
        None, description="Image caption or description (CLIP embeddings generated separately)"
    )
    source: str | None = Field(None, description="Image source (e.g., 'unsplash', 'user_upload')")
    source_id: str | None = Field(None, description="External source identifier")
    width: int | None = Field(None, description="Image width in pixels")
    height: int | None = Field(None, description="Image height in pixels")
    mime_type: str | None = Field(None, description="Image MIME type")
    file_size: int | None = Field(None, description="File size in bytes")
    tags: list[str] | None = Field(
        default_factory=list, description="Semantic tags for the image"
    )
    metadata: dict[str, Any] | None = Field(
        default_factory=dict, description="Additional image metadata"
    )

    model_config = {
        "key_field": "id",
        "table_name": "images",
        "description": "Visual content with CLIP embeddings for semantic search",
        "indexed": ["source", "source_id", "uri"],
    }

    @classmethod
    def get_embedding_column_values(
        cls, entities: list[dict]
    ) -> tuple[list[str], list[dict]]:
        """Extract caption values to embed and metadata about them."""
        embedding_columns = cls.get_embedding_fields()

        values_to_embed = []
        metadata = []

        for entity_idx, entity in enumerate(entities):
            for column in embedding_columns:
                if column in entity and entity[column]:
                    values_to_embed.append(entity[column])
                    metadata.append(
                        {
                            "entity_idx": entity_idx,
                            "column_name": column,
                        }
                    )

        return values_to_embed, metadata

    @classmethod
    def build_embedding_records(
        cls,
        entity_ids: list[str],
        column_metadata: list[dict],
        embedding_vectors: list[list[float]],
        tenant_id: str,
        embedding_provider: str = "clip",
    ) -> list[dict]:
        """Build CLIP embedding records from metadata and vectors."""
        from ..utils import make_uuid

        records = []

        for i, (metadata, vector) in enumerate(zip(column_metadata, embedding_vectors)):
            entity_idx = metadata["entity_idx"]
            entity_id = entity_ids[entity_idx]

            records.append(
                {
                    "id": make_uuid(
                        f"{entity_id}:{metadata['column_name']}:{embedding_provider}"
                    ),
                    "entity_id": entity_id,
                    "field_name": metadata["column_name"],
                    "embedding_provider": embedding_provider,
                    "embedding_vector": vector,
                    "tenant_id": tenant_id,
                    "vector_dimension": len(vector),
                }
            )

        return records


if __name__ == "__main__":
    """
    Model registration entry point for P8FS core models.

    Usage:
        # Generate SQL scripts for all models
        python -m p8fs.models.p8 --provider postgres --plan
        python -m p8fs.models.p8 --provider tidb --plan --output-dir extensions/migrations

        # Execute model registration (requires database connection)
        python -m p8fs.models.p8 --provider postgres --execute

        # Register specific models
        python -m p8fs.models.p8 --provider postgres --models User,Session --plan
    """
    import argparse
    import sys
    from pathlib import Path

    # Add parent directory to path for imports
    current_dir = Path(__file__).parent
    sys.path.insert(0, str(current_dir.parent.parent.parent))

    from p8fs.models.base import AbstractEntityModel, AbstractModel
    from p8fs.providers import (
        PostgreSQLProvider,
        RocksDBProvider,
        TiDBProvider,
    )

    def main():
        parser = argparse.ArgumentParser(description="P8FS Model Registration Tool")
        parser.add_argument(
            "--provider",
            required=True,
            choices=["postgres", "postgresql", "tidb", "rocksdb"],
        )
        parser.add_argument(
            "--plan",
            action="store_true",
            help="Generate SQL without executing (default)",
        )

        args = parser.parse_args()
        plan = args.plan or not hasattr(args, "execute")

        from p8fs.providers.base import BaseSQLProvider

        provider = BaseSQLProvider.get_provider(args.provider)

        all_sql = []

        # For TiDB, prepend database creation to match PostgreSQL's public schema
        if args.provider == "tidb":
            tidb_header = """-- P8FS Full TiDB Migration Script
-- Generated from Python models with TiDB-specific types
--
-- This migration creates tables in a 'public' database to match PostgreSQL's
-- public schema structure. This makes it easier to compare and switch between
-- PostgreSQL and TiDB deployments.
--
-- Structure:
--   - Main tables: public.agents, public.users, etc.
--   - Embedding tables: embeddings.agents_embeddings, etc.
--
-- Connection string: mysql://root@localhost:4000/public

-- Create public database to match PostgreSQL structure
CREATE DATABASE IF NOT EXISTS public;
CREATE DATABASE IF NOT EXISTS embeddings;
USE public;"""
            all_sql.append(tidb_header)

            # Add kv_entity_mapping table once at the start for TiDB
            kv_mapping_sql = provider.create_kv_mapping_table_sql()
            all_sql.append(kv_mapping_sql)

        for model_class in get_all_models().values():
            sql = provider.register_model(model_class, plan=plan)
            all_sql.append(sql)

        combined_sql = "\n\n".join(all_sql)

        if plan:
            print(combined_sql)
        else:
            print("Done" if combined_sql else "Failed")

    sys.exit(main())
