"""Unit tests for P8FS configuration."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from p8fs_cluster.config.settings import P8FSConfig
from p8fs_cluster.utils.env import (
    get_env_bool,
    get_env_int,
    get_env_list,
    get_env_port,
    load_environment,
    parse_port,
)


class TestP8FSConfig:
    """Test P8FS configuration settings."""
    
    @patch.dict(os.environ, {}, clear=True)
    def test_default_values(self):
        """Test that default configuration values are correct."""
        config = P8FSConfig()
        
        # Application defaults
        assert config.debug is False
        assert config.environment == "development"
        assert config.log_level == "INFO"
        assert config.default_tenant_id == "tenant-test"
        
        # API defaults
        assert config.api_host == "0.0.0.0"
        assert config.api_port == 8000
        assert config.api_workers == 1
        assert config.cors_origins == ["*"]
        
        # Storage defaults
        assert config.tikv_endpoints == ["localhost:2379"]
        assert config.seaweedfs_master == "localhost:9333"
        assert config.nats_url == "nats://localhost:4222"
    
    @patch.dict(os.environ, {
        "P8FS_DEBUG": "true",
        "P8FS_ENVIRONMENT": "production",
        "P8FS_LOG_LEVEL": "DEBUG",
        "P8FS_API_PORT": "9000"
    })
    def test_environment_variables(self):
        """Test that environment variables override defaults."""
        config = P8FSConfig()
        
        assert config.debug is True
        assert config.environment == "production"
        assert config.log_level == "DEBUG"
        assert config.api_port == 9000
    
    @patch.dict(os.environ, {
        "P8FS_TIKV_ENDPOINTS": '["localhost:2379", "localhost:2380"]',
        "P8FS_CORS_ORIGINS": '["http://localhost:3000", "http://localhost:8080"]'
    })
    def test_list_environment_variables(self):
        """Test that list-type environment variables are parsed correctly."""
        config = P8FSConfig()
        
        assert config.tikv_endpoints == ["localhost:2379", "localhost:2380"]
        assert config.cors_origins == ["http://localhost:3000", "http://localhost:8080"]
    
    @patch.dict(os.environ, {
        "P8FS_API_PORT": "tcp://10.107.144.156:8080"
    }, clear=True)
    def test_kubernetes_port_format(self):
        """Test that Kubernetes port format is handled correctly."""
        config = P8FSConfig()
        
        assert config.api_port == 8080
    
    @patch.dict(os.environ, {
        "SEAWEEDFS_ACCESS_KEY": "custom_access",
        "SEAWEEDFS_SECRET_KEY": "custom_secret"
    })
    def test_compatibility_environment_variables(self):
        """Test that compatibility environment variables work."""
        config = P8FSConfig()
        
        assert config.seaweedfs_access_key == "custom_access"
        assert config.seaweedfs_secret_key == "custom_secret"
    
    def test_environment_properties(self):
        """Test environment detection properties."""
        # Development
        config = P8FSConfig(environment="development")
        assert config.is_development is True
        assert config.is_production is False
        assert config.is_testing is False
        
        # Production  
        config = P8FSConfig(environment="production")
        assert config.is_development is False
        assert config.is_production is True
        assert config.is_testing is False
        
        # Testing
        config = P8FSConfig(environment="test")
        assert config.is_development is False
        assert config.is_production is False
        assert config.is_testing is True


class TestEnvironmentUtils:
    """Test environment utility functions."""
    
    def test_get_env_list_json_format(self):
        """Test parsing JSON array environment variables."""
        with patch.dict(os.environ, {"TEST_LIST": '["a", "b", "c"]'}):
            result = get_env_list("TEST_LIST")
            assert result == ["a", "b", "c"]
    
    def test_get_env_list_csv_format(self):
        """Test parsing comma-separated environment variables."""
        with patch.dict(os.environ, {"TEST_LIST": "a,b,c"}):
            result = get_env_list("TEST_LIST")
            assert result == ["a", "b", "c"]
    
    def test_get_env_list_default(self):
        """Test default value for missing environment variable."""
        result = get_env_list("NONEXISTENT", ["default"])
        assert result == ["default"]
    
    def test_get_env_bool_truthy_values(self):
        """Test boolean parsing for truthy values."""
        truthy_values = ["true", "1", "yes", "on", "enabled", "TRUE", "True"]
        
        for value in truthy_values:
            with patch.dict(os.environ, {"TEST_BOOL": value}):
                assert get_env_bool("TEST_BOOL") is True
    
    def test_get_env_bool_falsy_values(self):
        """Test boolean parsing for falsy values."""
        falsy_values = ["false", "0", "no", "off", "disabled", "FALSE", "False", ""]
        
        for value in falsy_values:
            with patch.dict(os.environ, {"TEST_BOOL": value}):
                assert get_env_bool("TEST_BOOL") is False
    
    def test_get_env_int_valid(self):
        """Test integer parsing for valid values."""
        with patch.dict(os.environ, {"TEST_INT": "42"}):
            result = get_env_int("TEST_INT")
            assert result == 42
    
    def test_get_env_int_invalid(self):
        """Test integer parsing for invalid values."""
        with patch.dict(os.environ, {"TEST_INT": "not_a_number"}):
            result = get_env_int("TEST_INT", default=99)
            assert result == 99
    
    def test_parse_port_plain_integer(self):
        """Test port parsing for plain integer."""
        assert parse_port("8080") == 8080
    
    def test_parse_port_kubernetes_format(self):
        """Test port parsing for Kubernetes service format."""
        assert parse_port("tcp://10.107.144.156:8080") == 8080
    
    def test_parse_port_invalid(self):
        """Test port parsing for invalid formats."""
        assert parse_port("invalid", default=9000) == 9000
        assert parse_port("", default=9000) == 9000
    
    def test_get_env_port(self):
        """Test port environment variable parsing."""
        with patch.dict(os.environ, {"TEST_PORT": "tcp://127.0.0.1:3000"}):
            result = get_env_port("TEST_PORT", default=8000)
            assert result == 3000
    
    def test_load_environment_with_file(self):
        """Test loading environment from .env file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("P8FS_TEST_VAR=test_value\n")
            f.write("P8FS_TEST_NUM=123\n")
            env_file = Path(f.name)
        
        try:
            load_environment(env_file)
            assert os.getenv("P8FS_TEST_VAR") == "test_value"
            assert os.getenv("P8FS_TEST_NUM") == "123"
        finally:
            env_file.unlink()
            # Clean up environment
            os.environ.pop("P8FS_TEST_VAR", None)
            os.environ.pop("P8FS_TEST_NUM", None)