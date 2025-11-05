# P8FS Queue Workers Implementation Plan

## Overview

The queue workers coordinate storage event processing using NATS JetStream. This module implements the tiered queue architecture that routes storage events based on file size and manages worker scaling through KEDA.

## Architecture

```
SeaweedFS Events → Tiered Router → Size-Based Queues → Storage Workers
```

### Components

1. **NATS Service** (`/p8fs/services/nats/`)
   - JetStream client with pull subscription support
   - Stream and consumer management
   - Connection handling and health monitoring

2. **Tiered Storage Router** (`tiered_router.py`)
   - Routes events from main queue to size-specific queues
   - File size classification: SMALL (0-100MB), MEDIUM (100MB-1GB), LARGE (1GB+)
   - Fail-hard design with comprehensive error handling

3. **Storage Event Worker** (`storage_worker.py`)
   - Processes individual file events from size-specific queues
   - Creates Files/Resources entries using existing storage workers
   - Integrates with content providers for text extraction

4. **Queue Configuration** (`config.py`)
   - Stream and consumer definitions
   - Size thresholds and routing logic
   - KEDA scaling parameters

## Queue Structure

### Streams and Subjects
- **Main Stream**: `P8FS_STORAGE_EVENTS` (`p8fs.storage.events`)
- **Small Queue**: `P8FS_STORAGE_EVENTS_SMALL` (`p8fs.storage.events.small`)
- **Medium Queue**: `P8FS_STORAGE_EVENTS_MEDIUM` (`p8fs.storage.events.medium`)
- **Large Queue**: `P8FS_STORAGE_EVENTS_LARGE` (`p8fs.storage.events.large`)

### Consumer Groups
- **Durable Names**: `small-workers`, `medium-workers`, `large-workers`
- **ACK Policy**: Explicit acknowledgment required
- **Retry Logic**: 3 attempts with exponential backoff

## Implementation Tasks

### Phase 1: Core Infrastructure
1. ✅ **NATS Service Implementation**
   - JetStream client with stream/consumer management
   - Pull subscription utilities
   - Connection handling and reconnection logic

2. ✅ **Queue Configuration**
   - Stream definitions with retention policies
   - Consumer configurations with appropriate timeouts
   - Size thresholds and routing constants

### Phase 2: Queue Management
3. ✅ **Tiered Storage Router**
   - Main queue consumer that routes to size-specific queues
   - File size classification and routing logic
   - Error handling and stale consumer cleanup

4. ✅ **Storage Event Worker**
   - Size-specific queue consumers
   - Integration with existing storage workers from parent module
   - Event validation and processing pipeline

### Phase 3: Integration and Testing
5. ✅ **Integration Tests**
   - End-to-end queue processing tests
   - KEDA scaling validation
   - Error recovery and retry testing

6. ✅ **Documentation and Examples**
   - CLI tools for queue management
   - Development and deployment guides

## Configuration Integration

All configuration uses the centralized `p8fs_cluster.config.settings` system:

```python
from p8fs_cluster.config.settings import config

# NATS connection from centralized config
nats_url = config.nats_url
# Database connections from centralized config  
pg_connection = config.pg_connection_string
```

## Key Design Principles

1. **Centralized Configuration**: All settings from `p8fs_cluster.config.settings`
2. **Fail-Hard Design**: Explicit error handling, no silent failures
3. **Separation of Concerns**: Router, workers, and NATS service are independent
4. **Lean Implementation**: Minimal code, maximum reliability
5. **Existing Worker Integration**: Wraps existing storage workers, doesn't reimplement

## Files Structure

```
p8fs/src/p8fs/
├── services/nats/
│   ├── __init__.py
│   ├── client.py          # JetStream client
│   ├── streams.py         # Stream management
│   └── consumers.py       # Consumer utilities
└── workers/queues/
    ├── __init__.py
    ├── config.py          # Queue configuration
    ├── tiered_router.py   # Main → size-specific routing
    ├── storage_worker.py  # Size-specific event processing
    └── cli.py            # Management tools
```

## Reference Implementation

Based on proven architecture from previous implementations:
- **Router**: `workers/tiered_storage_router.py`
- **Worker**: `workers/storage_event_worker.py`  
- **NATS Client**: `services/nats/client.py`

Refactored to use centralized configuration and lean design principles.
