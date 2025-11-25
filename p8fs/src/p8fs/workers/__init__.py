"""P8FS Workers for content processing and analysis."""

def __getattr__(name):
    """Lazy import to avoid module loading conflicts when running as __main__."""
    if name == "DreamingWorker":
        from .dreaming import DreamingWorker
        return DreamingWorker
    elif name == "StorageWorker":
        from .storage import StorageWorker
        return StorageWorker
    elif name == "ChunkStorageWorker":
        from .storage_chunks import StorageWorker as ChunkStorageWorker
        return ChunkStorageWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["StorageWorker", "DreamingWorker", "ChunkStorageWorker"]