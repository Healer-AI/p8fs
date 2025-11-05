"""Tests for queue configuration."""

import pytest
pytest.skip("Queue module dependencies not available", allow_module_level=True)

from p8fs.workers.queues.config import (
    ConsumerNames,
    KEDAScalingConfig,
    QueueSize,
    QueueSubjects,
    QueueThresholds,
    RouterConfig,
    StreamNames,
    WorkerConfig,
)


class TestQueueThresholds:
    """Test queue size classification."""
    
    def test_small_file_classification(self):
        """Test small file size classification."""
        # 1MB file
        size = QueueThresholds.get_queue_size(1024 * 1024)
        assert size == QueueSize.SMALL
        
        # Exactly at threshold
        size = QueueThresholds.get_queue_size(QueueThresholds.SMALL_MAX)
        assert size == QueueSize.SMALL
        
    def test_medium_file_classification(self):
        """Test medium file size classification."""
        # 500MB file
        size = QueueThresholds.get_queue_size(500 * 1024 * 1024)
        assert size == QueueSize.MEDIUM
        
        # Exactly at threshold
        size = QueueThresholds.get_queue_size(QueueThresholds.MEDIUM_MAX)
        assert size == QueueSize.MEDIUM
        
    def test_large_file_classification(self):
        """Test large file size classification."""
        # 2GB file
        size = QueueThresholds.get_queue_size(2 * 1024 * 1024 * 1024)
        assert size == QueueSize.LARGE
        
        # Just over medium threshold
        size = QueueThresholds.get_queue_size(QueueThresholds.MEDIUM_MAX + 1)
        assert size == QueueSize.LARGE


class TestQueueSubjects:
    """Test NATS subject mappings."""
    
    def test_subject_mapping(self):
        """Test queue size to subject mapping."""
        assert QueueSubjects.get_subject_for_size(QueueSize.SMALL) == "p8fs.storage.events.small"
        assert QueueSubjects.get_subject_for_size(QueueSize.MEDIUM) == "p8fs.storage.events.medium"
        assert QueueSubjects.get_subject_for_size(QueueSize.LARGE) == "p8fs.storage.events.large"
        
    def test_all_sizes_have_subjects(self):
        """Test that all queue sizes have corresponding subjects."""
        for size in QueueSize:
            subject = QueueSubjects.get_subject_for_size(size)
            assert subject.startswith("p8fs.storage.events.")
            assert subject.endswith(size.value)


class TestStreamNames:
    """Test stream name mappings."""
    
    def test_stream_mapping(self):
        """Test queue size to stream mapping."""
        assert StreamNames.get_stream_for_size(QueueSize.SMALL) == "P8FS_STORAGE_EVENTS_SMALL"
        assert StreamNames.get_stream_for_size(QueueSize.MEDIUM) == "P8FS_STORAGE_EVENTS_MEDIUM"
        assert StreamNames.get_stream_for_size(QueueSize.LARGE) == "P8FS_STORAGE_EVENTS_LARGE"
        
    def test_all_sizes_have_streams(self):
        """Test that all queue sizes have corresponding streams."""
        for size in QueueSize:
            stream = StreamNames.get_stream_for_size(size)
            assert stream.startswith("P8FS_STORAGE_EVENTS_")
            assert stream.endswith(size.value.upper())


class TestConsumerNames:
    """Test consumer name mappings."""
    
    def test_consumer_mapping(self):
        """Test queue size to consumer mapping."""
        assert ConsumerNames.get_consumer_for_size(QueueSize.SMALL) == "small-workers"
        assert ConsumerNames.get_consumer_for_size(QueueSize.MEDIUM) == "medium-workers"
        assert ConsumerNames.get_consumer_for_size(QueueSize.LARGE) == "large-workers"
        
    def test_all_sizes_have_consumers(self):
        """Test that all queue sizes have corresponding consumers."""
        for size in QueueSize:
            consumer = ConsumerNames.get_consumer_for_size(size)
            assert consumer.endswith("-workers")
            assert size.value in consumer


class TestWorkerConfig:
    """Test worker configuration."""
    
    def test_config_for_all_sizes(self):
        """Test that all queue sizes have configurations."""
        for size in QueueSize:
            config = WorkerConfig.get_config_for_size(size)
            assert "timeout" in config
            assert "batch_size" in config
            assert "max_ack_pending" in config
            assert "max_deliver" in config
            
    def test_timeout_increases_with_size(self):
        """Test that timeout increases with file size."""
        small_config = WorkerConfig.get_config_for_size(QueueSize.SMALL)
        medium_config = WorkerConfig.get_config_for_size(QueueSize.MEDIUM)
        large_config = WorkerConfig.get_config_for_size(QueueSize.LARGE)
        
        assert small_config["timeout"] < medium_config["timeout"]
        assert medium_config["timeout"] < large_config["timeout"]
        
    def test_batch_size_decreases_with_size(self):
        """Test that batch size decreases with file size."""
        small_config = WorkerConfig.get_config_for_size(QueueSize.SMALL)
        medium_config = WorkerConfig.get_config_for_size(QueueSize.MEDIUM)
        large_config = WorkerConfig.get_config_for_size(QueueSize.LARGE)
        
        assert small_config["batch_size"] > medium_config["batch_size"]
        assert medium_config["batch_size"] > large_config["batch_size"]


class TestKEDAScalingConfig:
    """Test KEDA scaling configuration."""
    
    def test_scaling_config_for_all_sizes(self):
        """Test that all queue sizes have scaling configurations."""
        for size in QueueSize:
            config = KEDAScalingConfig.get_scaling_config(size)
            assert "min_replicas" in config
            assert "max_replicas" in config
            assert "messages_per_replica" in config
            assert "cooldown_period" in config
            
    def test_max_replicas_decreases_with_size(self):
        """Test that max replicas decreases with file size."""
        small_config = KEDAScalingConfig.get_scaling_config(QueueSize.SMALL)
        medium_config = KEDAScalingConfig.get_scaling_config(QueueSize.MEDIUM)
        large_config = KEDAScalingConfig.get_scaling_config(QueueSize.LARGE)
        
        assert small_config["max_replicas"] > medium_config["max_replicas"]
        assert medium_config["max_replicas"] > large_config["max_replicas"]
        
    def test_cooldown_increases_with_size(self):
        """Test that cooldown period increases with file size."""
        small_config = KEDAScalingConfig.get_scaling_config(QueueSize.SMALL)
        medium_config = KEDAScalingConfig.get_scaling_config(QueueSize.MEDIUM)
        large_config = KEDAScalingConfig.get_scaling_config(QueueSize.LARGE)
        
        assert small_config["cooldown_period"] < medium_config["cooldown_period"]
        assert medium_config["cooldown_period"] < large_config["cooldown_period"]


class TestRouterConfig:
    """Test router configuration constants."""
    
    def test_constants_are_reasonable(self):
        """Test that router constants have reasonable values."""
        assert RouterConfig.FETCH_TIMEOUT > 0
        assert RouterConfig.MAX_CONSECUTIVE_ERRORS > 0
        assert RouterConfig.ACK_WAIT_SECONDS > 0
        assert RouterConfig.MAX_DELIVER > 0
        assert RouterConfig.BATCH_SIZE > 0