"""Example of instrumenting agents with OpenTelemetry.

This example shows how to add selective instrumentation to P8FS agents
for distributed tracing and observability.
"""

from p8fs_api.observability import trace_agent, trace_llm_call, trace_operation


# Example 1: Basic Agent Instrumentation
class ContentAnalysisAgent:
    """Agent for analyzing content with OpenTelemetry instrumentation."""

    def __init__(self, model: str = "gpt-4o"):
        self.model = model

    @trace_agent()
    async def analyze(self, content: str, context: dict | None = None) -> dict:
        """Main entry point - automatically traced.

        Creates span: agent.ContentAnalysisAgent.analyze
        Includes: agent.name, agent.method, agent.args_count, agent.status
        """
        # Preprocessing happens within the parent span
        processed = self._preprocess(content)

        # LLM call is traced separately
        analysis = await self._call_llm(processed)

        # Post-processing happens within parent span
        result = self._format_result(analysis)

        return result

    @trace_llm_call(model="gpt-4o", provider="openai", temperature=0.7)
    async def _call_llm(self, text: str) -> str:
        """LLM call - traced with model metadata.

        Creates span: llm.openai.gpt-4o
        Includes: llm.model, llm.provider, llm.temperature, llm.status
        """
        # In real implementation, call LLM here
        # response = await self.llm_client.generate(text)
        return f"Analysis of: {text[:50]}..."

    def _preprocess(self, text: str) -> str:
        """Private method - not separately traced.

        Executes within parent span (analyze).
        Use this for quick operations.
        """
        return text.strip().lower()

    def _format_result(self, analysis: str) -> dict:
        """Private method - not separately traced."""
        return {"analysis": analysis, "model": self.model}


# Example 2: Custom Operation Tracing
class EmbeddingGenerator:
    """Generator that traces expensive operations."""

    @trace_agent("EmbeddingGenerator")
    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings with detailed operation tracing.

        Creates span: agent.EmbeddingGenerator.generate_embeddings
        """
        embeddings = []

        # Trace the actual embedding generation
        with trace_operation(
            "batch_embedding_generation",
            batch_size=len(texts),
            total_chars=sum(len(t) for t in texts),
            model="text-embedding-3-small",
        ):
            for text in texts:
                embedding = await self._embed_single(text)
                embeddings.append(embedding)

        return embeddings

    async def _embed_single(self, text: str) -> list[float]:
        """Individual embedding - happens within parent operation span."""
        # In real implementation, call embedding service
        return [0.1] * 1536


# Example 3: Complex Agent with Multiple Steps
class DreamAnalysisAgent:
    """Multi-step agent with selective instrumentation."""

    @trace_agent("DreamAnalyzer")
    async def analyze_dream(self, dream_text: str) -> dict:
        """Main analysis entry point.

        Creates span: agent.DreamAnalyzer.analyze_dream
        Child spans will be nested under this.
        """
        # Step 1: Extract entities (traced separately)
        entities = await self._extract_entities(dream_text)

        # Step 2: Analyze emotions (traced separately)
        emotions = await self._analyze_emotions(dream_text)

        # Step 3: Generate insights with LLM
        insights = await self._generate_insights(dream_text, entities, emotions)

        return {
            "entities": entities,
            "emotions": emotions,
            "insights": insights,
        }

    @trace_agent("EntityExtractor")
    async def _extract_entities(self, text: str) -> list[str]:
        """Extract entities - traced as separate operation.

        Creates span: agent.EntityExtractor._extract_entities
        Nested under analyze_dream span.
        """
        with trace_operation("nlp_processing", task="entity_extraction"):
            # NLP processing here
            return ["person", "place", "object"]

    @trace_agent("EmotionAnalyzer")
    async def _analyze_emotions(self, text: str) -> dict[str, float]:
        """Analyze emotions - traced as separate operation.

        Creates span: agent.EmotionAnalyzer._analyze_emotions
        """
        with trace_operation("emotion_classification", num_classes=6):
            # Emotion analysis here
            return {"joy": 0.3, "fear": 0.5, "sadness": 0.2}

    @trace_llm_call(model="gpt-4o", provider="openai", temperature=0.7, max_tokens=500)
    async def _generate_insights(
        self, text: str, entities: list[str], emotions: dict
    ) -> str:
        """Generate insights using LLM.

        Creates span: llm.openai.gpt-4o
        Nested under analyze_dream span.
        """
        prompt = f"Text: {text}\nEntities: {entities}\nEmotions: {emotions}"
        # LLM call here
        return "Dream analysis insights..."


# Example 4: Conditional Tracing
class AdaptiveAgent:
    """Agent that traces conditionally based on complexity."""

    def __init__(self, always_trace: bool = False):
        self.always_trace = always_trace

    async def process(self, input_data: str) -> dict:
        """Process with conditional tracing.

        Trace complex operations, skip simple ones.
        """
        # Simple operations - no tracing overhead
        if len(input_data) < 100:
            return self._simple_process(input_data)

        # Complex operations - traced
        return await self._complex_process(input_data)

    def _simple_process(self, data: str) -> dict:
        """Simple processing - not traced."""
        return {"result": data.upper()}

    @trace_agent("ComplexProcessor")
    async def _complex_process(self, data: str) -> dict:
        """Complex processing - traced."""
        with trace_operation("data_transformation", size=len(data)):
            # Complex processing here
            result = data.upper()

        return {"result": result, "processed": True}


# Example 5: Error Handling (exceptions are automatically recorded)
class RobustAgent:
    """Agent with proper error handling (traces exceptions automatically)."""

    @trace_agent("RobustAgent")
    async def risky_operation(self, input_data: str) -> dict:
        """Operation that might fail.

        If an exception is raised, it's automatically:
        - Recorded in the span with full traceback
        - Span status set to ERROR
        - Exception details added as span events

        No need to manually catch and record.
        """
        # This will be traced. If it raises an exception,
        # the span will record it automatically.
        result = await self._process_risky_data(input_data)

        return result

    async def _process_risky_data(self, data: str) -> dict:
        """This might raise an exception."""
        if not data:
            raise ValueError("Empty input data")

        return {"processed": data}


# Example 6: Integration with Existing Agent Base Classes
from typing import Protocol


class BaseAgent(Protocol):
    """Example base agent interface."""

    async def execute(self, input: str) -> dict:
        """Execute agent logic."""
        ...


class InstrumentedAgent:
    """Wrapper to add instrumentation to existing agents."""

    def __init__(self, agent: BaseAgent, agent_name: str):
        self.agent = agent
        self.agent_name = agent_name

    @trace_agent()
    async def execute(self, input: str) -> dict:
        """Traced execution wrapper.

        Wraps existing agent with tracing without modifying the original.
        """
        # Original agent logic is traced
        return await self.agent.execute(input)


# Usage Examples

async def example_usage():
    """Show how to use instrumented agents."""

    # Example 1: Basic agent
    agent = ContentAnalysisAgent()
    result = await agent.analyze("This is content to analyze")

    # Example 2: Embedding generation
    embedder = EmbeddingGenerator()
    embeddings = await embedder.generate_embeddings(["text1", "text2", "text3"])

    # Example 3: Complex multi-step agent
    dream_agent = DreamAnalysisAgent()
    analysis = await dream_agent.analyze_dream("I dreamed about flying...")

    # Example 4: Adaptive tracing
    adaptive = AdaptiveAgent()
    simple = await adaptive.process("short")  # Not traced
    complex = await adaptive.process("x" * 1000)  # Traced

    # Example 5: Error handling
    robust = RobustAgent()
    try:
        await robust.risky_operation("")
    except ValueError:
        # Exception was automatically recorded in span
        pass


# Resulting Span Hierarchy

"""
Example span hierarchy for ContentAnalysisAgent:

