"""P8FS Core LLM Services - Language models, memory proxy, and embeddings.

CRITICAL SURFACE AREA TESTS REQUIRED:

1. **Function Calling + Streaming**: 
   - Agentic loops with real-time function execution
   - Tool call buffering across streaming chunks
   - Function result injection back into conversation
   - Native dialect function calling (OpenAI tools vs Anthropic tool_use vs Google functionCall)

2. **Protocol Adaptation Matrix**:
   - Anthropic requests → OpenAI streaming deltas (core conversion)
   - Google requests → OpenAI streaming deltas  
   - OpenAI requests → OpenAI streaming deltas (passthrough with buffering)
   - Cross-provider message format translation
   - Native dialect preservation in message stacks

3. **Batch + Streaming/Non-streaming Combinations**:
   - Batch mode with streaming collection
   - Batch mode with non-streaming aggregation
   - Protocol adaptation in batch mode (Anthropic batch → OpenAI format)
   - Cost optimization validation (50-95% savings)
   - Batch job tracking and status monitoring

4. **Complete Token Capture**:
   - Input/output token counting across all providers
   - Usage aggregation in streaming mode
   - Cost calculation accuracy
   - Token usage in function calling scenarios
   - Batch processing token optimization tracking

5. **Full Dialect Matrix Testing**:
   - OpenAI ↔ Anthropic ↔ Google (all 6 combinations)
   - Streaming ↔ Non-streaming for each provider
   - Function calling in each native dialect
   - Message stack consistency across providers
   - Error handling and fallback scenarios

All combinations must be tested with real provider APIs and real token consumption.

**Comprehensive Test Coverage:**
- tests/integration/test_memory_proxy_integration.py: Basic memory proxy functionality
- tests/integration/test_protocol_adaptation_comprehensive.py: Full protocol adaptation matrix
- tests/sample_data/llm_responses/: Sample streaming data for all providers (OpenAI, Anthropic, Google)

**System Prompt Testing:**
Memory proxy automatically sends system prompts from agent.get_model_description() when agent context
is provided. This ensures docstrings become system prompts and agent methods become available functions.

See tests/sample_data/ for provider-specific test data and response formats.
"""

from .base_proxy import BaseProxy
from .embedding_providers import (
    BaseEmbeddingProvider,
    EmbeddingService,
    LocalEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_service,
)
from .language_model import LanguageModel
from .memory_proxy import MemoryProxy
from .models import (
    BatchCallingContext,
    BatchResponse,
    CallingContext,
    JobStatusResponse,
)
from .openai_client import OpenAIRequestsClient

__all__ = [
    "LanguageModel",
    "BaseProxy",
    "MemoryProxy",
    "OpenAIRequestsClient",
    "CallingContext",
    "BatchCallingContext", 
    "BatchResponse",
    "JobStatusResponse",
    "BaseEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "LocalEmbeddingProvider",
    "EmbeddingService",
    "get_embedding_service"
]