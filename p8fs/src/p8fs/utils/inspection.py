"""
Inspection utilities for P8FS models and classes.

This module provides utilities for inspecting Python classes and instances,
particularly for extracting methods and functions for agent registration.
"""

import inspect
import types
from typing import Any, Callable, List


def get_public_instance_methods(cls_or_instance: Any) -> List[tuple[str, Callable]]:
    """
    Get all public instance methods from a class or instance.
    
    Args:
        cls_or_instance: Class or instance to inspect
        
    Returns:
        List of tuples (method_name, method)
    """
    methods = []
    
    # Handle both classes and instances
    obj = cls_or_instance
    if inspect.isclass(cls_or_instance):
        # For classes, we need to check if methods are instance methods
        for name, method in inspect.getmembers(obj, inspect.isfunction):
            if not name.startswith('_'):  # Public methods only
                methods.append((name, method))
    else:
        # For instances, use a Pydantic-aware approach to avoid deprecation warnings
        # Check if this is a Pydantic model instance
        if hasattr(obj.__class__, 'model_fields'):
            # Use dir() and getattr() instead of inspect.getmembers() for Pydantic models
            # This avoids accessing deprecated __fields__ and __fields_set__ attributes
            # Also skip Pydantic internal attributes that trigger deprecation warnings
            SKIP_ATTRS = {'model_computed_fields', 'model_fields', '__fields__', '__fields_set__'}
            for name in dir(obj):
                if not name.startswith('_') and name not in SKIP_ATTRS:
                    try:
                        attr = getattr(obj, name)
                        if inspect.ismethod(attr):
                            methods.append((name, attr))
                    except AttributeError:
                        # Skip attributes that can't be accessed
                        continue
        else:
            # For non-Pydantic instances, use the regular approach
            for name, method in inspect.getmembers(obj, inspect.ismethod):
                if not name.startswith('_'):  # Public methods only
                    methods.append((name, method))
    
    return methods


def get_selective_instance_methods(cls_or_instance: Any, inheriting_from: type = None) -> List[tuple[str, Callable]]:
    """
    Get selectively filtered public instance methods from a class or instance.
    
    This function provides more selective filtering than get_public_instance_methods,
    filtering out common inherited methods and only returning methods that are likely
    intended for external use (e.g., as LLM functions).
    
    Args:
        cls_or_instance: Class or instance to inspect
        inheriting_from: Optional base class to exclude inherited methods from
        
    Returns:
        List of tuples (method_name, method) for selective methods only
    """
    # Common methods to exclude (from object, dict, etc.)
    EXCLUDED_METHODS = {
        'model_dump', 'model_dump_json', 'model_validate', 'model_validate_json',
        'model_copy', 'model_fields_set', 'model_config',
        'dict', 'json', 'copy', 'update', 'clear', 'get', 'items', 'keys', 'values',
        'pop', 'popitem', 'setdefault', '__dict__', '__class__', '__module__',
        '__weakref__', '__annotations__', '__doc__',
        # Pydantic v2 methods
        'model_construct', 'model_rebuild', 'model_post_init'
    }
    
    methods = []
    
    def _get_defining_class(member, cls):
        """Get the class that defines this method."""
        defining_class = getattr(member, "__objclass__", None)
        if defining_class:
            return defining_class
        
        for base_class in cls.mro():
            if hasattr(base_class, member.__name__) and getattr(base_class, member.__name__) is member:
                return base_class
        return cls
    
    def _is_strict_subclass(subclass, superclass):
        """Check if subclass is a strict subclass (not the same class)."""
        try:
            if not subclass:
                return False
            return issubclass(subclass, superclass) and subclass is not superclass
        except:
            return False
    
    def _should_include_method(name, member):
        """Determine if a method should be included in the selective list."""
        # Skip private methods
        if name.startswith('_'):
            return False
            
        # Skip excluded common methods
        if name in EXCLUDED_METHODS:
            return False
            
        # If inheriting_from is specified, check inheritance
        if inheriting_from:
            cls = cls_or_instance if inspect.isclass(cls_or_instance) else cls_or_instance.__class__
            defining_class = _get_defining_class(member, cls)

            # Exclude methods defined on the base class itself
            if defining_class is inheriting_from:
                return False
            
        return True
    
    # Handle both classes and instances
    obj = cls_or_instance
    if inspect.isclass(cls_or_instance):
        # For classes, we need to check if methods are instance methods
        for name, method in inspect.getmembers(obj, inspect.isfunction):
            if _should_include_method(name, method):
                methods.append((name, method))
    else:
        # For instances, use a Pydantic-aware approach to avoid deprecation warnings
        # Check if this is a Pydantic model instance
        if hasattr(obj.__class__, 'model_fields'):
            # Use dir() and getattr() instead of inspect.getmembers() for Pydantic models
            # This avoids accessing deprecated __fields__ and __fields_set__ attributes
            # Also skip Pydantic internal attributes that trigger deprecation warnings
            SKIP_ATTRS = {'model_computed_fields', 'model_fields', '__fields__', '__fields_set__'}
            for name in dir(obj):
                if not name.startswith('_') and name not in SKIP_ATTRS:
                    try:
                        attr = getattr(obj, name)
                        if inspect.ismethod(attr) and _should_include_method(name, attr):
                            methods.append((name, attr))
                    except AttributeError:
                        # Skip attributes that can't be accessed
                        continue
        else:
            # For non-Pydantic instances, use the regular approach
            for name, method in inspect.getmembers(obj, inspect.ismethod):
                if _should_include_method(name, method):
                    methods.append((name, method))
    
    return methods