HTTP POST /api/v1/analyze [2.5s]
└─ agent.ContentAnalysisAgent.analyze [2.4s]
   ├─ llm.openai.gpt-4o [2.0s]
   │  ├─ http.client.request [1.9s]
   │  └─ (response parsing)
   └─ (formatting)


Example span hierarchy for DreamAnalysisAgent:

HTTP POST /api/v1/dream/analyze [3.2s]
└─ agent.DreamAnalyzer.analyze_dream [3.1s]
   ├─ agent.EntityExtractor._extract_entities [0.5s]
   │  └─ operation.nlp_processing [0.4s]
   ├─ agent.EmotionAnalyzer._analyze_emotions [0.3s]
   │  └─ operation.emotion_classification [0.2s]
   └─ llm.openai.gpt-4o [2.0s]


Each span includes:
- Timestamp (start/end)
- Duration
- Status (success/error)
- Attributes (agent.name, model, etc.)
- Events (exceptions, logs)
- Links (to parent spans)
"""


# Key Takeaways

"""
1. Use @trace_agent() on main entry points
   - Agent.analyze(), Agent.process(), Agent.execute()
   - Not on every private method

2. Use @trace_llm_call() for LLM interactions
   - Includes model, provider, temperature
   - Automatically tracks latency

3. Use trace_operation() for expensive operations
   - Embedding generation
   - Large computations
   - External service calls
   - Database queries (future)

4. Don't trace:
   - Simple getters/setters
   - Data transformations (< 1ms)
   - Private utilities
   - Loop iterations

5. Exceptions are automatically captured
   - No need to manually catch and record
   - Full traceback included in span
   - Span status set to ERROR

6. Nested operations create span hierarchy
   - Parent-child relationships preserved
   - Easy to see call flow
   - Duration rollup automatic

7. Use meaningful names
   - "DreamAnalyzer" not "agent1"
   - "embedding_generation" not "op1"
   - Include context as attributes
"""
