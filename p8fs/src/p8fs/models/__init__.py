"""P8FS Core Models - AbstractModel base classes and model utilities."""

from ..utils import make_uuid
from .base import AbstractEntityModel, AbstractModel
from .mixins import AbstractModelMixin

# Token usage calculator
from .audit_session import TokenUsageCalculator

# Core P8FS models
from .p8 import (
    Agent,
    ApiProxy,
    ChannelType,
    Error,
    Files,
    Function,
    Job,
    JobStatus,
    JobType,
    LanguageModelApi,
    Project,
    Resources,
    Session,
    SessionType,
    Task,
    TokenUsage,
    User,
)

# System agent
from .system_agent import SystemAgent

# Engram models are now in p8.py


# Build __all__ dynamically based on available imports
__all__ = [
    # Base classes
    "AbstractModel",
    "AbstractEntityModel",
    "AbstractModelMixin",
    # Token calculator
    "TokenUsageCalculator",
    # P8FS enums
    "JobStatus",
    "JobType",
    "SessionType",
    "ChannelType",
    # P8FS core models
    "Function",
    "ApiProxy",
    "LanguageModelApi",
    "Agent",
    "TokenUsage",
    "Session",
    "User",
    "Resources",
    "Project",
    "Task",
    "Files",
    "Error",
    "Job",
    # System agent
    "SystemAgent",
    # Engram and Moment models are now exported from p8.py
]


# this is just a sample - these are registered in databases
def _create_model_configs():
    """Generate language model configurations grouped by provider."""
    model_groups = {
        "openai": {
            "scheme": "openai",
            "completions_uri": "https://api.openai.com/v1/chat/completions",
            "token_env_key": "OPENAI_API_KEY",
            "models": [
                "gpt-5",
                "gpt-5-mini",
                "gpt-5-2025-08-07",
                "gpt-4o-2024-08-06",
                "gpt-4o-mini",
                "gpt-4.1",
                "gpt-4.1-mini",
                "gpt-4.1-nano",
                "gpt-4.1-2025-04-14",
            ],
        },
        "cerebras": {
            "scheme": "openai",
            "completions_uri": "https://api.cerebras.ai/v1/chat/completions",
            "token_env_key": "CEREBRAS_API_KEY",
            "models": [{"name": "cerebras-llama3.1-8b", "model": "llama3.1-8b"}],
        },
        "groq": {
            "scheme": "openai",
            "completions_uri": "https://api.groq.com/openai/v1/chat/completions",
            "token_env_key": "GROQ_API_KEY",
            "models": [
                {
                    "name": "groq-llama-3.3-70b-versatile",
                    "model": "llama-3.3-70b-versatile",
                }
            ],
        },
        "anthropic": {
            "scheme": "anthropic",
            "completions_uri": "https://api.anthropic.com/v1/messages",
            "token_env_key": "ANTHROPIC_API_KEY",
            "models": ["claude-3-5-sonnet-20241022", "claude-3-7-sonnet-20250219"],
        },
        "google": {
            "scheme": "google",
            "completions_uri": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            "token_env_key": "GEMINI_API_KEY",
            "models": [
                "gemini-1.5-flash",
                "gemini-2.0-flash",
                "gemini-2.0-flash-thinking-exp-01-21",
                "gemini-2.0-pro-exp-02-05",
            ],
        },
        "deepseek": {
            "scheme": "openai",
            "completions_uri": "https://api.deepseek.com/chat/completions",
            "token_env_key": "DEEPSEEK_API_KEY",
            "models": ["deepseek-chat"],
        },
        "xai": {
            "scheme": "openai",
            "completions_uri": "https://api.x.ai/v1/chat/completions",
            "token_env_key": "XAI_API_KEY",
            "models": ["grok-2-latest"],
        },
        "inception": {
            "scheme": "openai",
            "completions_uri": "https://api.inceptionlabs.ai/v1/chat/completions",
            "token_env_key": "INCEPTION_API_KEY",
            "models": ["mercury-coder-small"],
        },
    }

    all_models = []
    for config in model_groups.values():
        for model in config["models"]:
            if isinstance(model, dict):
                model_name = model["name"]
                model_id = model.get("model", model_name)
                model_kwargs = {"model": model_id} if "model" in model else {}
            else:
                model_name = model
                model_kwargs = {}

            completions_uri = config["completions_uri"]
            if "{model}" in completions_uri:
                completions_uri = completions_uri.format(model=model_name)

            all_models.append(
                LanguageModelApi(
                    id=make_uuid(model_name),
                    name=model_name,
                    scheme=config["scheme"],
                    completions_uri=completions_uri,
                    token_env_key=config["token_env_key"],
                    **model_kwargs,
                )
            )

    return all_models


sample_models = _create_model_configs()
