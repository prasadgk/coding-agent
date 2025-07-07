"""Tests for repository management data models."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import uuid

from src.core.repository_management.models import (
    RepositoryInfo,
    RepositoryWorkspace,
    RepositoryStatus,
    BranchStatus,
    RepositoryStats,
    CleanupPolicy,
    RepositoryLockInfo
)


class TestRepositoryInfo:
    """Test RepositoryInfo model."""
    
    def test_repository_info_creation(self):
        """Test creating RepositoryInfo instance."""
        now = datetime.utcnow()
        repo_info = RepositoryInfo(
            repository_url="https://github.com/test/repo.git",
            repository_key="github_com_test_repo",
            local_path=Path("/tmp/repos/test"),
            status=RepositoryStatus.AVAILABLE,
            last_accessed=now,
            last_updated=now,
            clone_date=now,
            size_bytes=1024 * 1024  # 1MB
        )
        
        assert repo_info.repository_url == "https://github.com/test/repo.git"
        assert repo_info.repository_key == "github_com_test_repo"
        assert repo_info.status == RepositoryStatus.AVAILABLE
        assert repo_info.is_available
        assert repo_info.error_count == 0
        assert len(repo_info.active_branches) == 0
    
    def test_repository_age_calculation(self):
        """Test age calculation methods."""
        old_date = datetime.utcnow() - timedelta(hours=48)
        recent_date = datetime.utcnow() - timedelta(hours=2)
        
        repo_info = RepositoryInfo(
            repository_url="test",
            repository_key="test",
            local_path=Path("/tmp/test"),
            status=RepositoryStatus.AVAILABLE,
            last_accessed=recent_date,
            last_updated=datetime.utcnow(),
            clone_date=old_date,
            size_bytes=0
        )
        
        assert 47.9 < repo_info.age_hours < 48.1
        assert 1.9 < repo_info.inactive_hours < 2.1
    
    def test_repository_status_checks(self):
        """Test repository status checks."""
        repo_info = RepositoryInfo(
            repository_url="test",
            repository_key="test",
            local_path=Path("/tmp/test"),
            status=RepositoryStatus.ERROR,
            last_accessed=datetime.utcnow(),
            last_updated=datetime.utcnow(),
            clone_date=datetime.utcnow(),
            size_bytes=0
        )
        
        assert not repo_info.is_available
        
        repo_info.status = RepositoryStatus.AVAILABLE
        assert repo_info.is_available


class TestRepositoryWorkspace:
    """Test RepositoryWorkspace model."""
    
    def test_workspace_creation(self):
        """Test creating workspace with auto-generated ID."""
        repo_info = RepositoryInfo(
            repository_url="test",
            repository_key="test",
            local_path=Path("/tmp/test"),
            status=RepositoryStatus.IN_USE,
            last_accessed=datetime.utcnow(),
            last_updated=datetime.utcnow(),
            clone_date=datetime.utcnow(),
            size_bytes=0
        )
        
        workspace = RepositoryWorkspace(
            workspace_id="",  # Should auto-generate
            repository_info=repo_info,
            ticket_id="TICKET-123",
            branch_name="feature/TICKET-123",
            workspace_path=Path("/tmp/test"),
            created_at=datetime.utcnow(),
            status=BranchStatus.ACTIVE
        )
        
        assert workspace.workspace_id  # Should have generated ID
        assert workspace.ticket_id == "TICKET-123"
        assert workspace.branch_name == "feature/TICKET-123"
        assert workspace.is_active
    
    def test_lock_duration_calculation(self):
        """Test lock duration calculation."""
        repo_info = RepositoryInfo(
            repository_url="test",
            repository_key="test",
            local_path=Path("/tmp/test"),
            status=RepositoryStatus.IN_USE,
            last_accessed=datetime.utcnow(),
            last_updated=datetime.utcnow(),
            clone_date=datetime.utcnow(),
            size_bytes=0
        )
        
        lock_time = datetime.utcnow() - timedelta(seconds=30)
        workspace = RepositoryWorkspace(
            workspace_id="test",
            repository_info=repo_info,
            ticket_id="TICKET-123",
            branch_name="test",
            workspace_path=Path("/tmp/test"),
            created_at=datetime.utcnow(),
            status=BranchStatus.ACTIVE,
            lock_acquired_at=lock_time
        )
        
        assert 29.9 < workspace.lock_duration_seconds < 30.1
        
        # Test without lock
        workspace.lock_acquired_at = None
        assert workspace.lock_duration_seconds is None


class TestRepositoryStats:
    """Test RepositoryStats model."""
    
    def test_stats_creation(self):
        """Test creating repository statistics."""
        stats = RepositoryStats(
            total_repositories=10,
            available_repositories=5,
            in_use_repositories=3,
            error_repositories=2,
            total_size_bytes=1024 * 1024 * 1024,  # 1GB
            oldest_repository_age_hours=168.0,
            average_age_hours=72.0,
            cache_hit_rate=0.85,
            average_lock_wait_time_seconds=2.5,
            cleanup_operations_count=5,
            failed_operations_count=1
        )
        
        assert stats.total_repositories == 10
        assert stats.cache_hit_rate == 0.85
        assert stats.timestamp <= datetime.utcnow()


class TestCleanupPolicy:
    """Test CleanupPolicy model."""
    
    def test_default_policy(self):
        """Test default cleanup policy values."""
        policy = CleanupPolicy()
        
        assert policy.max_inactive_hours == 24.0
        assert policy.max_repository_age_hours == 168.0  # 7 days
        assert policy.max_total_repositories == 50
        assert policy.max_total_size_gb == 100.0
        assert policy.cleanup_on_startup
        assert policy.cleanup_interval_hours == 6.0
    
    def test_custom_policy(self):
        """Test custom cleanup policy."""
        policy = CleanupPolicy(
            max_inactive_hours=12.0,
            max_total_repositories=100,
            cleanup_on_startup=False
        )
        
        assert policy.max_inactive_hours == 12.0
        assert policy.max_total_repositories == 100
        assert not policy.cleanup_on_startup


class TestRepositoryLockInfo:
    """Test RepositoryLockInfo model."""
    
    def test_lock_creation(self):
        """Test creating lock info."""
        now = datetime.utcnow()
        expires = now + timedelta(seconds=300)
        
        lock = RepositoryLockInfo(
            repository_key="test_repo",
            ticket_id="TICKET-123",
            acquired_at=now,
            expires_at=expires
        )
        
        assert lock.repository_key == "test_repo"
        assert lock.ticket_id == "TICKET-123"
        assert lock.lock_id  # Should have generated ID
        assert not lock.is_expired
        assert 299.9 < lock.time_remaining_seconds < 300.1
    
    def test_expired_lock(self):
        """Test expired lock detection."""
        past = datetime.utcnow() - timedelta(seconds=60)
        
        lock = RepositoryLockInfo(
            repository_key="test_repo",
            ticket_id="TICKET-123",
            acquired_at=past - timedelta(seconds=300),
            expires_at=past
        )
        
        assert lock.is_expired
        assert lock.time_remaining_seconds == 0