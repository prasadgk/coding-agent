"""Automatic cleanup and maintenance routines for repository management."""

import asyncio
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set
import psutil

from .models import (
    RepositoryInfo,
    RepositoryStatus,
    CleanupPolicy,
    BranchStatus
)
from .pool import RepositoryPool


logger = logging.getLogger(__name__)


class RepositoryCleaner:
    """Handles automatic cleanup and maintenance of repository pool."""
    
    def __init__(
        self,
        repository_pool: RepositoryPool,
        cleanup_policy: CleanupPolicy
    ):
        """Initialize the repository cleaner.
        
        Args:
            repository_pool: The repository pool to manage
            cleanup_policy: Policy configuration for cleanup
        """
        self.pool = repository_pool
        self.policy = cleanup_policy
        self.cleanup_task: Optional[asyncio.Task] = None
        self.last_cleanup = datetime.utcnow()
        self.cleanup_stats = {
            "total_cleanups": 0,
            "repositories_removed": 0,
            "space_reclaimed_gb": 0.0,
            "branches_cleaned": 0,
            "errors_encountered": 0
        }
    
    async def start(self):
        """Start the automatic cleanup routine."""
        if self.cleanup_task is not None:
            logger.warning("Cleanup routine already running")
            return
        
        # Run initial cleanup if configured
        if self.policy.cleanup_on_startup:
            logger.info("Running startup cleanup")
            await self.run_cleanup()
        
        # Start periodic cleanup
        self.cleanup_task = asyncio.create_task(self._periodic_cleanup())
        logger.info(
            f"Started automatic cleanup routine "
            f"(interval: {self.policy.cleanup_interval_hours} hours)"
        )
    
    async def stop(self):
        """Stop the automatic cleanup routine."""
        if self.cleanup_task is not None:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            self.cleanup_task = None
            logger.info("Stopped automatic cleanup routine")
    
    async def _periodic_cleanup(self):
        """Run cleanup at regular intervals."""
        while True:
            try:
                await asyncio.sleep(self.policy.cleanup_interval_hours * 3600)
                await self.run_cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                self.cleanup_stats["errors_encountered"] += 1
    
    async def run_cleanup(self) -> Dict[str, any]:
        """Run a complete cleanup cycle.
        
        Returns:
            Dictionary with cleanup results
        """
        logger.info("Starting repository cleanup cycle")
        start_time = datetime.utcnow()
        results = {
            "started_at": start_time,
            "repositories_checked": 0,
            "repositories_removed": 0,
            "branches_cleaned": 0,
            "space_reclaimed_gb": 0.0,
            "errors": []
        }
        
        try:
            # Check disk space
            disk_usage = psutil.disk_usage(str(self.pool.base_path))
            free_space_gb = disk_usage.free / (1024 ** 3)
            
            if free_space_gb < self.policy.min_free_disk_space_gb:
                logger.warning(
                    f"Low disk space: {free_space_gb:.1f}GB free "
                    f"(minimum: {self.policy.min_free_disk_space_gb}GB)"
                )
            
            # Get all repositories
            repositories = list(self.pool.repositories.values())
            results["repositories_checked"] = len(repositories)
            
            # Apply cleanup policies
            repos_to_remove = await self._identify_repositories_for_cleanup(repositories)
            
            # Clean up repositories
            for repo_info in repos_to_remove:
                try:
                    size_before = repo_info.size_bytes
                    await self._cleanup_repository(repo_info)
                    results["repositories_removed"] += 1
                    results["space_reclaimed_gb"] += size_before / (1024 ** 3)
                except Exception as e:
                    logger.error(f"Failed to cleanup repository {repo_info.repository_key}: {e}")
                    results["errors"].append(str(e))
            
            # Clean up abandoned branches
            branches_cleaned = await self._cleanup_abandoned_branches()
            results["branches_cleaned"] = branches_cleaned
            
            # Update statistics
            self.cleanup_stats["total_cleanups"] += 1
            self.cleanup_stats["repositories_removed"] += results["repositories_removed"]
            self.cleanup_stats["space_reclaimed_gb"] += results["space_reclaimed_gb"]
            self.cleanup_stats["branches_cleaned"] += results["branches_cleaned"]
            self.last_cleanup = datetime.utcnow()
            
            results["completed_at"] = datetime.utcnow()
            results["duration_seconds"] = (results["completed_at"] - start_time).total_seconds()
            
            logger.info(
                f"Cleanup completed: removed {results['repositories_removed']} repositories, "
                f"reclaimed {results['space_reclaimed_gb']:.2f}GB, "
                f"cleaned {results['branches_cleaned']} branches"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Cleanup cycle failed: {e}")
            self.cleanup_stats["errors_encountered"] += 1
            results["errors"].append(str(e))
            return results
    
    async def _identify_repositories_for_cleanup(
        self,
        repositories: List[RepositoryInfo]
    ) -> List[RepositoryInfo]:
        """Identify repositories that should be cleaned up based on policies.
        
        Args:
            repositories: List of all repositories
            
        Returns:
            List of repositories to remove
        """
        repos_to_remove = []
        
        # Sort by priority for removal (oldest, least recently used, errors)
        sorted_repos = sorted(
            repositories,
            key=lambda r: (
                r.error_count,  # High error count first
                -r.inactive_hours,  # Most inactive first
                -r.age_hours,  # Oldest first
                r.size_bytes  # Largest first
            ),
            reverse=True
        )
        
        # Apply policies
        for repo in sorted_repos:
            should_remove = False
            reason = ""
            
            # Skip if repository is in use
            if repo.status == RepositoryStatus.IN_USE:
                continue
            
            # Skip if repository has active branches and policy says to retain
            if self.policy.retain_active_branches and repo.active_branches:
                continue
            
            # Check inactive time
            if repo.inactive_hours > self.policy.max_inactive_hours:
                should_remove = True
                reason = f"Inactive for {repo.inactive_hours:.1f} hours"
            
            # Check age
            elif repo.age_hours > self.policy.max_repository_age_hours:
                should_remove = True
                reason = f"Repository age {repo.age_hours:.1f} hours exceeds maximum"
            
            # Check error count
            elif repo.error_count >= self.policy.max_error_count:
                should_remove = True
                reason = f"Error count {repo.error_count} exceeds maximum"
            
            # Check total count limit
            elif len(repositories) - len(repos_to_remove) > self.policy.max_total_repositories:
                should_remove = True
                reason = "Repository count exceeds maximum"
            
            # Check total size limit
            elif self._calculate_total_size_gb(repositories) > self.policy.max_total_size_gb:
                should_remove = True
                reason = "Total size exceeds maximum"
            
            if should_remove:
                logger.info(f"Marking {repo.repository_key} for cleanup: {reason}")
                repos_to_remove.append(repo)
        
        return repos_to_remove
    
    async def _cleanup_repository(self, repo_info: RepositoryInfo):
        """Clean up a specific repository.
        
        Args:
            repo_info: Repository to clean up
        """
        logger.info(f"Cleaning up repository {repo_info.repository_key}")
        
        # Update status
        repo_info.status = RepositoryStatus.SCHEDULED_FOR_CLEANUP
        
        # Remove from pool
        await self.pool._remove_repository(repo_info.repository_key)
    
    async def _cleanup_abandoned_branches(self) -> int:
        """Clean up abandoned branches in active repositories.
        
        Returns:
            Number of branches cleaned
        """
        branches_cleaned = 0
        
        for repo_info in self.pool.repositories.values():
            if repo_info.status != RepositoryStatus.AVAILABLE:
                continue
            
            # Find abandoned workspaces
            abandoned_workspaces = [
                ws for ws in self.pool.workspaces.values()
                if (ws.repository_info.repository_key == repo_info.repository_key and
                    ws.status in [BranchStatus.FAILED, BranchStatus.ABANDONED])
            ]
            
            for workspace in abandoned_workspaces:
                try:
                    await self.pool._delete_branch(repo_info, workspace.branch_name)
                    repo_info.active_branches.discard(workspace.branch_name)
                    branches_cleaned += 1
                    logger.debug(f"Cleaned up abandoned branch {workspace.branch_name}")
                except Exception as e:
                    logger.error(f"Failed to clean up branch {workspace.branch_name}: {e}")
        
        return branches_cleaned
    
    def _calculate_total_size_gb(self, repositories: List[RepositoryInfo]) -> float:
        """Calculate total size of repositories in GB.
        
        Args:
            repositories: List of repositories
            
        Returns:
            Total size in GB
        """
        total_bytes = sum(repo.size_bytes for repo in repositories)
        return total_bytes / (1024 ** 3)
    
    async def force_cleanup_repository(self, repository_key: str) -> bool:
        """Force cleanup of a specific repository.
        
        Args:
            repository_key: Key of repository to clean up
            
        Returns:
            True if cleaned up successfully
        """
        if repository_key not in self.pool.repositories:
            logger.warning(f"Repository {repository_key} not found for cleanup")
            return False
        
        repo_info = self.pool.repositories[repository_key]
        
        try:
            await self._cleanup_repository(repo_info)
            return True
        except Exception as e:
            logger.error(f"Failed to force cleanup repository {repository_key}: {e}")
            return False
    
    def get_cleanup_statistics(self) -> Dict[str, any]:
        """Get cleanup statistics.
        
        Returns:
            Dictionary with cleanup statistics
        """
        return {
            **self.cleanup_stats,
            "last_cleanup": self.last_cleanup.isoformat() if self.last_cleanup else None,
            "next_cleanup": (
                self.last_cleanup + timedelta(hours=self.policy.cleanup_interval_hours)
            ).isoformat() if self.last_cleanup else None,
            "policy": {
                "max_inactive_hours": self.policy.max_inactive_hours,
                "max_repository_age_hours": self.policy.max_repository_age_hours,
                "max_total_repositories": self.policy.max_total_repositories,
                "max_total_size_gb": self.policy.max_total_size_gb,
                "cleanup_interval_hours": self.policy.cleanup_interval_hours
            }
        }