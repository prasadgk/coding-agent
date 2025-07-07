"""Repository management module for efficient workspace handling.

This module provides optimized repository management with features including:
- Repository pooling and reuse
- Concurrent access with locking mechanisms
- Automatic cleanup and maintenance
- Health monitoring and recovery
- Configurable retention policies
"""

from .models import RepositoryInfo, RepositoryWorkspace, RepositoryStatus
from .pool import RepositoryPool
from .manager import RepositoryManager
from .cleaner import RepositoryCleaner
from .monitor import RepositoryHealthMonitor

__all__ = [
    'RepositoryInfo',
    'RepositoryWorkspace',
    'RepositoryStatus',
    'RepositoryPool',
    'RepositoryManager',
    'RepositoryCleaner',
    'RepositoryHealthMonitor',
]