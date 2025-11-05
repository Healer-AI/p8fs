"""Base AbstractModel classes for P8FS."""

import inspect
import types
from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_serializer
from pydantic.fields import FieldInfo
from pydantic._internal._model_construction import ModelMetaclass

from ..utils.typing import TypeInspector, get_class_and_instance_methods, object_namespace

T = TypeVar('T', bound='AbstractModel')


GENERIC_SQL_GEN_PREAMBLE = """You are a SQL query generator. Given a model description and schema, generate a SQL query that best matches the user's natural language request.

IMPORTANT INSTRUCTIONS:
1. Generate ONLY valid SQL for the specified dialect
2. Use the exact table name and column names from the schema
3. Return a JSON response with the following structure:
{
    "query": "SELECT ...",
    "confidence": 85,
    "brief_explanation": "Optional explanation if confidence < threshold"
}

4. Confidence should be 0-100 based on how well the request matches available schema
5. Only include "brief_explanation" if confidence is below the threshold
6. Use appropriate SQL features for the dialect:
   - PostgreSQL: Use ->> for JSON fields, ::type for casting, LIMIT for row limits
   - MySQL: Use JSON_EXTRACT for JSON fields, CAST() for type conversion, LIMIT for row limits
   - SQLite: Use json_extract for JSON fields, CAST() for type conversion, LIMIT for row limits
"""


def ensure_model_not_instance(cls_or_instance: Any):
    """Ensure we have a class, not an instance"""
    if not isinstance(cls_or_instance, ModelMetaclass) and isinstance(
        cls_or_instance, BaseModel
    ):
        # If it's an instance, return the class
        return cls_or_instance.__class__
    return cls_or_instance


class AbstractModelMixin:
    """Adds declarative metadata scraping from objects"""
    
    @classmethod
    def get_model_name(cls) -> str:
        """Get the unqualified model name"""
        c: ConfigDict = getattr(cls, 'model_config', {})
        return c.get("name") if isinstance(c, dict) else getattr(cls, '__name__', 'Unknown')
    
    @classmethod 
    def get_model_namespace(cls) -> str:
        """Get the namespace provided by config or convention"""
        c: ConfigDict = getattr(cls, 'model_config', {})
        if isinstance(c, dict) and c.get("namespace"):
            return c.get("namespace")
        return object_namespace(cls)


