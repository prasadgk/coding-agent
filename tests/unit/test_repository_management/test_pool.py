"""Tests for repository pool management."""

import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
import tempfile
import shutil
from unittest.mock import Mock, patch, AsyncMock

from src.core.repository_management.pool import RepositoryPool
from src.core.repository_management.models import (
    RepositoryInfo,
    RepositoryStatus,
    CleanupPolicy
)
from src.utils.exceptions import (
    RepositoryError,
    RepositoryLockError,
    RepositoryNotFoundError
)


@pytest.fixture
async def temp_workspace():
    """Create a temporary workspace directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def repository_pool(temp_workspace):
    """Create a repository pool instance."""
    pool = RepositoryPool(
        base_path=temp_workspace,
        max_repositories=5,
        lock_timeout_seconds=10
    )
    yield pool
    # Cleanup
    for repo_key in list(pool.repositories.keys()):
        await pool._remove_repository(repo_key)


class TestRepositoryPool:
    """Test RepositoryPool functionality."""
    
    def test_normalize_repository_url(self, repository_pool):
        """Test URL normalization."""
        test_cases = [
            ("https://github.com/user/repo.git", "github.com_user_repo"),
            ("git@github.com:user/repo.git", "github.com:user_repo"),
            ("https://bitbucket.org/team/project/", "bitbucket.org_team_project"),
            ("HTTP://GITHUB.COM/USER/REPO.GIT", "github.com_user_repo"),
        ]
        
        for url, expected in test_cases:
            normalized = repository_pool._normalize_repository_url(url)
            assert normalized == expected
    
    @pytest.mark.asyncio
    async def test_acquire_new_repository(self, repository_pool):
        """Test acquiring a new repository."""
        with patch.object(repository_pool, '_clone_repository') as mock_clone:
            # Mock successful clone
            repo_info = RepositoryInfo(
                repository_url="https://github.com/test/repo.git",
                repository_key="github.com_test_repo",
                local_path=repository_pool.base_path / "github.com_test_repo",
                status=RepositoryStatus.AVAILABLE,
                last_accessed=datetime.utcnow(),
                last_updated=datetime.utcnow(),
                clone_date=datetime.utcnow(),
                size_bytes=1024
            )
            mock_clone.return_value = repo_info
            
            with patch.object(repository_pool, '_create_workspace') as mock_workspace:
                from src.core.repository_management.models import RepositoryWorkspace, BranchStatus
                workspace = RepositoryWorkspace(
                    workspace_id="ws-123",
                    repository_info=repo_info,
                    ticket_id="TICKET-123",
                    branch_name="feature/TICKET-123",
                    workspace_path=repo_info.local_path,
                    created_at=datetime.utcnow(),
                    status=BranchStatus.ACTIVE
                )
                mock_workspace.return_value = workspace
                
                # Acquire repository
                result = await repository_pool.acquire_repository(
                    repository_url="https://github.com/test/repo.git",
                    ticket_id="TICKET-123"
                )
                
                assert result.ticket_id == "TICKET-123"
                assert result.workspace_id == "ws-123"
                assert repository_pool.cache_misses == 1
                assert repository_pool.cache_hits == 0
    
    @pytest.mark.asyncio
    async def test_reuse_existing_repository(self, repository_pool):
        """Test reusing an existing repository."""
        # Add existing repository to pool
        repo_info = RepositoryInfo(
            repository_url="https://github.com/test/repo.git",
            repository_key="github.com_test_repo",
            local_path=repository_pool.base_path / "github.com_test_repo",
            status=RepositoryStatus.AVAILABLE,
            last_accessed=datetime.utcnow() - timedelta(hours=1),
            last_updated=datetime.utcnow() - timedelta(hours=1),
            clone_date=datetime.utcnow() - timedelta(hours=2),
            size_bytes=1024
        )
        repository_pool.repositories["github.com_test_repo"] = repo_info
        
        with patch.object(repository_pool, '_update_repository') as mock_update:
            mock_update.return_value = None
            
            with patch.object(repository_pool, '_create_workspace') as mock_workspace:
                from src.core.repository_management.models import RepositoryWorkspace, BranchStatus
                workspace = RepositoryWorkspace(
                    workspace_id="ws-456",
                    repository_info=repo_info,
                    ticket_id="TICKET-456",
                    branch_name="feature/TICKET-456",
                    workspace_path=repo_info.local_path,
                    created_at=datetime.utcnow(),
                    status=BranchStatus.ACTIVE
                )
                mock_workspace.return_value = workspace
                
                # Acquire repository
                result = await repository_pool.acquire_repository(
                    repository_url="https://github.com/test/repo.git",
                    ticket_id="TICKET-456"
                )
                
                assert result.ticket_id == "TICKET-456"
                assert repository_pool.cache_hits == 1
                assert repository_pool.cache_misses == 0
                mock_update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_lock_timeout(self, repository_pool):
        """Test lock acquisition timeout."""
        repository_pool.lock_timeout_seconds = 0.1  # Very short timeout
        
        # Acquire lock for first ticket
        lock = repository_pool.repository_locks.get("test_repo", asyncio.Lock())
        repository_pool.repository_locks["test_repo"] = lock
        await lock.acquire()
        
        try:
            # Try to acquire for second ticket (should timeout)
            with pytest.raises(RepositoryLockError) as exc_info:
                await repository_pool.acquire_repository(
                    repository_url="https://github.com/test/repo.git",
                    ticket_id="TICKET-789"
                )
            
            assert "Failed to acquire lock" in str(exc_info.value)
        finally:
            lock.release()
    
    @pytest.mark.asyncio
    async def test_eviction_when_full(self, repository_pool):
        """Test repository eviction when pool is full."""
        repository_pool.max_repositories = 2
        
        # Fill the pool
        for i in range(2):
            repo_info = RepositoryInfo(
                repository_url=f"https://github.com/test/repo{i}.git",
                repository_key=f"repo_{i}",
                local_path=repository_pool.base_path / f"repo_{i}",
                status=RepositoryStatus.AVAILABLE,
                last_accessed=datetime.utcnow() - timedelta(hours=i+1),
                last_updated=datetime.utcnow(),
                clone_date=datetime.utcnow(),
                size_bytes=1024
            )
            repository_pool.repositories[f"repo_{i}"] = repo_info
        
        assert len(repository_pool.repositories) == 2
        
        # Mock eviction
        with patch.object(repository_pool, '_evict_repository') as mock_evict:
            mock_evict.return_value = None
            
            with patch.object(repository_pool, '_clone_repository') as mock_clone:
                new_repo = RepositoryInfo(
                    repository_url="https://github.com/test/repo_new.git",
                    repository_key="repo_new",
                    local_path=repository_pool.base_path / "repo_new",
                    status=RepositoryStatus.AVAILABLE,
                    last_accessed=datetime.utcnow(),
                    last_updated=datetime.utcnow(),
                    clone_date=datetime.utcnow(),
                    size_bytes=1024
                )
                mock_clone.return_value = new_repo
                
                with patch.object(repository_pool, '_create_workspace') as mock_workspace:
                    from src.core.repository_management.models import RepositoryWorkspace, BranchStatus
                    workspace = RepositoryWorkspace(
                        workspace_id="ws-new",
                        repository_info=new_repo,
                        ticket_id="TICKET-NEW",
                        branch_name="feature/TICKET-NEW",
                        workspace_path=new_repo.local_path,
                        created_at=datetime.utcnow(),
                        status=BranchStatus.ACTIVE
                    )
                    mock_workspace.return_value = workspace
                    
                    # Acquire new repository (should trigger eviction)
                    await repository_pool.acquire_repository(
                        repository_url="https://github.com/test/repo_new.git",
                        ticket_id="TICKET-NEW"
                    )
                    
                    mock_evict.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_release_workspace(self, repository_pool):
        """Test releasing a workspace."""
        # Create a workspace
        repo_info = RepositoryInfo(
            repository_url="https://github.com/test/repo.git",
            repository_key="test_repo",
            local_path=repository_pool.base_path / "test_repo",
            status=RepositoryStatus.IN_USE,
            last_accessed=datetime.utcnow(),
            last_updated=datetime.utcnow(),
            clone_date=datetime.utcnow(),
            size_bytes=1024,
            active_branches={"feature/test"}
        )
        
        from src.core.repository_management.models import RepositoryWorkspace, BranchStatus
        workspace = RepositoryWorkspace(
            workspace_id="ws-test",
            repository_info=repo_info,
            ticket_id="TICKET-TEST",
            branch_name="feature/test",
            workspace_path=repo_info.local_path,
            created_at=datetime.utcnow(),
            status=BranchStatus.ACTIVE
        )
        
        repository_pool.repositories["test_repo"] = repo_info
        repository_pool.workspaces["ws-test"] = workspace
        
        # Release without cleanup
        await repository_pool.release_workspace("ws-test", cleanup_branch=False)
        
        assert workspace.status == BranchStatus.COMPLETED
        assert workspace.lock_acquired_at is None
        assert "feature/test" in repo_info.active_branches
    
    @pytest.mark.asyncio
    async def test_release_nonexistent_workspace(self, repository_pool):
        """Test releasing a non-existent workspace."""
        with pytest.raises(RepositoryNotFoundError) as exc_info:
            await repository_pool.release_workspace("ws-nonexistent")
        
        assert "Workspace ws-nonexistent not found" in str(exc_info.value)
    
    def test_get_statistics(self, repository_pool):
        """Test getting pool statistics."""
        # Add some repositories
        for i in range(3):
            repo_info = RepositoryInfo(
                repository_url=f"https://github.com/test/repo{i}.git",
                repository_key=f"repo_{i}",
                local_path=repository_pool.base_path / f"repo_{i}",
                status=RepositoryStatus.AVAILABLE if i < 2 else RepositoryStatus.IN_USE,
                last_accessed=datetime.utcnow(),
                last_updated=datetime.utcnow(),
                clone_date=datetime.utcnow(),
                size_bytes=1024 * 1024 * (i + 1)  # 1MB, 2MB, 3MB
            )
            repository_pool.repositories[f"repo_{i}"] = repo_info
        
        repository_pool.cache_hits = 10
        repository_pool.cache_misses = 5
        repository_pool.total_acquisitions = 15
        
        stats = repository_pool.get_statistics()
        
        assert stats["total_repositories"] == 3
        assert stats["available_repositories"] == 2
        assert stats["in_use_repositories"] == 1
        assert stats["total_size_gb"] == 6 / 1024  # 6MB in GB
        assert stats["cache_hit_rate"] == 10 / 15
        assert stats["total_acquisitions"] == 15