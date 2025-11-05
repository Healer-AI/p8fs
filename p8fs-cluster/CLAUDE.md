# P8FS Cluster Module

## Module Overview

The P8FS Cluster module provides centralized configuration and runtime management for cluster deployments. It serves as the single source of truth for all system configuration, logging infrastructure, and environment management across the entire P8FS ecosystem.

## Architecture

### Core Components

- **Centralized Configuration System**: Single source of truth for all settings
- **Logging Infrastructure**: Shared logging setup across all modules
- **Environment Variable Management**: Unified environment handling
- **Cluster Coordination Utilities**: Tools for multi-node deployments

### Key Features

- Single configuration import for all modules
- Computed properties for connection strings
- Environment-based configuration overrides
- Shared logging setup and formatting

## Development Standards

### Code Quality

- Write minimal, efficient code with clear intent
- Avoid workarounds; implement proper solutions
- Prioritize maintainability over quick fixes
- Keep implementations lean and purposeful
- No comments unless absolutely necessary for complex configuration logic

### Configuration Architecture

**CRITICAL**: All configuration must originate from `p8fs_cluster.config.settings`. This module is the single source of truth for the entire P8FS system.

#### Key Principles

1. **Single Source of Truth**: All modules import configuration from this module
2. **No Direct Environment Variables**: Individual modules never read environment variables directly
3. **Computed Properties**: Connection strings and complex settings are computed automatically
4. **Provider Neutrality**: Database providers get connection strings, not individual parameters

### Configuration Patterns

#### Settings Structure
```python
from pydantic import BaseSettings, computed_field
from typing import Optional

class P8FSConfig(BaseSettings):
    # Storage provider selection
    storage_provider: str = "postgresql"  # postgresql, tidb, rocksdb
    
    # PostgreSQL settings
    pg_host: str = "localhost"
    pg_port: int = 5438
    pg_database: str = "app"
    pg_user: str = "postgres"
    pg_password: str = "postgres"
    
    # TiDB settings
    tidb_host: str = "localhost"
    tidb_port: int = 4000
    tidb_database: str = "test"
    tidb_user: str = "root"
    tidb_password: str = ""
    
    @computed_field
    @property
    def pg_connection_string(self) -> str:
        return f"postgresql://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_database}"
    
    @computed_field
    @property
    def tidb_connection_string(self) -> str:
        return f"mysql://{self.tidb_user}:{self.tidb_password}@{self.tidb_host}:{self.tidb_port}/{self.tidb_database}"
    
    class Config:
        env_prefix = "P8FS_"
        case_sensitive = False

config = P8FSConfig()
```

#### Module Integration
```python
# ✅ CORRECT - All modules use centralized config
from p8fs_cluster.config.settings import config

# Database provider gets connection string from config
def create_database_connection():
    if config.storage_provider == "postgresql":
        return psycopg2.connect(config.pg_connection_string)
    elif config.storage_provider == "tidb":
        return pymysql.connect(config.tidb_connection_string)

# API settings from centralized config
app_host = config.api_host
app_port = config.api_port
```

```python
# ❌ WRONG - Don't read environment variables directly
import os

# Don't do this in individual modules
db_host = os.getenv("P8FS_PG_HOST")  # Wrong!
db_port = os.getenv("P8FS_PG_PORT")  # Wrong!
```

### Logging Infrastructure

#### Shared Logging Setup
```python
import logging
import sys
from p8fs_cluster.config.settings import config

class LoggingSetup:
    @staticmethod
    def configure_logging():
        logging.basicConfig(
            level=config.log_level,
            format=config.log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(config.log_file) if config.log_file else None
            ]
        )
        
        # Configure module-specific loggers
        for module in ['p8fs_api', 'p8fs', 'p8fs_node', 'p8fs_auth']:
            logger = logging.getLogger(module)
            logger.setLevel(config.log_level)
```

#### Usage in Other Modules
```python
# ✅ CORRECT - Use shared logging setup
from p8fs_cluster.logging.setup import LoggingSetup
import logging

LoggingSetup.configure_logging()
logger = logging.getLogger('p8fs_api')

logger.info("Starting API server")
```

## Testing Requirements

### Unit Tests
- Mock configuration values for specific test scenarios
- Test configuration property computation
- Validate environment variable parsing
- Test logging setup functionality