class AbstractModel(BaseModel):
    """Base class for all P8FS models with self-describing capabilities."""
    
    model_config = ConfigDict(
        extra="ignore",
        validate_assignment=True,
        use_enum_values=True,
    )
    
    @field_serializer('*', mode='wrap')
    def serialize_fields(self, value, serializer, info):
        """Serialize datetime fields to ISO format and handle enums properly."""
        if isinstance(value, datetime):
            return value.isoformat()
        
        # Check if this field is supposed to be an enum but has already been converted to string
        # This happens with use_enum_values=True
        from enum import Enum
        if info.field_name and hasattr(self.__class__, 'model_fields'):
            field_info = self.__class__.model_fields.get(info.field_name)
            if field_info and hasattr(field_info.annotation, '__origin__'):
                # Handle Optional[EnumType] and similar
                import typing
                origin = typing.get_origin(field_info.annotation)
                args = typing.get_args(field_info.annotation)
                if origin is typing.Union and args:
                    # Check if any of the union types is an Enum
                    for arg in args:
                        if isinstance(arg, type) and issubclass(arg, Enum):
                            # This is an enum field that's already been converted to string
                            return value
            elif field_info and isinstance(field_info.annotation, type) and issubclass(field_info.annotation, Enum):
                # Direct enum type that's already been converted to string
                return value
        
        return serializer(value)

    @classmethod
    def get_model_name(cls) -> str:
        """Get the model name for database table naming and identification.
        
        Returns the class name as the model identifier.
        Used for generating table names and namespacing.
        """
        return cls.__name__

    @classmethod  
    def get_model_namespace(cls) -> str:
        """Get the model namespace from module path.
        
        Extracts namespace from the last two parts of the module path
        for logical grouping of related models.
        
        Returns:
            str: Namespace in format 'parent.module' or 'default'
        """
        module_parts = cls.__module__.split('.')
        if len(module_parts) >= 2:
            return '.'.join(module_parts[-2:])
        return 'default'

    @classmethod
    def get_model_full_name(cls) -> str:
        """Get fully qualified namespace.name"""
        return f"{cls.get_model_namespace()}.{cls.get_model_name()}"

    @classmethod
    def get_model_key_field(cls) -> str:
        """Get the primary key field name.
        
        Checks Config.key_field first, defaults to 'name'.
        Used for database operations requiring primary key identification.
        
        Returns:
            str: Primary key field name
        """
        # Check model_config first
        if hasattr(cls, 'model_config') and isinstance(cls.model_config, dict):
            if 'key_field' in cls.model_config:
                return cls.model_config['key_field']
        # Then check Config for backwards compatibility
        config = getattr(cls, 'Config', None)
        if config and hasattr(config, 'key_field'):
            return config.key_field
        return 'name'

    @classmethod
    def get_model_table_name(cls) -> str:
        """Get the database table name.
        
        Checks Config.table_name first, defaults to lowercase class name with 's' suffix.
        
        Returns:
            str: Database table name for this model
        """
        # Check model_config first
        if hasattr(cls, 'model_config') and isinstance(cls.model_config, dict):
            if 'table_name' in cls.model_config:
                return cls.model_config['table_name']
        # Then check Config for backwards compatibility
        config = getattr(cls, 'Config', None)
        if config and hasattr(config, 'table_name'):
            return config.table_name
        return cls.__name__.lower() + 's'

    @classmethod
    def get_model_description(
        cls,
        use_full_description: bool = True,
        schema_format: str = "yaml"
    ) -> str:
        """Get the model description for use as LLM system prompt.

        Extracts description from multiple sources with priority:
        1. Class docstring (highest priority for system prompts)
        2. Config.description attribute
        3. model_config description field

        Args:
            use_full_description: If True, includes schema and function information
            schema_format: Format for structured schema output. Options:
                - "yaml": YAML-formatted JSON schema (default)
                - "json": JSON-formatted schema
                - "markdown": Markdown table (TODO)
                - None: Simple field list (legacy behavior)

        Returns:
            str: Model description suitable for LLM system prompt
        """
        description = ""

        # Priority 1: Class docstring (this is the primary system prompt)
        if cls.__doc__:
            description = cls.__doc__.strip()

        # Priority 2: model_config description (fallback if no docstring)
        if not description and hasattr(cls, 'model_config') and isinstance(cls.model_config, dict):
            if 'description' in cls.model_config:
                description = cls.model_config['description']

        # Priority 3: Config.description (backwards compatibility)
        if not description:
            config = getattr(cls, 'Config', None)
            if config and hasattr(config, 'description'):
                description = config.description

        # Priority 4: model_config json_schema_extra description (lowest priority)
        if not description:
            if hasattr(cls, 'model_config') and hasattr(cls.model_config, 'json_schema_extra'):
                schema_extra = cls.model_config.json_schema_extra or {}
                if isinstance(schema_extra, dict) and 'description' in schema_extra:
                    description = schema_extra['description']

        # If use_full_description, add schema information
        if use_full_description and description:
            if schema_format:
                # Include structured schema in requested format
                import json
                schema = cls.model_json_schema()

                if schema_format.lower() == "yaml":
                    import yaml
                    schema_text = yaml.dump(schema, default_flow_style=False, sort_keys=False)
                    description += f"\n\nPlease provide your response in the following structured format:\n\n```yaml\n{schema_text}```\n\nReturn your response as valid JSON matching this schema structure."

                elif schema_format.lower() == "json":
                    schema_text = json.dumps(schema, indent=2)
                    description += f"\n\nPlease provide your response in the following structured format:\n\n```json\n{schema_text}\n```\n\nReturn your response as valid JSON matching this schema structure."

                elif schema_format.lower() == "markdown":
                    # TODO: Implement markdown table format
                    description += f"\n\n[Markdown table format not yet implemented - falling back to YAML]"
                    import yaml
                    schema_text = yaml.dump(schema, default_flow_style=False, sort_keys=False)
                    description += f"\n\n```yaml\n{schema_text}```"
            else:
                # Legacy behavior: simple field list
                description += f"\n\nModel: {cls.__name__}"

                # Add field information
                fields_info = []
                for field_name, field_info in cls.model_fields.items():
                    field_type = str(field_info.annotation) if field_info.annotation else "Any"
                    field_desc = field_info.description if hasattr(field_info, 'description') else ""
                    if field_desc:
                        fields_info.append(f"- {field_name} ({field_type}): {field_desc}")
                    else:
                        fields_info.append(f"- {field_name} ({field_type})")

                if fields_info:
                    description += "\n\nAvailable fields:\n" + "\n".join(fields_info)

        return description

    @classmethod
    def get_embedding_fields(cls) -> list[str]:
        """Get fields that should have embeddings generated.
        
        Checks Config.embedding_fields first, then auto-detects from field metadata.
        Fields with 'embedding_provider' or 'embedding' metadata are included.
        
        Returns:
            List[str]: Field names that require embedding generation
        """
        config = getattr(cls, 'Config', None)
        if config and hasattr(config, 'embedding_fields'):
            return config.embedding_fields
        
        # Auto-detect embedding fields from field metadata (embedding_provider)
        embedding_fields = []
        for field_name, field_info in cls.model_fields.items():
            if isinstance(field_info, FieldInfo) and field_info.json_schema_extra:
                # Check for embedding_provider in field metadata (percolate pattern)
                if field_info.json_schema_extra.get('embedding_provider') or field_info.json_schema_extra.get('embedding'):
                    embedding_fields.append(field_name)
        
        return embedding_fields

    @classmethod
    def get_embedding_providers(cls) -> dict[str, str]:
        """Get embedding provider for each embedding field.
        
        Maps field names to their embedding provider identifiers.
        Resolves 'default' to 'text-embedding-ada-002'.
        
        Returns:
            Dict[str, str]: Mapping of field_name -> provider_name
        """
        providers = {}
        
        for field_name, field_info in cls.model_fields.items():
            if isinstance(field_info, FieldInfo) and field_info.json_schema_extra:
                embedding_provider = field_info.json_schema_extra.get('embedding_provider')
                if embedding_provider:
                    # Resolve 'default' to actual provider name
                    if embedding_provider == 'default':
                        embedding_provider = 'text-embedding-ada-002'
                    providers[field_name] = embedding_provider
        
        return providers

    @classmethod
    def is_tenant_isolated(cls) -> bool:
        """Check if this model requires tenant isolation.
        
        Determines whether database operations should include tenant scoping.
        Defaults to True for security.
        
        Returns:
            bool: True if tenant isolation is required
        """
        config = getattr(cls, 'Config', None)
        if config and hasattr(config, 'tenant_isolated'):
            return config.tenant_isolated
        return True  # Default to tenant isolation

    @classmethod
    def get_field_metadata(cls, field_name: str) -> dict[str, Any]:
        """Get metadata for a specific field.
        
        Extracts field metadata including embedding settings, max_length, etc.
        
        Args:
            field_name: Name of the field to get metadata for
            
        Returns:
            Dict[str, Any]: Field metadata dictionary
        """
        field_info = cls.model_fields.get(field_name)
        if not field_info:
            return {}
        
        metadata = {}
        if field_info.json_schema_extra:
            metadata.update(field_info.json_schema_extra)
        
        if hasattr(field_info, 'max_length') and field_info.max_length:
            metadata['max_length'] = field_info.max_length
            
        return metadata

    @classmethod
    def to_sql_schema(cls) -> dict[str, Any]:
        """Generate SQL schema information for this model.
        
        Creates comprehensive schema metadata for database operations
        including table structure, field types, and embedding configuration.
        
        Returns:
            Dict[str, Any]: Complete schema definition with table_name, fields, etc.
        """
        schema = {
            'table_name': cls.get_model_table_name(),
            'key_field': cls.get_model_key_field(),
            'embedding_fields': cls.get_embedding_fields(),
            'embedding_providers': cls.get_embedding_providers(),
            'tenant_isolated': cls.is_tenant_isolated(),
            'fields': {}
        }
        
        type_inspector = TypeInspector()
        
        for field_name, field_info in cls.model_fields.items():
            field_schema = {
                'type': field_info.annotation,
                'nullable': not field_info.is_required(),
                'metadata': cls.get_field_metadata(field_name),
                'is_primary_key': field_name == 'id',
                'is_key': field_name == cls.get_model_key_field() and field_name != 'id',
                'is_embedding': field_name in schema['embedding_fields'],
                'embedding_provider': schema['embedding_providers'].get(field_name)
            }
            
            # Analyze complex types
            if field_info.annotation:
                field_schema['sql_type'] = type_inspector.python_to_sql_type(field_info.annotation)
                field_schema['is_vector'] = type_inspector.is_vector_type(field_info.annotation)
                field_schema['is_json'] = type_inspector.is_json_type(field_info.annotation)
            
            schema['fields'][field_name] = field_schema
        
        return schema

    @classmethod
    def create_model_from_function(cls, fn, **field_overrides) -> type['AbstractModel']:
        """Create a model dynamically from a function signature."""
        from ..utils.functions import FunctionInspector
        
        inspector = FunctionInspector()
        function_info = inspector.analyze_function(fn)
        
        # Build fields from function parameters
        fields = {}
        for param_name, param_info in function_info['parameters'].items():
            field_type = param_info.get('type', str)
            default_value = param_info.get('default', ...)
            
            if param_name in field_overrides:
                fields[param_name] = field_overrides[param_name]
            else:
                fields[param_name] = (field_type, Field(default=default_value))
        
        # Create dynamic model class
        model_name = f"{fn.__name__.title()}Model"
        return type(model_name, (cls,), fields)

    def generate_id(self, tenant_id: str | None = None) -> str:
        """Generate a unique ID for this model instance.
        
        Creates a namespaced ID including tenant isolation if enabled.
        Format: 'tenant_id:ModelName:key_value' or 'ModelName:key_value'
        
        Args:
            tenant_id: Optional tenant identifier for isolation
            
        Returns:
            str: Generated unique identifier
        """
        key_field = self.get_model_key_field()
        key_value = getattr(self, key_field, None)
        
        if not key_value:
            key_value = str(uuid4())
        
        if tenant_id and self.is_tenant_isolated():
            return f"{tenant_id}:{self.get_model_name()}:{key_value}"
        
        return f"{self.get_model_name()}:{key_value}"

    def get_embedding_content(self) -> dict[str, str]:
        """Get content that should be embedded.
        
        Extracts string content from embedding fields for vector generation.
        Only includes non-empty string fields.
        
        Returns:
            Dict[str, str]: Mapping of field_name -> content_string
        """
        embedding_fields = self.get_embedding_fields()
        content = {}
        
        for field_name in embedding_fields:
            value = getattr(self, field_name, None)
            if value and isinstance(value, str):
                content[field_name] = value
        
        return content

    def to_dict(self, include_computed: bool = False) -> dict[str, Any]:
        """Convert model to dictionary with optional computed fields.
        
        Standard Pydantic serialization with optional metadata inclusion.
        
        Args:
            include_computed: Whether to include computed metadata fields
            
        Returns:
            Dict[str, Any]: Dictionary representation of the model
        """
        data = self.model_dump()
        
        if include_computed:
            data['_model_name'] = self.get_model_name()
            data['_namespace'] = self.get_model_namespace()
            data['_table_name'] = self.get_model_table_name()
        
        return data
    
    @classmethod
    async def natural_language_to_sql(
        cls,
        query: str,
        context: Any = None,
        dialect: str = "postgresql",
        confidence_threshold: int = 80
    ) -> dict[str, Any]:
        """Generate SQL query from natural language using LLM.
        
        Converts natural language queries to SQL using the model's schema
        and description as context for the language model.
        
        Args:
            query: Natural language query to convert to SQL
            context: CallingContext or similar object with model selection
            dialect: SQL dialect to target (postgresql, mysql, sqlite)
            confidence_threshold: Threshold below which to include explanation (0-100)
            
        Returns:
            Dict containing:
                - query: Generated SQL query string
                - confidence: Confidence score (0-100)
                - brief_explanation: Explanation if confidence < threshold
        """
        import json
        from ..services.llm.language_model import LanguageModel
        from ..services.llm.models import CallingContext
        
        # Use provided context or create default
        if context is None:
            context = CallingContext(
                tenant_id="default",
                model="gpt-4o",  # Default model
                user_id="system"
            )
        
        # Get model schema information
        model_description = cls.get_model_description(use_full_description=True)
        schema_info = cls.to_sql_schema()
        pydantic_schema = cls.model_json_schema()
        
        # Build comprehensive prompt
        system_prompt = GENERIC_SQL_GEN_PREAMBLE + f"\n\nSQL Dialect: {dialect.upper()}"
        
        user_prompt = f"""TARGET SQL DIALECT: {dialect.upper()}
    Please generate SQL specifically for {dialect.upper()} database.

    Model Information:
    {model_description}

    Table Name: {schema_info['table_name']}
    Primary Key: {schema_info['key_field']}
    Tenant Isolated: {schema_info['tenant_isolated']}

    Schema Fields:
    """
        
        # Add field details
        for field_name, field_info in schema_info['fields'].items():
            field_type = field_info.get('sql_type', 'TEXT')
            nullable = "NULL" if field_info.get('nullable', True) else "NOT NULL"
            is_pk = " PRIMARY KEY" if field_info.get('is_primary_key') else ""
            user_prompt += f"- {field_name}: {field_type} {nullable}{is_pk}\n"
        
        # Add Pydantic schema for additional context
        user_prompt += f"\n\nPydantic Schema:\n{json.dumps(pydantic_schema, indent=2)}"
        
        user_prompt += f"\n\nUser Query: {query}"
        
        # Initialize language model
        llm = LanguageModel(
            model_name=getattr(context, 'model', 'gpt-4o'),
            tenant_id=getattr(context, 'tenant_id', 'default')
        )
        
        # Prepare messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Set response format to ensure JSON
        response = await llm.invoke_raw(
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,  # Lower temperature for more consistent SQL
            max_tokens=1000
        )
        
        # Parse response
        try:
            if 'choices' in response and response['choices']:
                content = response['choices'][0]['message']['content']
                result = json.loads(content)
                
                # Ensure required fields
                if 'query' not in result:
                    raise ValueError("Missing 'query' field in response")
                if 'confidence' not in result:
                    result['confidence'] = 70  # Default confidence
                
                # Add explanation only if confidence is below threshold
                if result['confidence'] >= confidence_threshold and 'brief_explanation' in result:
                    del result['brief_explanation']
                elif result['confidence'] < confidence_threshold and 'brief_explanation' not in result:
                    result['brief_explanation'] = f"Low confidence ({result['confidence']}): Query may not fully match available schema"
                
                return result
            else:
                raise ValueError("Invalid response structure from LLM")
                
        except json.JSONDecodeError as e:
            return {
                "query": "",
                "confidence": 0,
                "brief_explanation": f"Failed to parse LLM response as JSON: {str(e)}"
            }
        except Exception as e:
            return {
                "query": "",
                "confidence": 0,
                "brief_explanation": f"Error generating SQL: {str(e)}"
            }

    @staticmethod
    def Abstracted(model: BaseModel) -> BaseModel:
        """
        Mixin for any base model instance. If an instance is passed we modify to the type e.g. Instance of Base Model -> type(BaseModel)
        The class can implement the interface i.e. we do not add methods if they are on the pydantic object.
        Otherwise we add methods that inspect or infer declarative properties of the model
        """
        if isinstance(model, AbstractModel):
            return model

        model = ensure_model_not_instance(model)

        for method in get_class_and_instance_methods(AbstractModelMixin):
            # Only add if we are not replacing
            if not hasattr(model, method.__name__):
                if isinstance(method, classmethod):
                    # Rebind the classmethod by wrapping it for SampleModel
                    bound_method = classmethod(method.__func__.__get__(model, model))
                    setattr(model, method.__name__, bound_method)

                else:
                    # For instance methods, bind them to the SampleModel directly
                    bound_method = types.MethodType(method.__func__, model)
                    setattr(model, method.__name__, bound_method)

        return model


