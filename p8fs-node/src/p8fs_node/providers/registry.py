"""Content provider registry for mapping content types to providers."""

import logging
from pathlib import Path

from p8fs_node.models.content import ContentType
from p8fs_node.providers.base import ContentProvider

logger = logging.getLogger(__name__)


class ContentProviderRegistry:
    """Registry for content providers with lazy loading and type mapping."""

    def __init__(self):
        self._providers: dict[ContentType, type[ContentProvider]] = {}
        self._provider_map: dict[ContentType, tuple[str, str]] = {}  # Lazy loading map
        self._default_provider: type[ContentProvider] | None = None
        self._instances: dict[str, ContentProvider] = {}

    def register(
        self, provider_class: type[ContentProvider], is_default: bool = False
    ) -> None:
        """
        Register a content provider for specific content types.

        Args:
            provider_class: The provider class to register
            is_default: Whether this should be the default provider
        """
        # Create instance to get supported types
        instance = provider_class()

        # Register for each supported type
        for content_type in instance.supported_types:
            if content_type in self._providers:
                logger.warning(
                    f"Overriding existing provider for {content_type}: "
                    f"{self._providers[content_type].__name__} -> {provider_class.__name__}"
                )

            self._providers[content_type] = provider_class
            logger.debug(
                f"Registered {provider_class.__name__} for content type: {content_type}"
            )

        # Set as default if requested
        if is_default:
            self._default_provider = provider_class
            logger.debug(f"Set {provider_class.__name__} as default provider")

    def get_provider(self, content_path: str) -> ContentProvider | None:
        """
        Get the appropriate provider for a content file.

        Args:
            content_path: Path to the content file

        Returns:
            Content provider instance or None if no suitable provider found
        """
        # First, check if any registered provider specifically supports this file
        for provider_class in self._providers.values():
            # Create instance if not cached
            provider_name = provider_class.__name__
            if provider_name not in self._instances:
                self._instances[provider_name] = provider_class()
            
            provider_instance = self._instances[provider_name]
            
            # Check if provider has a supports_file method and can handle this file
            if hasattr(provider_instance, 'supports_file') and provider_instance.supports_file(content_path):
                logger.debug(f"Using specific provider for {content_path}: {provider_class.__name__}")
                return provider_instance

        # Detect content type from file extension
        content_type = self._detect_content_type(content_path)

        # Get provider class for this content type with lazy loading
        provider_class = self._providers.get(content_type)
        
        # Try lazy loading if not found
        if not provider_class and content_type in self._provider_map:
            provider_class = self._load_provider_class(content_type)
            if provider_class:
                self._providers[content_type] = provider_class

        # Fall back to default provider if no specific provider found
        if not provider_class and self._default_provider:
            provider_class = self._default_provider
            logger.debug(
                f"Using default provider for {content_type}: {provider_class.__name__}"
            )

        if not provider_class:
            logger.error(f"No provider found for content type: {content_type}")
            return None

        # Return cached instance or create new one
        provider_name = provider_class.__name__
        if provider_name not in self._instances:
            self._instances[provider_name] = provider_class()

        return self._instances[provider_name]

    def get_provider_by_type(self, content_type: ContentType) -> ContentProvider | None:
        """
        Get provider by content type with lazy loading.

        Args:
            content_type: The content type

        Returns:
            Content provider instance or None
        """
        provider_class = self._providers.get(content_type)
        
        # Try lazy loading if not found
        if not provider_class and content_type in self._provider_map:
            provider_class = self._load_provider_class(content_type)
            if provider_class:
                self._providers[content_type] = provider_class

        if not provider_class and self._default_provider:
            provider_class = self._default_provider

        if not provider_class:
            return None

        provider_name = provider_class.__name__
        if provider_name not in self._instances:
            self._instances[provider_name] = provider_class()

        return self._instances[provider_name]
    
    def _load_provider_class(self, content_type: ContentType) -> type[ContentProvider] | None:
        """Lazy load a provider class."""
        if content_type not in self._provider_map:
            return None
            
        module_name, class_name = self._provider_map[content_type]
        
        try:
            from importlib import import_module
            module = import_module(module_name, package='p8fs_node.providers')
            provider_class = getattr(module, class_name)
            logger.debug(f"Lazy loaded provider: {class_name}")
            return provider_class
        except Exception as e:
            logger.error(f"Failed to lazy load {class_name}: {e}")
            return None
    
    def register_provider_map(self, provider_map: dict):
        """Register provider map for lazy loading."""
        self._provider_map.update(provider_map)
        logger.debug(f"Registered {len(provider_map)} providers for lazy loading")

    def list_providers(self) -> dict[ContentType, str]:
        """
        List all registered providers.

        Returns:
            Dictionary mapping content types to provider names
        """
        return {
            content_type: provider_class.__name__
            for content_type, provider_class in self._providers.items()
        }

    def list_supported_types(self) -> list[ContentType]:
        """
        List all supported content types.

        Returns:
            List of supported content types
        """
        return list(self._providers.keys())

    def _detect_content_type(self, content_path: str) -> ContentType:
        """Detect content type from file extension."""
        path = Path(content_path)
        extension = path.suffix.lower()

        type_mapping = {
            ".pdf": ContentType.PDF,
            ".wav": ContentType.AUDIO,
            ".mp3": ContentType.AUDIO,
            ".m4a": ContentType.AUDIO,
            ".flac": ContentType.AUDIO,
            ".mp4": ContentType.VIDEO,
            ".avi": ContentType.VIDEO,
            ".mov": ContentType.VIDEO,
            ".mkv": ContentType.VIDEO,
            ".jpg": ContentType.IMAGE,
            ".jpeg": ContentType.IMAGE,
            ".png": ContentType.IMAGE,
            ".gif": ContentType.IMAGE,
            ".bmp": ContentType.IMAGE,
            ".json": ContentType.TEXT,  # JSON files handled by StructuredDataContentProvider
            ".yaml": ContentType.TEXT,  # YAML files handled by StructuredDataContentProvider
            ".yml": ContentType.TEXT,   # YAML files handled by StructuredDataContentProvider
            ".txt": ContentType.TEXT,
            ".md": ContentType.MARKDOWN,
            ".rst": ContentType.TEXT,
            ".docx": ContentType.DOCUMENT,
            ".doc": ContentType.DOCUMENT,
            ".odt": ContentType.DOCUMENT,
            ".xlsx": ContentType.SPREADSHEET,
            ".xls": ContentType.SPREADSHEET,
            ".ods": ContentType.SPREADSHEET,
            ".csv": ContentType.SPREADSHEET,
            ".pptx": ContentType.PRESENTATION,
            ".ppt": ContentType.PRESENTATION,
            ".odp": ContentType.PRESENTATION,
            ".zip": ContentType.ARCHIVE,
            ".tar": ContentType.ARCHIVE,
            ".gz": ContentType.ARCHIVE,
            ".7z": ContentType.ARCHIVE,
            ".py": ContentType.CODE,
            ".js": ContentType.CODE,
            ".ts": ContentType.CODE,
            ".java": ContentType.CODE,
            ".cpp": ContentType.CODE,
            ".c": ContentType.CODE,
            ".h": ContentType.CODE,
            ".hpp": ContentType.CODE,
            ".rs": ContentType.CODE,
            ".go": ContentType.CODE,
        }

        return type_mapping.get(extension, ContentType.UNKNOWN)


