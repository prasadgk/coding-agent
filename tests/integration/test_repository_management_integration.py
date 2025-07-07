"""Integration tests for repository management system."""

import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil
from datetime import datetime, timedelta

from src.core.repository_management.manager import RepositoryManager
from src.core.repository_management.models import (
    RetentionPolicy,
    ConcurrentProcessingConfig
)
from src.config.settings import RepositoryManagementConfig


class TestRepositoryManagementIntegration:
    """Integration tests for the complete repository management system."""
    
    @pytest.fixture
    async def integration_config(self):
        """Create configuration for integration testing."""
        temp_dir = tempfile.mkdtemp()
        
        config = RepositoryManagementConfig(
            base_workspace=Path(temp_dir),
            max_concurrent_repos=3,
            cleanup_interval_hours=0.1,  # Fast cleanup for testing
            health_check_interval_seconds=5,
            lock_timeout_seconds=10,
            retention_policy=RetentionPolicy(
                max_inactive_hours=0.5,  # 30 minutes
                max_repository_age_hours=1.0,  # 1 hour
                max_total_repositories=3,
                cleanup_on_startup=True
            ),
            concurrent_processing=ConcurrentProcessingConfig(
                max_parallel_tickets=5,
                repository_lock_timeout=10
            )
        )
        
        yield config
        
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_workspace_acquisition(self, integration_config):
        """Test concurrent acquisition of workspaces for the same repository."""
        manager = RepositoryManager(config=integration_config)
        await manager.start()
        
        try:
            # Simulate multiple tickets for the same repository
            tasks = []
            for i in range(3):
                task = asyncio.create_task(
                    manager.acquire_workspace(
                        repository_url="https://github.com/test/repo.git",
                        ticket_id=f"TICKET-{i}",
                        branch_name=f"feature/TICKET-{i}"
                    )
                )
                tasks.append(task)
            
            # All should succeed (handled by locking)
            workspaces = await asyncio.gather(*tasks)
            
            assert len(workspaces) == 3
            assert all(ws.ticket_id == f"TICKET-{i}" for i, ws in enumerate(workspaces))
            
            # Check statistics
            stats = manager.get_statistics()
            assert stats["active_workspaces"] == 3
            assert stats["pool_statistics"]["total_repositories"] == 1  # Reused same repo
            
            # Release all workspaces
            for ws in workspaces:
                await manager.release_workspace(ws.workspace_id)
                
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_repository_reuse_optimization(self, integration_config):
        """Test that repositories are reused for performance optimization."""
        manager = RepositoryManager(config=integration_config)
        await manager.start()
        
        try:
            # First acquisition - should clone
            ws1 = await manager.acquire_workspace(
                repository_url="https://github.com/test/repo.git",
                ticket_id="TICKET-1"
            )
            
            # Check cache miss
            assert manager.pool.cache_misses == 1
            assert manager.pool.cache_hits == 0
            
            # Release workspace
            await manager.release_workspace(ws1.workspace_id)
            
            # Second acquisition - should reuse
            ws2 = await manager.acquire_workspace(
                repository_url="https://github.com/test/repo.git",
                ticket_id="TICKET-2"
            )
            
            # Check cache hit
            assert manager.pool.cache_misses == 1
            assert manager.pool.cache_hits == 1
            
            # Should be same repository
            assert ws1.repository_info.repository_key == ws2.repository_info.repository_key
            
            await manager.release_workspace(ws2.workspace_id)
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_automatic_cleanup(self, integration_config):
        """Test automatic cleanup of inactive repositories."""
        # Set very aggressive cleanup policy
        integration_config.retention_policy.max_inactive_hours = 0.01  # 36 seconds
        integration_config.cleanup_interval_hours = 0.001  # 3.6 seconds
        
        manager = RepositoryManager(config=integration_config)
        await manager.start()
        
        try:
            # Create workspaces for different repositories
            workspaces = []
            for i in range(3):
                ws = await manager.acquire_workspace(
                    repository_url=f"https://github.com/test/repo{i}.git",
                    ticket_id=f"TICKET-{i}"
                )
                workspaces.append(ws)
            
            # Release all workspaces
            for ws in workspaces:
                await manager.release_workspace(ws.workspace_id)
            
            # Check initial state
            stats1 = manager.get_statistics()
            assert stats1["pool_statistics"]["total_repositories"] == 3
            
            # Wait for cleanup to run
            await asyncio.sleep(5)
            
            # Force a cleanup cycle
            await manager.force_cleanup()
            
            # Check after cleanup
            stats2 = manager.get_statistics()
            # Repositories should be cleaned up due to inactivity
            assert stats2["pool_statistics"]["total_repositories"] < 3
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_health_monitoring_and_recovery(self, integration_config):
        """Test health monitoring and recovery functionality."""
        manager = RepositoryManager(config=integration_config)
        await manager.start()
        
        try:
            # Acquire workspace
            ws = await manager.acquire_workspace(
                repository_url="https://github.com/test/repo.git",
                ticket_id="TICKET-1"
            )
            
            # Simulate repository corruption
            repo_info = ws.repository_info
            repo_info.error_count = 5  # High error count
            
            # Run health check
            health = await manager.check_health()
            
            # Should detect unhealthy repository
            assert not health["healthy"] or len(health["issues"]) > 0
            
            # Release workspace
            await manager.release_workspace(ws.workspace_id)
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_lock_expiration_and_recovery(self, integration_config):
        """Test handling of expired locks."""
        manager = RepositoryManager(config=integration_config)
        await manager.start()
        
        try:
            # Manually create an expired lock
            repo_key = manager.pool._normalize_repository_url("https://github.com/test/repo.git")
            
            from src.core.repository_management.models import RepositoryLockInfo
            expired_lock = RepositoryLockInfo(
                repository_key=repo_key,
                ticket_id="DEAD-TICKET",
                acquired_at=datetime.utcnow() - timedelta(minutes=10),
                expires_at=datetime.utcnow() - timedelta(minutes=5)
            )
            manager.lock_manager.locks[repo_key] = expired_lock
            
            # Try to acquire workspace (should handle expired lock)
            ws = await manager.acquire_workspace(
                repository_url="https://github.com/test/repo.git",
                ticket_id="NEW-TICKET"
            )
            
            assert ws.ticket_id == "NEW-TICKET"
            assert repo_key not in manager.lock_manager.locks or \
                   manager.lock_manager.locks[repo_key].ticket_id == "NEW-TICKET"
            
            await manager.release_workspace(ws.workspace_id)
            
        finally:
            await manager.stop()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_workflow_simulation(self, integration_config):
        """Test a complete workflow simulation with multiple operations."""
        manager = RepositoryManager(config=integration_config)
        await manager.start()
        
        try:
            # Simulate a development workflow
            
            # 1. Developer 1 starts work on TICKET-1
            ws1 = await manager.acquire_workspace(
                repository_url="https://github.com/test/project.git",
                ticket_id="TICKET-1",
                branch_name="feature/user-auth"
            )
            
            # 2. Developer 2 starts work on TICKET-2 (same repo)
            ws2 = await manager.acquire_workspace(
                repository_url="https://github.com/test/project.git",
                ticket_id="TICKET-2",
                branch_name="feature/api-endpoints"
            )
            
            # 3. Check active workspaces
            active = await manager.list_active_workspaces()
            assert len(active) == 2
            
            # 4. Developer 1 needs more time
            extended = await manager.extend_workspace_lock(ws1.workspace_id, 300)
            assert extended
            
            # 5. Developer 2 completes work
            await manager.release_workspace(ws2.workspace_id, cleanup_branch=True)
            
            # 6. Check statistics
            stats = manager.get_statistics()
            assert stats["active_workspaces"] == 1
            assert stats["pool_statistics"]["cache_hit_rate"] > 0  # Second acquisition was a hit
            
            # 7. Developer 1 completes work
            await manager.release_workspace(ws1.workspace_id, cleanup_branch=True)
            
            # 8. Final health check
            health = await manager.check_health()
            assert health["healthy"]
            
        finally:
            await manager.stop()


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "-m", "integration"])