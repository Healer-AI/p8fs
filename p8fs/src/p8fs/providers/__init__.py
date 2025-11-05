"""SQL Provider classes for different database dialects."""

from .base import BaseSQLProvider
from .postgresql import PostgreSQLProvider


# Lazy imports for optional providers
def _get_tidb_provider():
    from .tidb import TiDBProvider
    return TiDBProvider

def _get_rocksdb_provider():
    from .rocksdb import RocksDBProvider
    return RocksDBProvider

# Add sql module alias for backward compatibility
class SQLModule:
    PostgreSQLProvider = PostgreSQLProvider
    
    @property
    def TiDBProvider(self):
        return _get_tidb_provider()

sql = SQLModule()

def get_provider():
    """Get the configured provider instance based on settings."""
    from p8fs_cluster.config.settings import config
    
    if config.storage_provider == "postgresql":
        return PostgreSQLProvider()
    elif config.storage_provider == "tidb":
        TiDBProvider = _get_tidb_provider()
        return TiDBProvider()
    elif config.storage_provider == "rocksdb":
        RocksDBProvider = _get_rocksdb_provider()
        return RocksDBProvider()
    else:
        # Default to PostgreSQL
        return PostgreSQLProvider()


__all__ = [
    "BaseSQLProvider",
    "PostgreSQLProvider",
    "TiDBProvider", 
    "RocksDBProvider",
    "sql",
    "get_provider",
]

# Make TiDB and RocksDB available for direct import but lazy-loaded
def __getattr__(name):
    if name == "TiDBProvider":
        return _get_tidb_provider()
    elif name == "RocksDBProvider":
        return _get_rocksdb_provider()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")