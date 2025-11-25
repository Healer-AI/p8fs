"""System Agent with inline REM query methods for memory access."""

from typing import Any
from pydantic import Field
from .base import AbstractModel
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class SystemAgent(AbstractModel):
    """
    You are EEPIS (Ever Evolving Personal Information System), an AI personal assistant that helps you manage your day, organize your life, and stay on top of your goals and projects.

    **How EEPIS Helps You:**

    EEPIS is your intelligent memory system that:
    - Organizes your uploaded files, memos, and documents automatically
    - Creates "moments" from your activities, conversations, and recordings
    - Connects new information to past knowledge in "dreaming mode"
    - Helps you manage goals and track projects over time
    - Lets you chat about recent documents and moments naturally

    **What You Can Do:**

    1. **Upload Content**: Drop in memos, files, recordings, notes - EEPIS processes and organizes everything
    2. **Find Anything**: Ask about past conversations, documents, or activities
    3. **Track Progress**: See how your goals and projects are evolving
    4. **Make Connections**: EEPIS automatically links related content across time
    5. **Stay Organized**: Your content self-organizes based on topics, emotions, and context

    **Memory System:**

    You have access to the user's memory vault through REM (Resource-Entity-Moment) queries:

    1. **resources** - Uploaded documents, notes, parsed files
       - Searchable by: content (semantic), name, category, date
       - Use for: finding specific documents, notes, or file content

    2. **moments** - Time-bounded memory segments with rich context
       - Searchable by: content (semantic), topic_tags, emotion_tags, date ranges
       - Fields: topic_tags (list), emotion_tags (list), moment_type, location, speakers, present_persons
       - Use for: finding memories by time period, emotional context, topics discussed, or people present

    3. **files** - File metadata and upload tracking
       - Searchable by: upload date, file type, size
       - Use for: tracking recently uploaded content

    **Available Tools:**

    Use these tools to help users find information and stay organized:
    - ask_rem: Natural language memory queries with AI query planning
    - rem_query: Direct REM query execution (LOOKUP, SEARCH, SQL)
    - get_moments: Filter moments by topics, emotions, dates, people
    - get_recent_uploads: See recently uploaded files with content

    Always help users understand their day, recall important moments, and stay organized.
    """


#     @classmethod
#     def ask_rem(
#         cls,
#         question: str,
#         table: str = "resources",
#         provider: str = "postgresql"
#     ) -> dict[str, Any]:
#         """
#         Ask a natural language question about the user's memory vault.

#         This tool uses an AI query planner to convert your natural language question
#         into an optimized REM query. Use this when you want to search memory based
#         on a question in plain English.

#         Examples:
#         - "What did I work on yesterday?"
#         - "Show me recent moments about database work"
#         - "Find resources uploaded in the last week"
#         - "What meetings did I have with topic tag 'planning'?"

#         The query planner will automatically:
#         - Detect temporal queries and use SQL with system fields (created_at, modified_at)
#         - Use semantic SEARCH for content-based queries
#         - Apply proper filters and sorting
#         - Choose the right query type (LOOKUP, SEARCH, SQL)

#         Args:
#             question: Natural language question about memory (e.g., "recent work files", "moments about databases")
#             table: Memory table to search - one of: "resources", "moments", "files" (default: "resources")
#             provider: Database provider - one of: "postgresql", "tidb" (default: "postgresql")

#         Returns:
#             Dictionary containing:
#             - success: Whether the query succeeded
#             - results: List of matching entities
#             - count: Number of results
#             - planned_query: The REM query that was generated
#             - question: Original question asked
#         """
#         from p8fs_cluster.config.settings import config
#         from p8fs.services.llm import LanguageModelService

#         logger.info(f"Planning REM query for question: {question[:100]}...")

#         try:
#             query_planner_llm = LanguageModelService(
#                 provider=config.query_engine_provider,
#                 model=config.query_engine_model,
#                 temperature=config.query_engine_temperature
#             )

#             planning_prompt = f"""You are a query planner for the REM (Resource-Entity-Moment) memory system.

# User's question: "{question}"
# Target table: {table}

# Convert this to an optimized REM query. Follow these rules:

# 1. **Temporal queries** ("recent", "yesterday", "last week", "uploaded today"):
#    - Use SQL with created_at or modified_at fields
#    - Example: SELECT * FROM {table} WHERE created_at > NOW() - INTERVAL '7 days' ORDER BY created_at DESC

