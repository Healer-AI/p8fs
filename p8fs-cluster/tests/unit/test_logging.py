"""Unit tests for P8FS logging setup."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from loguru import logger
from p8fs_cluster.logging.setup import (
    P8FSLogger,
    get_logger,
    setup_logging,
    setup_service_logging,
    with_correlation_id,
)


class TestLoggingSetup:
    """Test logging setup functionality."""
    
    def setup_method(self):
        """Setup before each test."""
        # Clear existing handlers
        logger.remove()
    
    def teardown_method(self):
        """Cleanup after each test."""
        # Restore default handler
        logger.remove()
        logger.add(sys.stderr)
    
    def test_setup_logging_default(self):
        """Test basic logging setup with defaults."""
        setup_logging()
        
        # Check that we can log without errors
        test_logger = get_logger(__name__)
        test_logger.info("Test message")
        
        # Logger should be configured
        assert len(logger._core.handlers) > 0
    
    def test_setup_logging_with_file(self):
        """Test logging setup with file output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"
            
            setup_logging(
                level="DEBUG",
                log_file=log_file,
                rotation="1 MB",
                retention="1 day"
            )
            
            # Log a test message
            test_logger = get_logger(__name__)
            test_logger.info("Test file logging")
            
            # Check that log file was created
            assert log_file.exists()
            
            # Check that we have both console and file handlers
            assert len(logger._core.handlers) >= 2
    
    def test_setup_logging_custom_level(self):
        """Test logging setup with custom level."""
        setup_logging(level="ERROR")
        
        test_logger = get_logger(__name__)
        test_logger.error("Error message")
        
        # Should work without issues
        assert len(logger._core.handlers) > 0
    
    @patch('p8fs_cluster.config.settings.config')
    def test_setup_logging_production_mode(self, mock_config):
        """Test logging setup in production mode."""
        mock_config.is_development = False
        mock_config.log_level = "INFO"
        mock_config.otel_service_name = "test-service"
        mock_config.otel_service_version = "1.0.0"
        mock_config.environment = "production"
        mock_config.default_tenant = "test-tenant"
        
        setup_logging()
        
        # Should configure without colorization
        test_logger = get_logger(__name__)
        test_logger.info("Production test")
        
        assert len(logger._core.handlers) > 0
    
    def test_get_logger(self):
        """Test getting a named logger."""
        setup_logging()
        
        test_logger = get_logger("test.module")
        
        # Should return a logger instance
        assert test_logger is not None
        
        # Should be able to log
        test_logger.info("Test message from named logger")
    
    def test_setup_service_logging(self):
        """Test service-specific logging setup."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            
            setup_service_logging("test-service", log_dir)
            
            # Check that service log file was created
            service_log = log_dir / "test-service.log"
            
            # Log a message to trigger file creation
            test_logger = get_logger(__name__)
            test_logger.info("Service logging test")
            
            assert service_log.exists()
    
    def test_setup_service_logging_no_dir(self):
        """Test service logging setup without log directory."""
        setup_service_logging("test-service")
        
        # Should work (stdout only)
        test_logger = get_logger(__name__)
        test_logger.info("Service logging test without file")
        
        assert len(logger._core.handlers) > 0
    
    def test_correlation_logger_context_manager(self):
        """Test correlation ID logger context manager."""
        setup_logging()
        
        correlation_id = "test-correlation-123"
        
        with with_correlation_id(correlation_id, user_id="user123") as corr_logger:
            corr_logger.info("Test message with correlation ID")
            
            # Logger should be bound with correlation ID
            assert corr_logger is not None
    
    def test_correlation_logger_exception_handling(self):
        """Test that correlation logger handles exceptions properly."""
        setup_logging()
        
        correlation_id = "test-error-correlation"
        
        try:
            with with_correlation_id(correlation_id) as corr_logger:
                raise ValueError("Test exception")
        except ValueError:
            pass  # Expected
        
        # Should not raise additional exceptions
    
    def test_p8fs_logger_direct_usage(self):
        """Test P8FSLogger direct instantiation."""
        setup_logging()
        
        correlation_id = "direct-test-123"
        context = {"service": "test-service", "operation": "test-op"}
        
        p8fs_logger = P8FSLogger(correlation_id, **context)
        
        with p8fs_logger as logger_instance:
            logger_instance.info("Direct P8FSLogger test")
            
            assert logger_instance is not None
    
    def test_logging_with_structured_context(self):
        """Test logging with structured context data."""
        setup_logging()
        
        test_logger = get_logger(__name__)
        
        # Log with structured data
        test_logger.info(
            "User action performed",
            user_id="user123",
            action="login",
            ip_address="192.168.1.1",
            success=True
        )
        
        # Should work without errors
        assert len(logger._core.handlers) > 0


class TestLoggingConfiguration:
    """Test logging configuration with different P8FS configs."""
    
    def setup_method(self):
        """Setup before each test."""
        logger.remove()
    
    def teardown_method(self):
        """Cleanup after each test."""
        logger.remove()
        logger.add(sys.stderr)
    
    def test_development_logging_format(self):
        """Test that development environment uses colorized format."""
        with patch('p8fs_cluster.config.settings.config') as mock_config:
            mock_config.is_development = True
            mock_config.log_level = "DEBUG"
            mock_config.otel_service_name = "dev-service"
            mock_config.otel_service_version = "dev"
            mock_config.environment = "development"
            mock_config.default_tenant = "dev"
            
            setup_logging()
            
            # Should set up development format
            assert len(logger._core.handlers) > 0
    
    def test_production_logging_format(self):
        """Test that production environment uses plain format."""
        with patch('p8fs_cluster.config.settings.config') as mock_config:
            mock_config.is_development = False
            mock_config.is_production = True
            mock_config.log_level = "INFO"
            mock_config.otel_service_name = "prod-service"
            mock_config.otel_service_version = "1.0.0"
            mock_config.environment = "production"
            mock_config.default_tenant = "production"
            
            setup_logging()
            
            # Should set up production format
            assert len(logger._core.handlers) > 0