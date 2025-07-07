"""Data models for repository management system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set
import uuid


class RepositoryStatus(Enum):
    """Status of a repository in the pool."""
    AVAILABLE = "available"
    IN_USE = "in_use"
    UPDATING = "updating"
    CLONING = "cloning"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    SCHEDULED_FOR_CLEANUP = "scheduled_for_cleanup"


class BranchStatus(Enum):
    """Status of a branch workspace."""
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


@dataclass
class RepositoryInfo:
    """Information about a repository in the pool."""
    repository_url: str
    repository_key: str  # Normalized URL for consistent identification
    local_path: Path
    status: RepositoryStatus
    last_accessed: datetime
    last_updated: datetime
    clone_date: datetime
    size_bytes: int
    active_branches: Set[str] = field(default_factory=set)
    error_count: int = 0
    last_error: Optional[str] = None
    metadata: Dict[str, any] = field(default_factory=dict)
    
    @property
    def is_available(self) -> bool:
        """Check if repository is available for use."""
        return self.status == RepositoryStatus.AVAILABLE
    
    @property
    def age_hours(self) -> float:
        """Get age of repository clone in hours."""
        return (datetime.utcnow() - self.clone_date).total_seconds() / 3600
    
    @property
    def inactive_hours(self) -> float:
        """Get hours since last access."""
        return (datetime.utcnow() - self.last_accessed).total_seconds() / 3600


@dataclass
class RepositoryWorkspace:
    """Represents a workspace for a specific ticket/branch."""
    workspace_id: str
    repository_info: RepositoryInfo
    ticket_id: str
    branch_name: str
    workspace_path: Path  # Same as repository local_path but semantically different
    created_at: datetime
    status: BranchStatus
    lock_acquired_at: Optional[datetime] = None
    metadata: Dict[str, any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize workspace ID if not provided."""
        if not self.workspace_id:
            self.workspace_id = str(uuid.uuid4())
    
    @property
    def is_active(self) -> bool:
        """Check if workspace is active."""
        return self.status == BranchStatus.ACTIVE
    
    @property
    def lock_duration_seconds(self) -> Optional[float]:
        """Get duration of current lock in seconds."""
        if self.lock_acquired_at:
            return (datetime.utcnow() - self.lock_acquired_at).total_seconds()
        return None


@dataclass
class RepositoryStats:
    """Statistics for repository pool monitoring."""
    total_repositories: int
    available_repositories: int
    in_use_repositories: int
    error_repositories: int
    total_size_bytes: int
    oldest_repository_age_hours: float
    average_age_hours: float
    cache_hit_rate: float
    average_lock_wait_time_seconds: float
    cleanup_operations_count: int
    failed_operations_count: int
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CleanupPolicy:
    """Configuration for repository cleanup policies."""
    max_inactive_hours: float = 24.0
    max_repository_age_hours: float = 168.0  # 7 days
    max_total_repositories: int = 50
    max_total_size_gb: float = 100.0
    max_error_count: int = 5
    cleanup_on_startup: bool = True
    cleanup_interval_hours: float = 6.0
    retain_active_branches: bool = True
    min_free_disk_space_gb: float = 10.0


@dataclass
class RepositoryLockInfo:
    """Information about a repository lock."""
    repository_key: str
    ticket_id: str
    acquired_at: datetime
    expires_at: datetime
    lock_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    @property
    def is_expired(self) -> bool:
        """Check if lock has expired."""
        return datetime.utcnow() > self.expires_at
    
    @property
    def time_remaining_seconds(self) -> float:
        """Get remaining time on lock in seconds."""
        remaining = (self.expires_at - datetime.utcnow()).total_seconds()
        return max(0, remaining)