class AbstractEntityModel(AbstractModel):
    """AbstractModel with required ID field for entities."""
    
    id: UUID | str = Field(..., description="Unique identifier")  # Required, no default
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime | None = Field(default=None, description="Last update timestamp")
    


class Function(AbstractEntityModel):
    """Functions are external tools that agents can use. See field comments for context.
    Functions can be searched and used as LLM tools.
    The function spec is derived from OpenAPI but adapted to the conventional used in LLMs
    """

    id: UUID | str = Field(
        description="A unique id in this case generated by the proxy and function name"
    )
    key: str | None = Field(None, description="optional key e.g operation id")
    name: str = Field(
        description="A friendly name that is unique within the proxy scope e.g. a single api or python library"
    )
    verb: str | None = Field(None, description="The verb e.g. get, post etc")
    endpoint: str | None = Field(
        None, description="A callable endpoint in the case of REST"
    )
    description: str = Field(
        "",
        description="A detailed description of the function - may be more comprehensive than the one within the function spec - this is semantically searchable",
    )
    function_spec: dict = Field(
        description="A function description that is OpenAI and based on the OpenAPI spec"
    )
    proxy_uri: str = Field(
        description="a reference to an api or library namespace that qualifies the named function"
    )

    @model_validator(mode="before")
    @classmethod
    def _f(cls, values):
        if not values.get("id"):
            from ..utils.misc import make_uuid
            values["id"] = make_uuid(
                {"key": values["name"], "proxy_uri": values["proxy_uri"]}
            )
        return values