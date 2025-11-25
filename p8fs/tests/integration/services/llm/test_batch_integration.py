"""Integration tests for P8FS batch processing with real OpenAI API calls."""

import json
import os
from pathlib import Path

import pytest

from p8fs.models.base import AbstractModel
from p8fs.services.llm import MemoryProxy
from p8fs.services.llm.models import BatchCallingContext


class SampleBatchAgent(AbstractModel):
    """Test agent for batch processing integration tests."""
    
    async def analyze_data(self, data: str, format: str = "summary") -> dict:
        """Analyze data and return structured results."""
        return {
            "data": data,
            "format": format,
            "analysis_type": "mock_analysis",
            "status": "processed"
        }


@pytest.mark.llm
class TestBatchIntegration:
    """Integration tests for batch processing functionality."""

    def load_sample_data(self):
        """Load sample data for testing."""
        current_dir = Path(__file__).parent
        sample_file = current_dir.parent.parent.parent / "sample_data" / "llm_requests" / "openai_requests.json"
        
        with open(sample_file, 'r') as f:
            return json.load(f)

    def load_expected_responses(self):
        """Load expected response patterns for validation."""
        current_dir = Path(__file__).parent
        response_file = current_dir.parent.parent.parent / "sample_data" / "llm_responses" / "openai_responses.json"
        
        with open(response_file, 'r') as f:
            return json.load(f)

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_gpt4_batch_submission(self):
        """Test GPT-4 batch job submission with sample data patterns."""
        # Load sample data patterns
        sample_data = self.load_sample_data()
        expected_responses = self.load_expected_responses()
        
        # Initialize memory proxy with test agent
        memory_proxy = MemoryProxy(SampleBatchAgent)
        tenant_id = "integration-test-batch"
        
        # Create batch context using sample data patterns
        batch_context = BatchCallingContext(
            model="gpt-4o",
            tenant_id=tenant_id,
            batch_size=3,
            batch_timeout=3600,
            batch_priority="standard",
            temperature=sample_data["basic_chat"]["temperature"],
            max_tokens=sample_data["basic_chat"]["max_tokens"],
            system_message="You are a helpful assistant."
        )
        
        # Use questions based on sample data
        questions = [
            sample_data["basic_chat"]["messages"][0]["content"],
            sample_data["system_message"]["messages"][1]["content"],
            sample_data["batch_item"]["body"]["messages"][0]["content"]
        ]
        
        # Submit the batch job
        batch_response = await memory_proxy.batch(questions, batch_context)
        
        # Verify response structure matches expected pattern
        expected_batch_response = expected_responses["batch_submission_response"]
        
        assert batch_response is not None
        assert hasattr(batch_response, 'batch_id')
        assert hasattr(batch_response, 'status')
        assert hasattr(batch_response, 'job_id')
        assert hasattr(batch_response, 'questions_count')
        
        # Verify response data
        response_dict = batch_response.model_dump() if hasattr(batch_response, 'model_dump') else batch_response
        
        assert response_dict["batch_type"] == expected_batch_response["batch_type"]
        assert response_dict["status"] == expected_batch_response["status"]
        assert response_dict["questions_count"] == len(questions)
        assert response_dict["cost_savings"] == expected_batch_response["cost_savings"]
        assert "batch_id" in response_dict
        assert "job_id" in response_dict
        assert "submitted_at" in response_dict

    @pytest.mark.integration
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available")
    @pytest.mark.llm
    async def test_gpt5_batch_submission_with_reasoning(self):
        """Test GPT-5 batch job submission with reasoning parameters."""
        sample_data = self.load_sample_data()
        expected_responses = self.load_expected_responses()
        
        # Initialize memory proxy
        memory_proxy = MemoryProxy(SampleBatchAgent)
        tenant_id = "integration-test-gpt5-batch"
        
        # Create batch context with GPT-5 reasoning parameters
        batch_context = BatchCallingContext(
            model="gpt-4o",  # Using GPT-4 as GPT-5 proxy
            tenant_id=tenant_id,
            batch_size=2,
            batch_timeout=7200,
            batch_priority="high",
            temperature=0.3,
            max_completion_tokens=sample_data["gpt5_request"]["max_completion_tokens"],
            reasoning_effort=sample_data["gpt5_request"]["reasoning_effort"],
            verbosity=sample_data["gpt5_request"]["verbosity"],
            system_message="You are an advanced AI that provides detailed, well-reasoned responses."
        )
        
        # Complex questions for reasoning test
        questions = [
            sample_data["gpt5_request"]["messages"][0]["content"],
            "Explain the philosophical implications of artificial intelligence consciousness and its impact on human identity."
        ]
        
        # Submit the batch job
        batch_response = await memory_proxy.batch(questions, batch_context)
        
        # Verify response structure
        expected_batch_response = expected_responses["batch_submission_gpt5_response"]
        
        assert batch_response is not None
        response_dict = batch_response.model_dump() if hasattr(batch_response, 'model_dump') else batch_response
        
        assert response_dict["batch_type"] == expected_batch_response["batch_type"]
        assert response_dict["status"] == expected_batch_response["status"]
        assert response_dict["questions_count"] == len(questions)
        assert response_dict["cost_savings"] == expected_batch_response["cost_savings"]

    @pytest.mark.integration
    @pytest.mark.llm
    async def test_batch_job_creation_without_api_call(self):
        """Test batch job creation and database persistence without API calls."""
        from p8fs.models.p8 import Job
        from p8fs.repository import TenantRepository
        
        # Create batch context
        batch_context = BatchCallingContext(
            model="gpt-4o",
            tenant_id="test-tenant",
            batch_size=2,
            temperature=0.7
        )
        
        # Create batch job
        questions = ["What is AI?", "How does machine learning work?"]
        job = Job.create_batch_job(questions, batch_context, tenant_id="test-tenant")
        
        # Verify job structure
        assert job.job_type == "batch_completion"
        assert job.status == "pending"
        assert job.is_batch is True
        assert job.batch_size == len(questions)
        assert job.payload["questions"] == questions
        assert job.payload["model"] == "gpt-4o"
        
        # Test database persistence - upsert should succeed without errors
        jobs_repo = TenantRepository(Job, "test-tenant")
        saved_job = await jobs_repo.upsert(job)
        
        # Verify upsert completed successfully (no exceptions thrown)
        assert saved_job is not None

    @pytest.mark.integration
    @pytest.mark.llm
    async def test_sample_data_consistency(self):
        """Test that sample data is consistent and properly structured."""
        sample_requests = self.load_sample_data()
        sample_responses = self.load_expected_responses()
        
        # Verify request data structure
        assert "batch_item" in sample_requests
        assert "basic_chat" in sample_requests
        assert "gpt5_request" in sample_requests
        
        batch_item = sample_requests["batch_item"]
        assert batch_item["method"] == "POST"
        assert batch_item["url"] == "/v1/chat/completions"
        assert "model" in batch_item["body"]
        assert "messages" in batch_item["body"]
        
        # Verify response data structure
        assert "batch_submission_response" in sample_responses
        assert "batch_submission_gpt5_response" in sample_responses
        
        batch_response = sample_responses["batch_submission_response"]
        assert "batch_id" in batch_response
        assert "batch_type" in batch_response
        assert "status" in batch_response
        assert "questions_count" in batch_response
        assert "cost_savings" in batch_response
        
        gpt5_response = sample_responses["batch_submission_gpt5_response"]
        assert "reasoning_effort" not in gpt5_response  # Should be in context, not response
        assert gpt5_response["questions_count"] == 2

    @pytest.mark.integration
    @pytest.mark.llm
    async def test_batch_agent_functions(self):
        """Test that batch agents properly register and execute functions."""
        memory_proxy = MemoryProxy(SampleBatchAgent)
        
        # Verify function registration
        function_handler = memory_proxy._function_handler
        assert function_handler is not None
        
        # Check that our test function is registered
        schemas = function_handler.get_schemas()
        function_names = [schema["function"]["name"] for schema in schemas]
        assert "analyze_data" in function_names
        
        # Test function execution - use private attribute _functions
        analyze_func = None
        for func in function_handler._functions.values():
            if hasattr(func, 'fn') and func.fn.__name__ == 'analyze_data':
                analyze_func = func
                break
        
        assert analyze_func is not None
        
        # Execute the function
        result = await analyze_func(data="test data", format="detailed")
        assert result["data"] == "test data"
        assert result["format"] == "detailed"
        assert result["analysis_type"] == "mock_analysis"
        assert result["status"] == "processed"