### Integration Tests
- Use real configuration (no mocking of config module)
- Test configuration inheritance across modules
- Validate complete system configuration

### Testing Approach

#### Unit Test Configuration Mocking
```python
from unittest.mock import patch
import pytest
from p8fs_cluster.config.settings import P8FSConfig

def test_connection_string_computation():
    with patch.dict(os.environ, {
        'P8FS_PG_HOST': 'testhost',
        'P8FS_PG_PORT': '5432',
        'P8FS_PG_DATABASE': 'testdb',
        'P8FS_PG_USER': 'testuser',
        'P8FS_PG_PASSWORD': 'testpass'
    }):
        config = P8FSConfig()
        expected = "postgresql://testuser:testpass@testhost:5432/testdb"
        assert config.pg_connection_string == expected
```

#### Integration Test with Real Config
```python
import pytest
from p8fs_cluster.config.settings import config

@pytest.mark.integration
def test_database_provider_integration():
    # Uses real centralized config - no mocking
    if config.storage_provider == "postgresql":
        assert "postgresql://" in config.pg_connection_string
    elif config.storage_provider == "tidb":
        assert "mysql://" in config.tidb_connection_string
```

## Environment Configuration

### Development Environment
```bash
# Set storage provider
export P8FS_STORAGE_PROVIDER=postgresql

# Database settings (automatically used by computed properties)
export P8FS_PG_HOST=localhost
export P8FS_PG_PORT=5438
export P8FS_PG_DATABASE=app

# Logging settings
export P8FS_LOG_LEVEL=INFO
export P8FS_LOG_FORMAT="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

### Production Environment
```bash
# Use TiDB in production
export P8FS_STORAGE_PROVIDER=tidb
export P8FS_TIDB_HOST=tidb-cluster.example.com
export P8FS_TIDB_PORT=4000
export P8FS_TIDB_DATABASE=production

# Security settings
export P8FS_AUTH_JWT_SECRET=secure-production-secret
export P8FS_AUTH_TOKEN_EXPIRY=3600
```

## Testing Patterns

### Test Structure
```
tests/
├── unit/
│   ├── test_config.py        # Configuration unit tests
│   └── test_logging.py       # Logging setup tests
└── integration/
    └── test_system_config.py  # Cross-module configuration tests
```

### Running Tests
```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# All tests
pytest tests/ -v
```

## Dependencies

- **pydantic**: Configuration management with validation
- **python-dotenv**: Environment file loading

## Development Workflow

1. Install dependencies:
   ```bash
   pip install pydantic python-dotenv
   ```

2. Run tests:
   ```bash
   pytest tests/ -v
   ```

3. Lint and type check:
   ```bash
   ruff check src/
   mypy src/
   ```

## Configuration Validation

Implement validation for critical configuration:

```python
from pydantic import BaseSettings, validator

class P8FSConfig(BaseSettings):
    storage_provider: str = "postgresql"
    
    @validator('storage_provider')
    def validate_storage_provider(cls, v):
        allowed = ['postgresql', 'tidb', 'rocksdb']
        if v not in allowed:
            raise ValueError(f'storage_provider must be one of {allowed}')
        return v
    
    @validator('pg_port', 'tidb_port')
    def validate_ports(cls, v):
        if not (1 <= v <= 65535):
            raise ValueError('Port must be between 1 and 65535')
        return v
```

## Error Handling

Handle configuration errors gracefully:

```python
from p8fs_cluster.config.settings import config
from p8fs_cluster.exceptions import ConfigurationError

def validate_configuration():
    try:
        # Test database connection
        if config.storage_provider == "postgresql":
            test_connection = psycopg2.connect(config.pg_connection_string)
            test_connection.close()
    except Exception as e:
        raise ConfigurationError(f"Database configuration invalid: {e}")
```

## Cluster Deployment

For Kubernetes deployments:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: p8fs-config
data:
  P8FS_STORAGE_PROVIDER: "tidb"
  P8FS_TIDB_HOST: "tidb-cluster"
  P8FS_TIDB_PORT: "4000"
  P8FS_LOG_LEVEL: "INFO"
```

## Performance Considerations

- Cache configuration objects to avoid repeated parsing
- Use lazy loading for expensive computed properties
- Implement configuration hot-reloading for development
- Validate configuration at startup, not runtime