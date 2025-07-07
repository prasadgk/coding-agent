"""Main repository manager that orchestrates all repository management components."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import asdict

from .models import (
    RepositoryWorkspace,
    CleanupPolicy,
    RepositoryStatus,
    BranchStatus
)
from .pool import RepositoryPool
from .locking import DistributedLockManager
from .cleaner import RepositoryCleaner
from .monitor import RepositoryHealthMonitor
from ...config.settings import RepositoryManagementConfig
from ...utils.metrics import MetricsCollector


logger = logging.getLogger(__name__)


class RepositoryManager:
    """High-level manager for repository operations with configurable policies."""
    
    def __init__(
        self,
        config: RepositoryManagementConfig,
        metrics_collector: Optional[MetricsCollector] = None
    ):
        """Initialize the repository manager.
        
        Args:
            config: Repository management configuration
            metrics_collector: Optional metrics collector
        """
        self.config = config
        self.metrics = metrics_collector
        
        # Initialize components
        self.lock_manager = DistributedLockManager(
            default_timeout_seconds=config.lock_timeout_seconds
        )
        
        self.pool = RepositoryPool(
            base_path=Path(config.base_workspace),
            max_repositories=config.max_concurrent_repos,
            lock_timeout_seconds=config.lock_timeout_seconds,
            cleanup_policy=self._create_cleanup_policy()
        )
        
        self.cleaner = RepositoryCleaner(
            repository_pool=self.pool,
            cleanup_policy=self._create_cleanup_policy()
        )
        
        self.monitor = RepositoryHealthMonitor(
            repository_pool=self.pool,
            check_interval_seconds=config.health_check_interval_seconds,
            metrics_collector=metrics_collector
        )
        
        # Track active operations
        self.active_operations: Dict[str, RepositoryWorkspace] = {}
        self._started = False
    
    def _create_cleanup_policy(self) -> CleanupPolicy:
        """Create cleanup policy from configuration.
        
        Returns:
            CleanupPolicy instance
        """
        return CleanupPolicy(
            max_inactive_hours=self.config.retention_policy.max_inactive_hours,
            max_repository_age_hours=self.config.retention_policy.max_repository_age_hours,
            max_total_repositories=self.config.retention_policy.max_total_repositories,
            max_total_size_gb=self.config.disk_space_limit_gb,
            max_error_count=5,
            cleanup_on_startup=self.config.retention_policy.cleanup_on_startup,
            cleanup_interval_hours=self.config.cleanup_interval_hours,
            retain_active_branches=True,
            min_free_disk_space_gb=10.0
        )
    
    async def start(self):
        """Start the repository manager and all components."""
        if self._started:
            logger.warning("Repository manager already started")
            return
        
        logger.info("Starting repository manager")
        
        # Start components
        await self.cleaner.start()
        await self.monitor.start()
        
        # Clean up expired locks periodically
        asyncio.create_task(self._periodic_lock_cleanup())
        
        self._started = True
        logger.info("Repository manager started successfully")
    
    async def stop(self):
        """Stop the repository manager and all components."""
        if not self._started:
            return
        
        logger.info("Stopping repository manager")
        
        # Stop components
        await self.cleaner.stop()
        await self.monitor.stop()
        
        # Release all active workspaces
        for workspace_id in list(self.active_operations.keys()):
            await self.release_workspace(workspace_id)
        
        self._started = False
        logger.info("Repository manager stopped")
    
    async def acquire_workspace(
        self,
        repository_url: str,
        ticket_id: str,
        branch_name: Optional[str] = None,
        base_branch: str = "main",
        priority: int = 0
    ) -> RepositoryWorkspace:
        """Acquire a repository workspace for a ticket.
        
        Args:
            repository_url: URL of the repository
            ticket_id: Ticket ID requesting the workspace
            branch_name: Optional branch name
            base_branch: Base branch for new branches
            priority: Priority for resource allocation
            
        Returns:
            RepositoryWorkspace instance
        """
        logger.info(
            f"Acquiring workspace for ticket {ticket_id} "
            f"(repo: {repository_url}, branch: {branch_name or 'auto'})"
        )
        
        # Acquire distributed lock first
        repo_key = self.pool._normalize_repository_url(repository_url)
        lock_info = await self.lock_manager.acquire_lock(
            repository_key=repo_key,
            ticket_id=ticket_id,
            priority=priority
        )
        
        try:
            # Get workspace from pool
            workspace = await self.pool.acquire_repository(
                repository_url=repository_url,
                ticket_id=ticket_id,
                branch_name=branch_name,
                base_branch=base_branch
            )
            
            # Track active operation
            self.active_operations[workspace.workspace_id] = workspace
            
            # Record metrics
            if self.metrics:
                self.metrics.record_counter(
                    "repository_manager.workspace_acquired",
                    tags={"repository": repo_key}
                )
            
            logger.info(
                f"Successfully acquired workspace {workspace.workspace_id} "
                f"for ticket {ticket_id}"
            )
            
            return workspace
            
        except Exception as e:
            # Release lock on failure
            await self.lock_manager.release_lock(repo_key, ticket_id)
            raise
    
    async def release_workspace(
        self,
        workspace_id: str,
        cleanup_branch: bool = False
    ):
        """Release a repository workspace.
        
        Args:
            workspace_id: ID of the workspace to release
            cleanup_branch: Whether to delete the branch
        """
        if workspace_id not in self.active_operations:
            logger.warning(f"Workspace {workspace_id} not found in active operations")
            return
        
        workspace = self.active_operations[workspace_id]
        repo_key = workspace.repository_info.repository_key
        
        logger.info(
            f"Releasing workspace {workspace_id} for ticket {workspace.ticket_id} "
            f"(cleanup_branch: {cleanup_branch})"
        )
        
        try:
            # Release from pool
            await self.pool.release_workspace(workspace_id, cleanup_branch)
            
            # Release distributed lock
            await self.lock_manager.release_lock(repo_key, workspace.ticket_id)
            
            # Remove from active operations
            del self.active_operations[workspace_id]
            
            # Record metrics
            if self.metrics:
                self.metrics.record_counter(
                    "repository_manager.workspace_released",
                    tags={"repository": repo_key, "cleanup_branch": str(cleanup_branch)}
                )
            
            logger.info(f"Successfully released workspace {workspace_id}")
            
        except Exception as e:
            logger.error(f"Error releasing workspace {workspace_id}: {e}")
            workspace.status = BranchStatus.FAILED
    
    async def extend_workspace_lock(
        self,
        workspace_id: str,
        additional_seconds: int
    ) -> bool:
        """Extend the lock for a workspace.
        
        Args:
            workspace_id: ID of the workspace
            additional_seconds: Seconds to extend the lock
            
        Returns:
            True if lock was extended
        """
        if workspace_id not in self.active_operations:
            return False
        
        workspace = self.active_operations[workspace_id]
        repo_key = workspace.repository_info.repository_key
        
        return await self.lock_manager.extend_lock(
            repo_key,
            workspace.ticket_id,
            additional_seconds
        )
    
    async def get_workspace_status(
        self,
        workspace_id: str
    ) -> Optional[Dict[str, any]]:
        """Get status of a workspace.
        
        Args:
            workspace_id: ID of the workspace
            
        Returns:
            Workspace status dictionary or None
        """
        if workspace_id not in self.active_operations:
            return None
        
        workspace = self.active_operations[workspace_id]
        
        return {
            "workspace_id": workspace.workspace_id,
            "ticket_id": workspace.ticket_id,
            "branch_name": workspace.branch_name,
            "status": workspace.status.value,
            "created_at": workspace.created_at.isoformat(),
            "lock_duration_seconds": workspace.lock_duration_seconds,
            "repository": {
                "url": workspace.repository_info.repository_url,
                "status": workspace.repository_info.status.value,
                "inactive_hours": workspace.repository_info.inactive_hours
            }
        }
    
    async def list_active_workspaces(self) -> List[Dict[str, any]]:
        """List all active workspaces.
        
        Returns:
            List of workspace status dictionaries
        """
        workspaces = []
        for workspace_id in self.active_operations:
            status = await self.get_workspace_status(workspace_id)
            if status:
                workspaces.append(status)
        return workspaces
    
    async def _periodic_lock_cleanup(self):
        """Periodically clean up expired locks."""
        while self._started:
            try:
                await asyncio.sleep(60)  # Check every minute
                cleaned = await self.lock_manager.cleanup_expired_locks()
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} expired locks")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in lock cleanup: {e}")
    
    def get_statistics(self) -> Dict[str, any]:
        """Get comprehensive repository manager statistics.
        
        Returns:
            Dictionary with all statistics
        """
        return {
            "pool_statistics": self.pool.get_statistics(),
            "lock_statistics": self.lock_manager.get_lock_statistics(),
            "cleanup_statistics": self.cleaner.get_cleanup_statistics(),
            "health_summary": self.monitor.get_health_summary(),
            "active_workspaces": len(self.active_operations),
            "configuration": {
                "base_workspace": str(self.config.base_workspace),
                "max_concurrent_repos": self.config.max_concurrent_repos,
                "enable_repository_caching": self.config.enable_repository_caching,
                "retention_policy": asdict(self.config.retention_policy)
            }
        }
    
    async def force_cleanup(self, repository_url: Optional[str] = None):
        """Force cleanup of repositories.
        
        Args:
            repository_url: Optional specific repository to clean
        """
        if repository_url:
            repo_key = self.pool._normalize_repository_url(repository_url)
            success = await self.cleaner.force_cleanup_repository(repo_key)
            return {"repository": repository_url, "cleaned": success}
        else:
            results = await self.cleaner.run_cleanup()
            return results
    
    async def check_health(self) -> Dict[str, any]:
        """Run health check and return results.
        
        Returns:
            Health check results
        """
        stats = await self.monitor.check_all_repositories()
        return {
            "timestamp": stats.timestamp.isoformat(),
            "healthy": stats.error_repositories == 0,
            "statistics": asdict(stats),
            "issues": dict(self.monitor.health_issues)
        }