def get_public_class_methods(cls: type) -> List[Callable]:
    """
    Get all public class methods from a class.
    
    Args:
        cls: Class to inspect
        
    Returns:
        List of public class methods
    """
    methods = []
    
    for name, method in inspect.getmembers(cls, inspect.ismethod):
        if not name.startswith('_') and isinstance(method, classmethod):
            methods.append(method)
    
    return methods


def get_all_public_methods(cls_or_instance: Any) -> List[Callable]:
    """
    Get all public methods (both instance and class methods) from a class or instance.
    
    Args:
        cls_or_instance: Class or instance to inspect
        
    Returns:
        List of all public methods
    """
    methods = []
    
    # Get instance methods
    methods.extend(get_public_instance_methods(cls_or_instance))
    
    # Get class methods if we have a class
    if inspect.isclass(cls_or_instance):
        methods.extend(get_public_class_methods(cls_or_instance))
    else:
        # For instances, get class methods from the class
        methods.extend(get_public_class_methods(cls_or_instance.__class__))
    
    return methods


def is_callable_method(obj: Any, method_name: str) -> bool:
    """
    Check if an object has a callable method with the given name.
    
    Args:
        obj: Object to check
        method_name: Name of the method
        
    Returns:
        True if the object has a callable method with that name
    """
    if not hasattr(obj, method_name):
        return False
    
    attr = getattr(obj, method_name)
    return callable(attr)


def get_method_signature(method: Callable) -> dict:
    """
    Get the signature information for a method.
    
    Args:
        method: Method to inspect
        
    Returns:
        Dictionary with signature information
    """
    try:
        sig = inspect.signature(method)
        
        return {
            'name': method.__name__,
            'doc': method.__doc__,
            'parameters': {
                name: {
                    'type': param.annotation if param.annotation != param.empty else None,
                    'default': param.default if param.default != param.empty else None,
                    'required': param.default == param.empty
                }
                for name, param in sig.parameters.items()
                if name != 'self'  # Exclude self parameter
            },
            'return_type': sig.return_annotation if sig.return_annotation != sig.empty else None,
            'is_async': inspect.iscoroutinefunction(method)
        }
    except Exception as e:
        return {
            'name': getattr(method, '__name__', 'unknown'),
            'doc': getattr(method, '__doc__', None),
            'parameters': {},
            'return_type': None,
            'is_async': False,
            'error': str(e)
        }


def load_entity(entity_name: str):
    """
    Load an entity/agent by name from the model registry.
    
    This function attempts to load entities in the following order:
    1. Built-in P8FS agents (e.g., p8-research, p8-analysis)
    2. Custom agents from the database
    3. Abstract model creation as fallback
    
    Args:
        entity_name: The name of the entity to load (e.g., "p8-research", "Agent")
        
    Returns:
        AbstractModel instance or None if not found
    """
    from p8fs_cluster.logging import get_logger
    
    logger = get_logger(__name__)
    
    try:
        # Try to load built-in P8FS agents first
        if entity_name.startswith("p8-") or entity_name in ["Agent", "Research", "Analysis"]:
            from p8fs.models.p8 import Agent
            
            # Map common agent names to Agent class
            if entity_name in ["p8-research", "research", "Research"]:
                return Agent.create_research_agent()
            elif entity_name in ["p8-analysis", "analysis", "Analysis"]:
                return Agent.create_analysis_agent()
            elif entity_name in ["Agent", "agent"]:
                return Agent()
            
        # Try to load from database using TenantRepository
        try:
            from p8fs.repository import TenantRepository
            from p8fs.models.p8 import Agent as AgentModel
            
            # Use default tenant for now - could be made configurable
            repo = TenantRepository(AgentModel, tenant_id="default")
            
            # Try to find by name/key
            agents = repo.find_by_filter({"name": entity_name})
            if agents: 
                return agents[0]
                
        except Exception as e:
            logger.debug(f"Failed to load entity from database: {e}")
        
        # Try dynamic import for built-in models
        try:
            from p8fs.models.base import AbstractModel
            from p8fs.models import p8
            
            # Check if it's available in the p8 module
            if hasattr(p8, entity_name):
                return getattr(p8, entity_name)
                
        except Exception as e:
            logger.debug(f"Failed dynamic import for entity {entity_name}: {e}")
        
        # Last resort: create abstract model
        from p8fs.models.base import AbstractModel
        
        logger.info(f"Creating abstract model for entity: {entity_name}")
        return AbstractModel.create_model(
            name=entity_name,
            namespace="dynamic",
            description=f"Dynamically created model for {entity_name}"
        )
        
    except Exception as e:
        logger.error(f"Failed to load entity {entity_name}: {e}")
        return None