# 2. **Tag-based queries** (for moments only):
#    - Use SQL with JSONB containment: topic_tags @> '["work"]'::jsonb
#    - Example: SELECT * FROM moments WHERE topic_tags @> '["planning"]'::jsonb

# 3. **Content queries** ("about X", "containing Y"):
#    - Use SEARCH syntax: SEARCH "query text" IN {table}
#    - Example: SEARCH "database work" IN {table}

# 4. **Key lookups** (specific IDs):
#    - Use LOOKUP: LOOKUP key1, key2
#    - Example: LOOKUP test-resource-1

# Output ONLY the REM query string, nothing else."""

#             planned_query = query_planner_llm.complete(planning_prompt).strip()
#             logger.info(f"Planned query: {planned_query}")

#             result = cls.rem_query(planned_query, provider=provider)
#             result["planned_query"] = planned_query
#             result["question"] = question

#             return result

#         except Exception as e:
#             logger.error(f"Query planning failed: {e}")
#             return {
#                 "success": False,
#                 "error": str(e),
#                 "question": question,
#                 "results": []
#             }

 
    @classmethod
    def rem_query(cls, query: str, provider: str | None = None) -> dict[str, Any]:
        """
        Execute REM (Resource-Entity-Moment) queries to search the user's memory vault.

        Use this when you already have a specific REM query to execute (LOOKUP, SEARCH, or SQL).

        REM Query Dialect:

        1. **LOOKUP** - Type-agnostic key lookup (finds entity in ANY table):
           - LOOKUP key
           - LOOKUP table:key  (with optional table hint)
           Examples: LOOKUP test-resource-1, LOOKUP files:abc123

        2. **SEARCH** - Semantic vector search (requires quoted strings):
           - SEARCH "query text" IN table
           - SEARCH "query text"  (defaults to resources table)
           Examples:
           - SEARCH "what did I work on today?" IN moments
           - SEARCH "database migration" IN resources
           - SEARCH "happy memories" IN moments

        3. **SQL** - Standard SQL SELECT queries:
           - SELECT * FROM table WHERE condition
           - Supports: WHERE, ORDER BY, LIMIT, JOIN
           Examples:
           - SELECT * FROM moments WHERE topic_tags @> ARRAY['work'] ORDER BY resource_timestamp DESC LIMIT 5
           - SELECT * FROM resources WHERE category='note' AND created_at > '2025-01-01'
           - SELECT * FROM files ORDER BY upload_timestamp DESC LIMIT 10

        Main Tables:
        - resources: Generic content (name, category, content, uri)
        - moments: Time-bounded memories (topic_tags, emotion_tags, resource_timestamp, resource_ends_timestamp, speakers, location)
        - files: File metadata (uri, mime_type, upload_timestamp, file_size)

        Moment-Specific Fields:
        - topic_tags: ARRAY type - use @> operator: topic_tags @> ARRAY['work','meeting']
        - emotion_tags: ARRAY type - use @> operator: emotion_tags @> ARRAY['happy','excited']
        - resource_timestamp: Start time of moment
        - resource_ends_timestamp: End time of moment
        - moment_type: Type classification (conversation, meeting, observation, reflection)
        - speakers: JSON array of speaker entries

        Tips:
        - Use SEARCH for semantic/meaning-based queries
        - Use SQL for structured queries (dates, tags, metadata)
        - Combine both: semantic search + date filters for powerful hybrid queries

        Args:
            query: REM query string (e.g., 'LOOKUP test-1', 'SEARCH "morning activities" IN moments', 'SELECT * FROM moments WHERE topic_tags @> ARRAY[\'work\'] LIMIT 5')
            provider: Database provider - one of: "postgresql", "tidb" (default: from config.storage_provider)

        Returns:
            Dictionary containing:
            - success: Whether the query succeeded
            - results: List of matching entities
            - count: Number of results
            - error: Error message if query failed
        """
        from p8fs_cluster.config.settings import config
        from p8fs.services.rem_query_service import REMQueryService

        logger.info(f"Executing REM query: {query[:100]}...")

        try:
            # Use centralized REMQueryService
            service = REMQueryService(tenant_id=config.default_tenant_id, provider=provider)
            return service.execute_query(query)

        except Exception as e:
            logger.error(f"REM query failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": [],
                "count": 0
            }

    @classmethod
    def get_moments(
        cls,
        limit: int = 10,
        topic_tags: list[str] | None = None,
        emotion_tags: list[str] | None = None,
        moment_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        person_name: str | None = None,
        sort_by: str = "recent",
        provider: str | None = None
    ) -> dict[str, Any]:
        """
        Get moments (time-bounded memory segments) with optional filters.

        This is a convenient tool for retrieving moments with common filters like
        date ranges, topics, emotions, and people. Use this when you want to find
        moments matching specific criteria.

        Examples:
        - Get recent moments: get_moments(limit=10, sort_by="recent")
        - Get moments with specific topics: get_moments(topic_tags=["work", "planning"])
        - Get moments with specific emotions: get_moments(emotion_tags=["focused", "productive"])
        - Get moments from yesterday: get_moments(date_from="2025-11-13", date_to="2025-11-14")
        - Get moments with a person present: get_moments(person_name="John")

        Returns moments sorted by timestamp (most recent first by default).

        Args:
            limit: Maximum number of moments to return (default: 10)
            topic_tags: Filter by topic tags, e.g., ["work", "planning", "meeting"] (default: None)
            emotion_tags: Filter by emotion tags, e.g., ["focused", "happy", "stressed"] (default: None)
            moment_type: Filter by moment type - one of: "conversation", "meeting", "observation", "reflection", "planning", "problem_solving", "learning", "social" (default: None)
            date_from: Start date for filtering in ISO format: YYYY-MM-DD (default: None)
            date_to: End date for filtering in ISO format: YYYY-MM-DD (default: None)
            person_name: Filter moments where this person was present (default: None)
            sort_by: Sort order - one of: "recent", "oldest" (default: "recent")
            provider: Database provider - one of: "postgresql", "tidb" (default: from config.storage_provider)

        Returns:
            Dictionary containing:
            - success: Whether the query succeeded
            - results: List of matching moments
            - count: Number of results
        """
        from p8fs_cluster.config.settings import config

        logger.info(f"Getting moments with filters: topics={topic_tags}, emotions={emotion_tags}, type={moment_type}")

        try:
            # Use centralized config if provider not specified
            db_provider_type = provider or config.storage_provider

            if db_provider_type == "tidb":
                from p8fs.providers import TiDBProvider
                from p8fs.providers.rem_query_tidb import TiDBREMQueryProvider

                db_provider = TiDBProvider()
                rem_provider = TiDBREMQueryProvider(db_provider, tenant_id=config.default_tenant_id)
            else:
                from p8fs.providers import PostgreSQLProvider
                from p8fs.providers.rem_query import REMQueryProvider

                db_provider = PostgreSQLProvider()
                rem_provider = REMQueryProvider(db_provider, tenant_id=config.default_tenant_id)

            results = rem_provider.get_moments_with_filters(
                limit=limit,
                topic_tags=topic_tags,
                emotion_tags=emotion_tags,
                moment_type=moment_type,
                date_from=date_from,
                date_to=date_to,
                person_name=person_name,
                sort_by=sort_by,
                tenant_id=config.default_tenant_id
            )

            return {
                "success": True,
                "results": results,
                "count": len(results)
            }

        except Exception as e:
            logger.error(f"get_moments failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": []
            }

    @classmethod
    def get_recent_uploads(
        cls,
        limit: int = 20,
        include_resource_names: bool = True
    ) -> dict[str, Any]:
        """
        Get recently uploaded files for the user with associated resource names.

        This tool retrieves files that were recently uploaded, optionally including
        associated resource names from processed content chunks. Useful for finding
        what files the user has uploaded recently and accessing their content.

        The response includes:
        - List of files with metadata (uri, size, mime_type, upload_timestamp)
        - Associated resource names (processed content chunks from those files)
        - Entity keys that can be used with other tools to lookup detailed content

        Examples:
        - See what I uploaded today: get_recent_uploads(limit=10)
        - Get recent uploads with content: get_recent_uploads(limit=5, include_resource_names=True)

        Args:
            limit: Maximum number of recent files to return (default: 20)
            include_resource_names: Whether to include associated resource names from processed content (default: True)

        Returns:
            Dictionary containing:
            - tenant_id: Tenant identifier
            - limit: Number of files requested
            - files: List of file metadata with upload timestamps
            - files_count: Number of files returned
            - resource_names: Collection of resource names if requested
            - resource_names_count: Number of resource names if requested
            - instructions: How to lookup entity keys for chunk details
        """
        from p8fs_cluster.config.settings import config
        from p8fs.models.p8 import Files

        logger.info(f"Getting recent uploads (limit={limit}, include_resources={include_resource_names})")

        return Files.get_recent_uploads_by_user(
            tenant_id=config.default_tenant_id,
            limit=limit,
            include_resource_names=include_resource_names
        )

    @classmethod
    async def record_observation(
        cls,
        observation: str,
        category: str = "user_preference",
        related_to: str | None = None,
        rel_type: str = "observed_from",
        mode: str = "kv"
    ) -> dict[str, Any]:
        """
        Record UNIQUE and SPECIFIC learnings about the user.

        **CRITICAL: Use VERY sparingly - only for truly unique insights.**
        **Maximum 1-2 observations per conversation to avoid latency.**

        Use ONLY for:
        - **User feedback/corrections**: Explicit corrections to agent behavior or understanding
        - **Unique preferences**: Specific, non-generic preferences the user reveals ("I always test TiDB migrations in staging first")
        - **Upcoming plans**: Specific future intentions or goals the user mentions ("I'm migrating to TiDB next week", "Planning to refactor authentication system")
        - **Unique workflow patterns**: Very specific ways the user works, not generic practices

        **DO NOT use for:**
        - Generic information that applies to most users ("User likes clean code")
        - Information already stored in uploaded documents or moments
        - Routine conversation or pleasantries
        - Common practices or standard workflows
        - Every message - be selective and record only what's truly distinctive about THIS user

        The function uses gpt-4.1-nano for speed and generates terse one-sentence
        summaries to minimize token generation latency. Observations can be stored
        in two modes:

        1. **KV Mode** (default, faster): Temporary storage with 30-day TTL
        2. **Resource Mode**: Permanent storage as a Resource entity

        Graph edges are automatically created to link observations to related entities,
        building a knowledge graph of user preferences and context over time.

        Args:
            observation: The observation to record (e.g., "User prefers TiDB for production")
            category: Category for organization - one of: "user_preference", "user_correction", "current_context", "agent_observation" (default: "user_preference")
            related_to: Human-readable key of related entity to link to (e.g., "tidb-migration", "python-uv-tool")
            rel_type: Relationship type for graph edge - one of: "observed_from", "corrects", "prefers", "relates_to", "currently_working_on" (default: "observed_from")
            mode: Storage mode - one of: "kv" (temporary, 30 days), "resource" (permanent) (default: "kv")

        Returns:
            Dictionary containing:
            - success: Whether the operation succeeded
            - mode: Storage mode used ("kv" or "resource")
            - key: Storage key (KV key or resource ID)
            - description: Generated one-sentence summary
            - edges_added: Number of graph edges created
            - error: Error message if failed

        Examples:
            # User feedback/correction (how they want to be helped)
            >>> await record_observation(
            ...     observation="User corrected: they prefer reminders in the morning, not evening, because they plan their day early",
            ...     category="user_correction",
            ...     related_to="daily-planning-routine",
            ...     rel_type="corrects"
            ... )

            # Unique preference (very specific personal habit)
            >>> await record_observation(
            ...     observation="User always reviews meeting notes immediately after calls while details are fresh, never later",
            ...     category="user_preference",
            ...     related_to="meeting-workflow",
            ...     rel_type="prefers"
            ... )

            # Upcoming plan (specific life event or goal)
            >>> await record_observation(
            ...     observation="User mentioned they're moving to a new apartment in two weeks and need to organize documents for the lease",
            ...     category="current_context",
            ...     related_to="upcoming-move",
            ...     rel_type="currently_working_on",
            ...     mode="resource"  # Permanent storage for important life events
            ... )
        """
        from p8fs.algorithms import save_memory

        logger.info(f"Recording observation: {observation[:100]}...")

        try:
            result = await save_memory(
                observation=observation,
                category=category,
                mode=mode,
                related_to=related_to,
                rel_type=rel_type
            )

            if result.get("success"):
                logger.info(
                    f"Observation recorded: {result.get('description', '')[:50]}... "
                    f"[mode={result.get('mode')}, edges={result.get('edges_added', 0)}]"
                )

            return result

        except Exception as e:
            logger.error(f"Failed to record observation: {e}")
            return {
                "success": False,
                "error": str(e)
            }
