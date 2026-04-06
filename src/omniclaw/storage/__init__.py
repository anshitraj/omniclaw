"""
Storage backends for OmniClaw.

Provides pluggable persistence for ledger, guards, and other stateful components.

Configuration via environment:
    OMNICLAW_STORAGE_BACKEND=file  # 'file', 'memory', or 'redis'
    OMNICLAW_REDIS_URL=redis://localhost:6379/0
    OMNICLAW_STORAGE_DIR=~/.omniclaw/data  # for file storage

Example:
    >>> from omniclaw.storage import get_storage, InMemoryStorage, RedisStorage, FileStorage
    >>>
    >>> # Get storage from environment
    >>> storage = get_storage()
    >>>
    >>> # Or create specific backend
    >>> storage = FileStorage()
    >>> storage = InMemoryStorage()
    >>> storage = RedisStorage(redis_url="redis://localhost:6379")
"""

from __future__ import annotations

import os

from omniclaw.storage.base import (
    StorageBackend,
    get_storage_backend,
    list_storage_backends,
    register_storage_backend,
)
from omniclaw.storage.memory import InMemoryStorage

# Import Redis storage to register it (optional dependency)
try:
    from omniclaw.storage.redis import RedisStorage
except ImportError:
    RedisStorage = None  # type: ignore

# Import and register FileStorage
from omniclaw.storage.file import FileStorage

register_storage_backend("file", FileStorage)


def get_storage(backend_name: str | None = None) -> StorageBackend:
    """
    Get storage backend from environment or by name.

    Args:
        backend_name: Backend name, or None to read from OMNICLAW_STORAGE_BACKEND env

    Returns:
        StorageBackend instance

    Raises:
        ValueError: If backend name is unknown

    Warning:
        Using 'memory' backend in production will lose all state on process restart.
        For production, use 'redis' backend: OMNICLAW_STORAGE_BACKEND=redis
    """
    import warnings

    if backend_name is None:
        backend_name = os.environ.get("OMNICLAW_STORAGE_BACKEND", "file")

    backend_class = get_storage_backend(backend_name)

    if backend_class is None:
        available = list_storage_backends()
        raise ValueError(
            f"Unknown storage backend: '{backend_name}'. Available: {', '.join(available)}"
        )

    # Warn about memory storage in production
    if backend_name == "memory":
        env = os.environ.get("OMNICLAW_ENV", "").lower()
        if env in ("production", "prod", "mainnet"):
            raise ValueError(
                "CRITICAL: Cannot use memory storage backend in production. "
                "All state will be lost on process restart, causing budget bypass and fund loss. "
                "Use Redis: OMNICLAW_STORAGE_BACKEND=redis OMNICLAW_REDIS_URL=redis://..."
            )
        elif env not in ("", "test", "development", "dev"):
            warnings.warn(
                f"Using memory storage with OMNICLAW_ENV={env}. "
                "For production use, configure Redis: OMNICLAW_STORAGE_BACKEND=redis",
                UserWarning,
                stacklevel=2,
            )

    return backend_class()


__all__ = [
    "StorageBackend",
    "InMemoryStorage",
    "FileStorage",
    "RedisStorage",
    "get_storage",
    "get_storage_backend",
    "list_storage_backends",
    "register_storage_backend",
]
