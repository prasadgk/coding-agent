"""Repository health monitoring and recovery system."""

import asyncio
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import psutil

from .models import (
    RepositoryInfo,
    RepositoryStatus,
    RepositoryStats,
    BranchStatus
)
from .pool import RepositoryPool
from ...utils.metrics import MetricsCollector


logger = logging.getLogger(__name__)


class RepositoryHealthMonitor:
    """Monitors repository health and performs recovery operations."""
    
    def __init__(
        self,
        repository_pool: RepositoryPool,
        check_interval_seconds: int = 300,
        metrics_collector: Optional[MetricsCollector] = None
    ):
        """Initialize the health monitor.
        
        Args:
            repository_pool: The repository pool to monitor
            check_interval_seconds: Interval between health checks
            metrics_collector: Optional metrics collector for reporting
        """
        self.pool = repository_pool
        self.check_interval_seconds = check_interval_seconds
        self.metrics = metrics_collector
        self.monitor_task: Optional[asyncio.Task] = None
        
        # Health check results
        self.last_check_time = datetime.utcnow()
        self.health_history: List[RepositoryStats] = []
        self.recovery_attempts: Dict[str, int] = {}
        self.health_issues: Dict[str, List[str]] = {}
    
    async def start(self):
        """Start the health monitoring routine."""
        if self.monitor_task is not None:
            logger.warning("Health monitor already running")
            return
        
        self.monitor_task = asyncio.create_task(self._periodic_health_check())
        logger.info(f"Started repository health monitor (interval: {self.check_interval_seconds}s)")
    
    async def stop(self):
        """Stop the health monitoring routine."""
        if self.monitor_task is not None:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            self.monitor_task = None
            logger.info("Stopped repository health monitor")
    
    async def _periodic_health_check(self):
        """Run health checks at regular intervals."""
        while True:
            try:
                await asyncio.sleep(self.check_interval_seconds)
                await self.check_all_repositories()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic health check: {e}")
    
    async def check_all_repositories(self) -> RepositoryStats:
        """Check health of all repositories in the pool.
        
        Returns:
            Repository statistics
        """
        logger.debug("Starting repository health check")
        start_time = datetime.utcnow()
        
        # Collect basic statistics
        stats = self._collect_pool_statistics()
        
        # Check individual repository health
        unhealthy_repos = []
        for repo_info in self.pool.repositories.values():
            issues = await self._check_repository_health(repo_info)
            if issues:
                unhealthy_repos.append((repo_info, issues))
                self.health_issues[repo_info.repository_key] = issues
            else:
                # Clear any previous issues
                if repo_info.repository_key in self.health_issues:
                    del self.health_issues[repo_info.repository_key]
        
        # Attempt recovery for unhealthy repositories
        for repo_info, issues in unhealthy_repos:
            await self._attempt_recovery(repo_info, issues)
        
        # Check system resources
        await self._check_system_resources()
        
        # Store health check results
        self.last_check_time = datetime.utcnow()
        self.health_history.append(stats)
        
        # Keep only last 24 hours of history
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        self.health_history = [
            s for s in self.health_history
            if s.timestamp > cutoff_time
        ]
        
        # Report metrics if available
        if self.metrics:
            await self._report_metrics(stats)
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.debug(f"Health check completed in {duration:.2f}s")
        
        return stats
    
    def _collect_pool_statistics(self) -> RepositoryStats:
        """Collect current pool statistics.
        
        Returns:
            Repository statistics
        """
        repositories = list(self.pool.repositories.values())
        
        total_size = sum(repo.size_bytes for repo in repositories)
        ages = [repo.age_hours for repo in repositories]
        
        # Calculate lock wait times
        total_wait_time = 0
        total_lock_count = 0
        for wait_times in self.pool.lock_wait_times.values():
            if wait_times:
                total_wait_time += sum(wait_times)
                total_lock_count += len(wait_times)
        
        avg_lock_wait = total_wait_time / total_lock_count if total_lock_count > 0 else 0
        
        return RepositoryStats(
            total_repositories=len(repositories),
            available_repositories=len([
                r for r in repositories
                if r.status == RepositoryStatus.AVAILABLE
            ]),
            in_use_repositories=len([
                r for r in repositories
                if r.status == RepositoryStatus.IN_USE
            ]),
            error_repositories=len([
                r for r in repositories
                if r.status == RepositoryStatus.ERROR
            ]),
            total_size_bytes=total_size,
            oldest_repository_age_hours=max(ages) if ages else 0,
            average_age_hours=sum(ages) / len(ages) if ages else 0,
            cache_hit_rate=(
                self.pool.cache_hits / self.pool.total_acquisitions
                if self.pool.total_acquisitions > 0 else 0
            ),
            average_lock_wait_time_seconds=avg_lock_wait,
            cleanup_operations_count=0,  # Would be tracked by cleaner
            failed_operations_count=sum(
                repo.error_count for repo in repositories
            )
        )
    
    async def _check_repository_health(
        self,
        repo_info: RepositoryInfo
    ) -> List[str]:
        """Check health of a specific repository.
        
        Args:
            repo_info: Repository to check
            
        Returns:
            List of health issues found
        """
        issues = []
        
        # Check if repository path exists
        if not repo_info.local_path.exists():
            issues.append("Repository path does not exist")
            return issues
        
        # Check git repository integrity
        try:
            process = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--git-dir",
                cwd=str(repo_info.local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            
            if process.returncode != 0:
                issues.append(f"Git repository integrity check failed: {stderr.decode()}")
        except Exception as e:
            issues.append(f"Failed to check git integrity: {e}")
        
        # Check for uncommitted changes
        try:
            process = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=str(repo_info.local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            
            if stdout.strip():
                issues.append("Repository has uncommitted changes")
        except Exception as e:
            issues.append(f"Failed to check git status: {e}")
        
        # Check repository size
        try:
            size_bytes = sum(
                f.stat().st_size for f in repo_info.local_path.rglob("*") if f.is_file()
            )
            repo_info.size_bytes = size_bytes  # Update size
            
            # Check if repository is unusually large
            if size_bytes > 1024 ** 3:  # 1GB
                issues.append(f"Repository is large: {size_bytes / (1024 ** 3):.1f}GB")
        except Exception as e:
            issues.append(f"Failed to check repository size: {e}")
        
        # Check for stuck locks
        if repo_info.repository_key in self.pool.lock_info:
            lock_info = self.pool.lock_info[repo_info.repository_key]
            if lock_info.is_expired:
                issues.append(f"Repository has expired lock from ticket {lock_info.ticket_id}")
        
        # Check error threshold
        if repo_info.error_count > 3:
            issues.append(f"High error count: {repo_info.error_count}")
        
        return issues
    
    async def _attempt_recovery(
        self,
        repo_info: RepositoryInfo,
        issues: List[str]
    ):
        """Attempt to recover an unhealthy repository.
        
        Args:
            repo_info: Repository to recover
            issues: List of issues found
        """
        repo_key = repo_info.repository_key
        
        # Track recovery attempts
        if repo_key not in self.recovery_attempts:
            self.recovery_attempts[repo_key] = 0
        
        self.recovery_attempts[repo_key] += 1
        
        # Don't attempt too many recoveries
        if self.recovery_attempts[repo_key] > 3:
            logger.error(
                f"Repository {repo_key} has failed {self.recovery_attempts[repo_key]} "
                "recovery attempts, marking for cleanup"
            )
            repo_info.status = RepositoryStatus.ERROR
            return
        
        logger.warning(
            f"Attempting recovery for repository {repo_key} "
            f"(attempt {self.recovery_attempts[repo_key]}): {issues}"
        )
        
        recovery_successful = True
        
        # Handle specific issues
        if "Repository path does not exist" in issues:
            # Re-clone the repository
            try:
                await self.pool._clone_repository(repo_info.repository_url, repo_key)
                logger.info(f"Successfully re-cloned repository {repo_key}")
            except Exception as e:
                logger.error(f"Failed to re-clone repository {repo_key}: {e}")
                recovery_successful = False
        
        if "Repository has uncommitted changes" in issues:
            # Clean uncommitted changes
            try:
                await self._clean_uncommitted_changes(repo_info)
                logger.info(f"Cleaned uncommitted changes in repository {repo_key}")
            except Exception as e:
                logger.error(f"Failed to clean uncommitted changes: {e}")
                recovery_successful = False
        
        if any("expired lock" in issue for issue in issues):
            # Force release expired locks
            if repo_key in self.pool.lock_info:
                lock_info = self.pool.lock_info[repo_key]
                await self.pool.lock_manager.release_lock(repo_key, lock_info.ticket_id)
                logger.info(f"Released expired lock for repository {repo_key}")
        
        if recovery_successful:
            # Reset error count on successful recovery
            repo_info.error_count = 0
            repo_info.status = RepositoryStatus.AVAILABLE
            self.recovery_attempts[repo_key] = 0
            logger.info(f"Successfully recovered repository {repo_key}")
        else:
            repo_info.status = RepositoryStatus.ERROR
    
    async def _clean_uncommitted_changes(self, repo_info: RepositoryInfo):
        """Clean uncommitted changes in a repository.
        
        Args:
            repo_info: Repository to clean
        """
        # Reset to clean state
        process = await asyncio.create_subprocess_exec(
            "git", "reset", "--hard", "HEAD",
            cwd=str(repo_info.local_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        # Clean untracked files
        process = await asyncio.create_subprocess_exec(
            "git", "clean", "-fd",
            cwd=str(repo_info.local_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
    
    async def _check_system_resources(self):
        """Check system resource availability."""
        # Check disk space
        disk_usage = psutil.disk_usage(str(self.pool.base_path))
        free_space_gb = disk_usage.free / (1024 ** 3)
        
        if free_space_gb < 5:
            logger.error(f"Critical: Low disk space - {free_space_gb:.1f}GB free")
        elif free_space_gb < 10:
            logger.warning(f"Warning: Low disk space - {free_space_gb:.1f}GB free")
        
        # Check memory usage
        memory = psutil.virtual_memory()
        if memory.percent > 90:
            logger.error(f"Critical: High memory usage - {memory.percent}%")
        elif memory.percent > 80:
            logger.warning(f"Warning: High memory usage - {memory.percent}%")
    
    async def _report_metrics(self, stats: RepositoryStats):
        """Report metrics to monitoring system.
        
        Args:
            stats: Repository statistics to report
        """
        if not self.metrics:
            return
        
        # Report pool metrics
        self.metrics.record_gauge("repository_pool.total", stats.total_repositories)
        self.metrics.record_gauge("repository_pool.available", stats.available_repositories)
        self.metrics.record_gauge("repository_pool.in_use", stats.in_use_repositories)
        self.metrics.record_gauge("repository_pool.errors", stats.error_repositories)
        self.metrics.record_gauge("repository_pool.size_gb", stats.total_size_bytes / (1024 ** 3))
        self.metrics.record_gauge("repository_pool.cache_hit_rate", stats.cache_hit_rate)
        self.metrics.record_gauge(
            "repository_pool.avg_lock_wait_seconds",
            stats.average_lock_wait_time_seconds
        )
        
        # Report health issues
        total_issues = sum(len(issues) for issues in self.health_issues.values())
        self.metrics.record_gauge("repository_pool.health_issues", total_issues)
    
    def get_health_summary(self) -> Dict[str, any]:
        """Get current health summary.
        
        Returns:
            Dictionary with health information
        """
        current_stats = self._collect_pool_statistics()
        
        return {
            "last_check_time": self.last_check_time.isoformat(),
            "current_stats": {
                "total_repositories": current_stats.total_repositories,
                "available_repositories": current_stats.available_repositories,
                "in_use_repositories": current_stats.in_use_repositories,
                "error_repositories": current_stats.error_repositories,
                "cache_hit_rate": f"{current_stats.cache_hit_rate * 100:.1f}%",
                "total_size_gb": f"{current_stats.total_size_bytes / (1024 ** 3):.2f}"
            },
            "health_issues": dict(self.health_issues),
            "recovery_attempts": dict(self.recovery_attempts),
            "pool_statistics": self.pool.get_statistics()
        }