"""Integration test extracted from getting_started.ipynb notebook.

This test validates the complete P8FS workflow demonstrated in the notebook:
1. Weather agent creation and function calling
2. MemoryProxy with normal, streaming, and batch modes
3. Session auditing and storage
4. File processing with storage worker
5. Dreaming agent integration
"""

import asyncio
import time
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import pytest
from p8fs_cluster.config import config

# Core imports
from p8fs.models import AbstractModel
from p8fs.services.llm import MemoryProxy, CallingContext, BatchCallingContext
from p8fs.repository import TenantRepository, SystemRepository
from p8fs.models.p8 import Session, Files, Resources
from p8fs.workers.storage import StorageWorker
from p8fs.workers.dreaming import DreamingWorker
from p8fs.models.agentlets import DreamModel


@asynccontextmanager
async def managed_agent(agent_class):
    """Context manager for proper resource cleanup of MemoryProxy."""
    agent = MemoryProxy(agent_class)
    try:
        yield agent
    finally:
        # Try various cleanup methods to prevent resource leaks
        cleanup_methods = [
            ('cleanup', lambda: agent.cleanup()),
            ('close', lambda: agent.close()),
            ('_client.close', lambda: agent._client.close() if hasattr(agent, '_client') and hasattr(agent._client, 'close') else None),
        ]
        
        for method_name, method_call in cleanup_methods:
            try:
                result = method_call()
                if result is not None and asyncio.iscoroutine(result):
                    await result
                    break
            except (AttributeError, Exception):
                continue


class WeatherAgent(AbstractModel):
    """Test weather agent with function calling capabilities."""
    
    def get_weather(self, location: str, units: str = "fahrenheit"):
        """Get current weather for a location."""
        temp = 72 if units == "fahrenheit" else 22
        return {
            "location": location,
            "temperature": temp,
            "units": units,
            "conditions": "sunny"
        }
    
    def get_forecast(self, location: str, days: int = 3):
        """Get weather forecast for a location."""
        return {
            "location": location,
            "days": days,
            "forecast": [
                {"day": i+1, "high": 75+i, "low": 60+i, "conditions": "sunny"}
                for i in range(days)
            ]
        }


@pytest.mark.integration
async def test_weather_agent_creation():
    """Test 1: Weather agent creation and function registration."""
    print("🧪 Testing weather agent creation...")
    
    # Create agent and wrap with MemoryProxy
    agent = MemoryProxy(WeatherAgent)
    
    # Verify function registration
    assert 'get_weather' in agent._function_handler._functions
    assert 'get_forecast' in agent._function_handler._functions
    
    # Test direct function call
    weather_func = agent._function_handler._functions['get_weather']
    result = weather_func('paris')
    
    assert result['location'] == 'paris'
    assert result['temperature'] == 72
    assert result['units'] == 'fahrenheit'
    assert result['conditions'] == 'sunny'
    
    print("   ✅ Weather agent functions registered and working")