# Global registry instance
_registry = ContentProviderRegistry()


def get_content_provider(content_path: str) -> ContentProvider:
    """
    Get the appropriate content provider for a file.

    Args:
        content_path: Path to the content file

    Returns:
        Content provider instance

    Raises:
        ValueError: If no suitable content provider is found for the file type
    """
    provider = _registry.get_provider(content_path)
    if provider is None:
        content_type = _registry._detect_content_type(content_path)
        raise ValueError(
            f"No content provider found for file: {content_path} "
            f"(detected type: {content_type}). "
            f"Available providers: {list(_registry._provider_map.keys())}"
        )
    return provider


def register_content_provider(
    provider_class: type[ContentProvider], is_default: bool = False
) -> None:
    """
    Register a content provider in the global registry.

    Args:
        provider_class: The provider class to register
        is_default: Whether this should be the default provider
    """
    _registry.register(provider_class, is_default)


def list_content_providers() -> dict[ContentType, str]:
    """
    List all registered content providers.

    Returns:
        Dictionary mapping content types to provider names
    """
    return _registry.list_providers()


def list_supported_content_types() -> list[ContentType]:
    """
    List all supported content types.

    Returns:
        List of supported content types
    """
    return _registry.list_supported_types()


def register_provider_map(provider_map: dict) -> None:
    """
    Register provider map for lazy loading in the global registry.

    Args:
        provider_map: Dictionary mapping content types to (module, class) tuples
    """
    _registry.register_provider_map(provider_map)


# Auto-register all providers on module import
from .auto_register import auto_register
auto_register()