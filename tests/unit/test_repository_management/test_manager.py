"""Tests for the main repository manager."""

import pytest
import asyncio
from pathlib import Path
from datetime import datetime
import tempfile
import shutil
from unittest.mock import Mock, patch, AsyncMock

from src.core.repository_management.manager import RepositoryManager
from src.core.repository_management.models import (
    RepositoryWorkspace,
    BranchStatus,
    RetentionPolicy
)
from src.config.settings import RepositoryManagementConfig
from src.utils.metrics import MetricsCollector


@pytest.fixture
async def temp_workspace():
    """Create a temporary workspace directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def repo_config(temp_workspace):
    """Create repository management configuration."""
    config = RepositoryManagementConfig(
        base_workspace=temp_workspace,
        max_concurrent_repos=5,
        cleanup_interval_hours=1.0,
        health_check_interval_seconds=60,
        lock_timeout_seconds=10,
        retention_policy=RetentionPolicy(
            max_inactive_hours=24.0,
            max_repository_age_hours=168.0,
            max_total_repositories=10,
            cleanup_on_startup=False
        )
    )
    return config


@pytest.fixture
async def repository_manager(repo_config):
    """Create a repository manager instance."""
    manager = RepositoryManager(config=repo_config)
    yield manager
    # Cleanup
    if manager._started:
        await manager.stop()


class TestRepositoryManager:
    """Test RepositoryManager functionality."""
    
    @pytest.mark.asyncio
    async def test_manager_initialization(self, repository_manager, repo_config):
        """Test manager initialization."""
        assert repository_manager.config == repo_config
        assert not repository_manager._started
        assert len(repository_manager.active_operations) == 0
        assert repository_manager.pool is not None
        assert repository_manager.cleaner is not None
        assert repository_manager.monitor is not None
        assert repository_manager.lock_manager is not None
    
    @pytest.mark.asyncio
    async def test_start_stop_manager(self, repository_manager):
        """Test starting and stopping the manager."""
        # Mock component start methods
        repository_manager.cleaner.start = AsyncMock()
        repository_manager.monitor.start = AsyncMock()
        
        # Start manager
        await repository_manager.start()
        assert repository_manager._started
        repository_manager.cleaner.start.assert_called_once()
        repository_manager.monitor.start.assert_called_once()
        
        # Try starting again (should warn)
        await repository_manager.start()
        
        # Mock component stop methods
        repository_manager.cleaner.stop = AsyncMock()
        repository_manager.monitor.stop = AsyncMock()
        
        # Stop manager
        await repository_manager.stop()
        assert not repository_manager._started
        repository_manager.cleaner.stop.assert_called_once()
        repository_manager.monitor.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_acquire_workspace(self, repository_manager):
        """Test acquiring a workspace."""
        # Mock dependencies
        lock_info = Mock()
        repository_manager.lock_manager.acquire_lock = AsyncMock(return_value=lock_info)
        
        workspace = Mock(spec=RepositoryWorkspace)
        workspace.workspace_id = "ws-123"
        workspace.ticket_id = "TICKET-123"
        workspace.repository_info = Mock()
        workspace.repository_info.repository_key = "test_repo"
        
        repository_manager.pool.acquire_repository = AsyncMock(return_value=workspace)
        
        # Acquire workspace
        result = await repository_manager.acquire_workspace(
            repository_url="https://github.com/test/repo.git",
            ticket_id="TICKET-123",
            branch_name="feature/test"
        )
        
        assert result == workspace
        assert "ws-123" in repository_manager.active_operations
        repository_manager.lock_manager.acquire_lock.assert_called_once()
        repository_manager.pool.acquire_repository.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_acquire_workspace_failure(self, repository_manager):
        """Test workspace acquisition failure."""
        # Mock lock acquisition success but pool failure
        lock_info = Mock()
        repository_manager.lock_manager.acquire_lock = AsyncMock(return_value=lock_info)
        repository_manager.lock_manager.release_lock = AsyncMock()
        
        repository_manager.pool.acquire_repository = AsyncMock(
            side_effect=Exception("Pool error")
        )
        
        # Should release lock on failure
        with pytest.raises(Exception) as exc_info:
            await repository_manager.acquire_workspace(
                repository_url="https://github.com/test/repo.git",
                ticket_id="TICKET-123"
            )
        
        assert "Pool error" in str(exc_info.value)
        repository_manager.lock_manager.release_lock.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_release_workspace(self, repository_manager):
        """Test releasing a workspace."""
        # Create active workspace
        workspace = Mock(spec=RepositoryWorkspace)
        workspace.workspace_id = "ws-123"
        workspace.ticket_id = "TICKET-123"
        workspace.repository_info = Mock()
        workspace.repository_info.repository_key = "test_repo"
        workspace.status = BranchStatus.ACTIVE
        
        repository_manager.active_operations["ws-123"] = workspace
        
        # Mock release operations
        repository_manager.pool.release_workspace = AsyncMock()
        repository_manager.lock_manager.release_lock = AsyncMock()
        
        # Release workspace
        await repository_manager.release_workspace("ws-123", cleanup_branch=True)
        
        assert "ws-123" not in repository_manager.active_operations
        repository_manager.pool.release_workspace.assert_called_once_with("ws-123", True)
        repository_manager.lock_manager.release_lock.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extend_workspace_lock(self, repository_manager):
        """Test extending a workspace lock."""
        # Create active workspace
        workspace = Mock(spec=RepositoryWorkspace)
        workspace.workspace_id = "ws-123"
        workspace.ticket_id = "TICKET-123"
        workspace.repository_info = Mock()
        workspace.repository_info.repository_key = "test_repo"
        
        repository_manager.active_operations["ws-123"] = workspace
        repository_manager.lock_manager.extend_lock = AsyncMock(return_value=True)
        
        # Extend lock
        result = await repository_manager.extend_workspace_lock("ws-123", 300)
        
        assert result is True
        repository_manager.lock_manager.extend_lock.assert_called_once_with(
            "test_repo", "TICKET-123", 300
        )
    
    @pytest.mark.asyncio
    async def test_get_workspace_status(self, repository_manager):
        """Test getting workspace status."""
        # Create active workspace
        workspace = Mock(spec=RepositoryWorkspace)
        workspace.workspace_id = "ws-123"
        workspace.ticket_id = "TICKET-123"
        workspace.branch_name = "feature/test"
        workspace.status = BranchStatus.ACTIVE
        workspace.created_at = datetime.utcnow()
        workspace.lock_duration_seconds = 120
        workspace.repository_info = Mock()
        workspace.repository_info.repository_url = "https://github.com/test/repo.git"
        workspace.repository_info.status.value = "in_use"
        workspace.repository_info.inactive_hours = 2.5
        
        repository_manager.active_operations["ws-123"] = workspace
        
        # Get status
        status = await repository_manager.get_workspace_status("ws-123")
        
        assert status["workspace_id"] == "ws-123"
        assert status["ticket_id"] == "TICKET-123"
        assert status["branch_name"] == "feature/test"
        assert status["status"] == BranchStatus.ACTIVE.value
        assert status["lock_duration_seconds"] == 120
        assert status["repository"]["url"] == "https://github.com/test/repo.git"
    
    @pytest.mark.asyncio
    async def test_list_active_workspaces(self, repository_manager):
        """Test listing active workspaces."""
        # Create multiple workspaces
        for i in range(3):
            workspace = Mock(spec=RepositoryWorkspace)
            workspace.workspace_id = f"ws-{i}"
            workspace.ticket_id = f"TICKET-{i}"
            workspace.branch_name = f"feature/test-{i}"
            workspace.status = BranchStatus.ACTIVE
            workspace.created_at = datetime.utcnow()
            workspace.lock_duration_seconds = i * 60
            workspace.repository_info = Mock()
            workspace.repository_info.repository_url = f"https://github.com/test/repo{i}.git"
            workspace.repository_info.status.value = "in_use"
            workspace.repository_info.inactive_hours = i * 0.5
            
            repository_manager.active_operations[f"ws-{i}"] = workspace
        
        # List workspaces
        workspaces = await repository_manager.list_active_workspaces()
        
        assert len(workspaces) == 3
        assert all(ws["workspace_id"] in ["ws-0", "ws-1", "ws-2"] for ws in workspaces)
    
    def test_get_statistics(self, repository_manager):
        """Test getting manager statistics."""
        # Mock component statistics
        repository_manager.pool.get_statistics = Mock(return_value={"pool": "stats"})
        repository_manager.lock_manager.get_lock_statistics = Mock(return_value={"lock": "stats"})
        repository_manager.cleaner.get_cleanup_statistics = Mock(return_value={"cleanup": "stats"})
        repository_manager.monitor.get_health_summary = Mock(return_value={"health": "summary"})
        
        # Get statistics
        stats = repository_manager.get_statistics()
        
        assert stats["pool_statistics"] == {"pool": "stats"}
        assert stats["lock_statistics"] == {"lock": "stats"}
        assert stats["cleanup_statistics"] == {"cleanup": "stats"}
        assert stats["health_summary"] == {"health": "summary"}
        assert stats["active_workspaces"] == 0
        assert "configuration" in stats
    
    @pytest.mark.asyncio
    async def test_force_cleanup_specific_repo(self, repository_manager):
        """Test forcing cleanup of a specific repository."""
        repository_manager.cleaner.force_cleanup_repository = AsyncMock(return_value=True)
        repository_manager.pool._normalize_repository_url = Mock(return_value="test_repo")
        
        result = await repository_manager.force_cleanup(
            repository_url="https://github.com/test/repo.git"
        )
        
        assert result["repository"] == "https://github.com/test/repo.git"
        assert result["cleaned"] is True
        repository_manager.cleaner.force_cleanup_repository.assert_called_once_with("test_repo")
    
    @pytest.mark.asyncio
    async def test_force_cleanup_all(self, repository_manager):
        """Test forcing cleanup of all repositories."""
        cleanup_results = {
            "repositories_removed": 2,
            "space_reclaimed_gb": 5.5
        }
        repository_manager.cleaner.run_cleanup = AsyncMock(return_value=cleanup_results)
        
        result = await repository_manager.force_cleanup()
        
        assert result == cleanup_results
        repository_manager.cleaner.run_cleanup.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_health(self, repository_manager):
        """Test health check."""
        from src.core.repository_management.models import RepositoryStats
        
        stats = RepositoryStats(
            total_repositories=5,
            available_repositories=3,
            in_use_repositories=2,
            error_repositories=0,
            total_size_bytes=1024 * 1024 * 1024,
            oldest_repository_age_hours=24.0,
            average_age_hours=12.0,
            cache_hit_rate=0.8,
            average_lock_wait_time_seconds=1.5,
            cleanup_operations_count=2,
            failed_operations_count=0
        )
        
        repository_manager.monitor.check_all_repositories = AsyncMock(return_value=stats)
        repository_manager.monitor.health_issues = {"repo1": ["issue1"]}
        
        result = await repository_manager.check_health()
        
        assert result["healthy"] is True  # No error repositories
        assert "timestamp" in result
        assert "statistics" in result
        assert result["issues"] == {"repo1": ["issue1"]}