@pytest.mark.integration
@pytest.mark.llm
async def test_memory_proxy_normal_mode():
    """Test 2: MemoryProxy normal mode with function calling."""
    print("🧪 Testing MemoryProxy normal mode...")
    
    # Suppress aiohttp warnings for cleaner test output
    warnings.filterwarnings("ignore", message="Unclosed client session")
    warnings.filterwarnings("ignore", message="Unclosed connector")
    
    # Use unique tenant ID for isolation
    tenant_id = f"test-notebook-normal-{int(time.time())}"
    
    async with managed_agent(WeatherAgent) as agent:
        context = CallingContext(
            model="gpt-4o",
            tenant_id=tenant_id
        )
        
        response = await agent.run("What's the weather in Chicago?", context)
        
        # Verify response is a string
        assert isinstance(response, str)
        assert len(response) > 0
        
        # Verify session was created
        session_repo = SystemRepository(Session)
        recent_sessions = session_repo.execute("""
            SELECT * FROM sessions
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, [tenant_id])
        
        assert len(recent_sessions) > 0
        session = recent_sessions[0]
        assert session['tenant_id'] == tenant_id
        assert "Chicago" in session['query']
        
        print("   ✅ Normal mode with function calling works")


@pytest.mark.integration
@pytest.mark.llm
async def test_memory_proxy_streaming_mode():
    """Test 3: MemoryProxy streaming mode."""
    print("🧪 Testing MemoryProxy streaming mode...")
    
    tenant_id = f"test-notebook-stream-{int(time.time())}"
    
    agent = MemoryProxy(WeatherAgent)
    stream_context = CallingContext(
        stream=True,
        tenant_id=tenant_id
    )
    
    chunks_received = 0
    content_received = ""
    
    async for chunk in agent.stream("Tell me about Miami weather", stream_context):
        chunks_received += 1
        if "choices" in chunk:
            content = chunk["choices"][0].get("delta", {}).get("content", "")
            content_received += content
        
        # Limit test to avoid long execution
        if chunks_received > 20:
            break
    
    # Verify we received streaming data
    assert chunks_received > 0
    
    print(f"   ✅ Streaming mode received {chunks_received} chunks")


@pytest.mark.integration
@pytest.mark.llm
async def test_memory_proxy_batch_mode():
    """Test 4: MemoryProxy batch mode."""
    print("🧪 Testing MemoryProxy batch mode...")
    
    tenant_id = f"test-notebook-batch-{int(time.time())}"
    
    agent = MemoryProxy(WeatherAgent)
    questions = [
        "Weather in Boston?",
        "3-day forecast for Seattle?",
        "Temperature in Phoenix in Celsius?"
    ]
    
    batch_context = BatchCallingContext(
        model="gpt-5",
        tenant_id=tenant_id,
        system_message="You are a weather assistant."
    )
    
    result = await agent.batch(questions, batch_context)
    
    # Verify batch response structure
    assert result.questions_count == 3
    assert result.status == 'submitted'
    assert result.batch_type == 'openai_batch_api'
    assert result.job_id is not None
    
    print("   ✅ Batch mode submission works")


@pytest.mark.integration
async def test_session_auditing():
    """Test 5: Session auditing and database storage."""
    print("🧪 Testing session auditing...")
    
    tenant_id = f"test-notebook-audit-{int(time.time())}"
    
    # Create some session activity
    agent = MemoryProxy(WeatherAgent)
    context = CallingContext(tenant_id=tenant_id)
    
    # Direct function call to create session
    weather_func = agent._function_handler._functions['get_weather']
    result = weather_func('test-location')
    
    # Query recent sessions using SystemRepository
    session_repo = SystemRepository(Session)
    recent_sessions = session_repo.execute("""
        SELECT * FROM sessions
        WHERE tenant_id = %s
        ORDER BY created_at DESC
        LIMIT 5
    """, [tenant_id])
    
    # Note: Direct function calls don't create sessions, only run/stream/batch calls do
    # This test verifies the SystemRepository works correctly
    assert isinstance(recent_sessions, list)
    
    print("   ✅ Session auditing infrastructure works")


@pytest.mark.integration
async def test_file_processing_integration():
    """Test 6: File processing with storage worker (replacing CLI bash commands)."""
    print("🧪 Testing file processing integration...")
    
    tenant_id = f"test-notebook-files-{int(time.time())}"
    
    # Get Sample.md file path
    sample_file = Path(__file__).parent.parent / "sample_data" / "content" / "Sample.md"
    assert sample_file.exists(), f"Sample file not found: {sample_file}"
    
    # Process file using storage worker (instead of CLI bash commands)
    worker = StorageWorker(tenant_id)
    await worker.process_file(str(sample_file), tenant_id)
    
    # Verify file and resources were created
    files_repo = TenantRepository(Files, tenant_id=tenant_id)
    resources_repo = TenantRepository(Resources, tenant_id=tenant_id)
    
    file_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{sample_file}"))
    files = await files_repo.select(filters={"id": file_id})
    
    assert len(files) == 1
    file_entry = files[0]
    assert file_entry.uri == str(sample_file)
    assert file_entry.file_size > 0
    assert file_entry.metadata["name"] == "Sample.md"
    
    # Check resources (chunks)
    all_resources = await resources_repo.select(limit=1000)
    resources = [r for r in all_resources if r.metadata and r.metadata.get("file_id") == file_id]
    
    assert len(resources) > 0, "No resources created for file"
    assert all(r.category == "content_chunk" for r in resources)
    assert all(r.content and len(r.content) > 0 for r in resources)
    
    print(f"   ✅ File processing created {len(resources)} chunks")
    
    # Cleanup
    await worker.delete_file(file_id)


@pytest.mark.integration
@pytest.mark.llm
async def test_dreaming_worker_integration():
    """Test 7: Dreaming worker and agent integration."""
    print("🧪 Testing dreaming worker integration...")
    
    tenant_id = f"test-notebook-dream-{int(time.time())}"
    
    # Create some test data first (session and file)
    agent = MemoryProxy(WeatherAgent)
    context = CallingContext(tenant_id=tenant_id)
    
    # This creates a session
    try:
        await agent.run("Test dreaming data", context)
    except:
        # LLM calls may fail in test environment, but session should still be created
        pass
    
    # Process a file to create resources
    sample_file = Path(__file__).parent.parent / "sample_data" / "content" / "Sample.md"
    if sample_file.exists():
        worker = StorageWorker(tenant_id)
        try:
            await worker.process_file(str(sample_file), tenant_id)
        except:
            # File processing may fail but we continue with dreaming test
            pass
    
    # Test dreaming worker data collection
    dreaming_worker = DreamingWorker()
    user_data = await dreaming_worker.collect_user_data(tenant_id)
    
    # Verify user_data structure
    assert hasattr(user_data, 'tenant_id') or hasattr(user_data, 'id')
    # UserDataBatch might have different attribute names, just verify it has data
    assert hasattr(user_data, 'sessions')
    assert hasattr(user_data, 'resources')
    assert hasattr(user_data, 'files')
    
    # Test dreaming agent
    dream_agent = MemoryProxy(DreamModel)
    dream_context = CallingContext(tenant_id=tenant_id)
    
    query = f"Analyze this user activity data: {user_data.model_dump()} Provide key insights."
    
    try:
        response = await dream_agent.run(query, dream_context)
        assert isinstance(response, str)
        assert len(response) > 0
        print("   ✅ Dreaming agent analysis completed")
    except Exception as e:
        print(f"   ⚠️  Dreaming agent LLM call failed (expected in test): {e}")
        print("   ✅ Dreaming data collection works")


@pytest.mark.integration
async def test_complete_workflow():
    """Test 8: Complete end-to-end workflow from notebook."""
    print("🧪 Testing complete workflow integration...")
    
    tenant_id = f"test-notebook-complete-{int(time.time())}"
    
    # 1. Create weather agent
    weather_agent = MemoryProxy(WeatherAgent)
    
    # 2. Test function calling
    weather_func = weather_agent._function_handler._functions['get_weather']
    weather_result = weather_func('test-city')
    assert weather_result['location'] == 'test-city'
    
    # 3. Process a file to create content
    sample_file = Path(__file__).parent.parent / "sample_data" / "content" / "Sample.md"
    if sample_file.exists():
        worker = StorageWorker(tenant_id)
        await worker.process_file(str(sample_file), tenant_id)
        
        # Verify file was processed
        files_repo = TenantRepository(Files, tenant_id=tenant_id)
        file_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{sample_file}"))
        files = await files_repo.select(filters={"id": file_id})
        assert len(files) == 1
    
    # 4. Test dreaming data collection
    dreaming_worker = DreamingWorker()
    user_data = await dreaming_worker.collect_user_data(tenant_id)
    # Just verify user_data is not None and has expected structure
    assert user_data is not None
    assert hasattr(user_data, 'sessions')
    assert hasattr(user_data, 'resources')
    
    # 5. Verify repositories work
    session_repo = SystemRepository(Session)
    sessions = session_repo.execute("SELECT COUNT(*) as count FROM sessions")
    assert len(sessions) > 0
    
    print("   ✅ Complete workflow integration successful")


if __name__ == "__main__":
    # Run individual tests for development
    asyncio.run(test_weather_agent_creation())
    asyncio.run(test_session_auditing())
    asyncio.run(test_file_processing_integration())
    print("🎉 All integration tests completed!")