"""Repository pool management for efficient workspace handling."""

import asyncio
import logging
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .models import (
    RepositoryInfo,
    RepositoryWorkspace,
    RepositoryStatus,
    BranchStatus,
    RepositoryLockInfo,
    CleanupPolicy
)
from ...utils.exceptions import (
    RepositoryError,
    RepositoryLockError,
    RepositoryNotFoundError
)


logger = logging.getLogger(__name__)


class RepositoryPool:
    """Manages a pool of persistent repository clones for optimal resource usage."""
    
    def __init__(
        self,
        base_path: Path,
        max_repositories: int = 50,
        lock_timeout_seconds: int = 300,
        cleanup_policy: Optional[CleanupPolicy] = None
    ):
        """Initialize repository pool.
        
        Args:
            base_path: Base directory for storing repository clones
            max_repositories: Maximum number of repositories to maintain
            lock_timeout_seconds: Default timeout for repository locks
            cleanup_policy: Cleanup policy configuration
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        self.max_repositories = max_repositories
        self.lock_timeout_seconds = lock_timeout_seconds
        self.cleanup_policy = cleanup_policy or CleanupPolicy()
        
        # Repository tracking
        self.repositories: Dict[str, RepositoryInfo] = {}
        self.workspaces: Dict[str, RepositoryWorkspace] = {}
        
        # Locking mechanism
        self.repository_locks: Dict[str, asyncio.Lock] = {}
        self.lock_info: Dict[str, RepositoryLockInfo] = {}
        
        # Statistics
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_acquisitions = 0
        
    def _normalize_repository_url(self, url: str) -> str:
        """Normalize repository URL for consistent identification."""
        # Remove protocol variations and trailing slashes
        parsed = urlparse(url.lower())
        
        # Remove .git extension if present
        path = parsed.path.rstrip('/')
        if path.endswith('.git'):
            path = path[:-4]
        
        # Construct normalized key
        return f"{parsed.netloc}{path}".replace('/', '_')
    
    def _get_repository_path(self, repository_key: str) -> Path:
        """Get local path for a repository."""
        return self.base_path / repository_key
    
    async def acquire_repository(
        self,
        repository_url: str,
        ticket_id: str,
        branch_name: Optional[str] = None,
        base_branch: str = "main"
    ) -> RepositoryWorkspace:
        """Acquire a repository workspace for a specific ticket.
        
        Args:
            repository_url: URL of the repository
            ticket_id: Ticket ID requesting the workspace
            branch_name: Optional branch name (will be created if not exists)
            base_branch: Base branch to create new branches from
            
        Returns:
            RepositoryWorkspace instance
            
        Raises:
            RepositoryError: If repository cannot be acquired
            RepositoryLockError: If lock cannot be acquired
        """
        repository_key = self._normalize_repository_url(repository_url)
        self.total_acquisitions += 1
        
        # Ensure we have a lock for this repository
        if repository_key not in self.repository_locks:
            self.repository_locks[repository_key] = asyncio.Lock()
        
        # Try to acquire lock with timeout
        try:
            async with asyncio.timeout(self.lock_timeout_seconds):
                async with self.repository_locks[repository_key]:
                    # Create lock info
                    lock_info = RepositoryLockInfo(
                        repository_key=repository_key,
                        ticket_id=ticket_id,
                        acquired_at=datetime.utcnow(),
                        expires_at=datetime.utcnow() + timedelta(seconds=self.lock_timeout_seconds)
                    )
                    self.lock_info[repository_key] = lock_info
                    
                    try:
                        # Check if repository exists in pool
                        if repository_key in self.repositories:
                            repo_info = self.repositories[repository_key]
                            workspace = await self._reuse_repository(
                                repo_info, ticket_id, branch_name, base_branch
                            )
                            self.cache_hits += 1
                        else:
                            # Check if we need to make space
                            if len(self.repositories) >= self.max_repositories:
                                await self._evict_repository()
                            
                            # Clone new repository
                            repo_info = await self._clone_repository(
                                repository_url, repository_key
                            )
                            self.repositories[repository_key] = repo_info
                            workspace = await self._create_workspace(
                                repo_info, ticket_id, branch_name, base_branch
                            )
                            self.cache_misses += 1
                        
                        self.workspaces[workspace.workspace_id] = workspace
                        return workspace
                        
                    finally:
                        # Release lock info
                        if repository_key in self.lock_info:
                            del self.lock_info[repository_key]
                            
        except asyncio.TimeoutError:
            raise RepositoryLockError(
                f"Failed to acquire lock for repository {repository_key} within {self.lock_timeout_seconds}s"
            )
    
    async def _reuse_repository(
        self,
        repo_info: RepositoryInfo,
        ticket_id: str,
        branch_name: Optional[str],
        base_branch: str
    ) -> RepositoryWorkspace:
        """Reuse an existing repository for a new workspace."""
        logger.info(f"Reusing repository {repo_info.repository_key} for ticket {ticket_id}")
        
        # Update repository status
        repo_info.status = RepositoryStatus.UPDATING
        
        try:
            # Update repository to latest
            await self._update_repository(repo_info, base_branch)
            
            # Create workspace
            workspace = await self._create_workspace(
                repo_info, ticket_id, branch_name, base_branch
            )
            
            # Update repository info
            repo_info.status = RepositoryStatus.IN_USE
            repo_info.last_accessed = datetime.utcnow()
            
            return workspace
            
        except Exception as e:
            repo_info.status = RepositoryStatus.ERROR
            repo_info.error_count += 1
            repo_info.last_error = str(e)
            raise RepositoryError(f"Failed to reuse repository: {e}")
    
    async def _clone_repository(
        self,
        repository_url: str,
        repository_key: str
    ) -> RepositoryInfo:
        """Clone a new repository."""
        logger.info(f"Cloning repository {repository_url}")
        
        local_path = self._get_repository_path(repository_key)
        
        try:
            # Clone repository
            process = await asyncio.create_subprocess_exec(
                "git", "clone", repository_url, str(local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise RepositoryError(f"Git clone failed: {stderr.decode()}")
            
            # Get repository size
            size_bytes = sum(
                f.stat().st_size for f in local_path.rglob("*") if f.is_file()
            )
            
            # Create repository info
            now = datetime.utcnow()
            repo_info = RepositoryInfo(
                repository_url=repository_url,
                repository_key=repository_key,
                local_path=local_path,
                status=RepositoryStatus.AVAILABLE,
                last_accessed=now,
                last_updated=now,
                clone_date=now,
                size_bytes=size_bytes
            )
            
            return repo_info
            
        except Exception as e:
            # Clean up on failure
            if local_path.exists():
                shutil.rmtree(local_path, ignore_errors=True)
            raise RepositoryError(f"Failed to clone repository: {e}")
    
    async def _update_repository(self, repo_info: RepositoryInfo, base_branch: str):
        """Update repository to latest state."""
        logger.debug(f"Updating repository {repo_info.repository_key}")
        
        try:
            # Fetch latest changes
            process = await asyncio.create_subprocess_exec(
                "git", "fetch", "origin",
                cwd=str(repo_info.local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            # Checkout base branch
            process = await asyncio.create_subprocess_exec(
                "git", "checkout", base_branch,
                cwd=str(repo_info.local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            # Pull latest changes
            process = await asyncio.create_subprocess_exec(
                "git", "pull", "origin", base_branch,
                cwd=str(repo_info.local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise RepositoryError(f"Git pull failed: {stderr.decode()}")
            
            repo_info.last_updated = datetime.utcnow()
            
        except Exception as e:
            raise RepositoryError(f"Failed to update repository: {e}")
    
    async def _create_workspace(
        self,
        repo_info: RepositoryInfo,
        ticket_id: str,
        branch_name: Optional[str],
        base_branch: str
    ) -> RepositoryWorkspace:
        """Create a workspace for a specific ticket."""
        if not branch_name:
            branch_name = f"feature/{ticket_id}"
        
        try:
            # Create and checkout new branch
            process = await asyncio.create_subprocess_exec(
                "git", "checkout", "-b", branch_name, f"origin/{base_branch}",
                cwd=str(repo_info.local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            # If branch already exists, just check it out
            if process.returncode != 0 and "already exists" in stderr.decode():
                process = await asyncio.create_subprocess_exec(
                    "git", "checkout", branch_name,
                    cwd=str(repo_info.local_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
            
            # Add branch to active branches
            repo_info.active_branches.add(branch_name)
            
            # Create workspace
            workspace = RepositoryWorkspace(
                workspace_id="",  # Will be auto-generated
                repository_info=repo_info,
                ticket_id=ticket_id,
                branch_name=branch_name,
                workspace_path=repo_info.local_path,
                created_at=datetime.utcnow(),
                status=BranchStatus.ACTIVE,
                lock_acquired_at=datetime.utcnow()
            )
            
            return workspace
            
        except Exception as e:
            raise RepositoryError(f"Failed to create workspace: {e}")
    
    async def release_workspace(self, workspace_id: str, cleanup_branch: bool = False):
        """Release a workspace back to the pool.
        
        Args:
            workspace_id: ID of the workspace to release
            cleanup_branch: Whether to delete the branch
        """
        if workspace_id not in self.workspaces:
            raise RepositoryNotFoundError(f"Workspace {workspace_id} not found")
        
        workspace = self.workspaces[workspace_id]
        repo_info = workspace.repository_info
        
        try:
            if cleanup_branch:
                # Delete the branch
                await self._delete_branch(repo_info, workspace.branch_name)
                repo_info.active_branches.discard(workspace.branch_name)
            
            # Update workspace status
            workspace.status = BranchStatus.COMPLETED
            workspace.lock_acquired_at = None
            
            # Update repository status
            if not repo_info.active_branches:
                repo_info.status = RepositoryStatus.AVAILABLE
            
            logger.info(f"Released workspace {workspace_id} for repository {repo_info.repository_key}")
            
        except Exception as e:
            logger.error(f"Error releasing workspace: {e}")
            workspace.status = BranchStatus.FAILED
    
    async def _delete_branch(self, repo_info: RepositoryInfo, branch_name: str):
        """Delete a branch from the repository."""
        try:
            # Checkout main/master first
            process = await asyncio.create_subprocess_exec(
                "git", "checkout", "main",
                cwd=str(repo_info.local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            # Delete the branch
            process = await asyncio.create_subprocess_exec(
                "git", "branch", "-D", branch_name,
                cwd=str(repo_info.local_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
        except Exception as e:
            logger.warning(f"Failed to delete branch {branch_name}: {e}")
    
    async def _evict_repository(self):
        """Evict least recently used repository to make space."""
        if not self.repositories:
            return
        
        # Find LRU repository that's available
        lru_repo = None
        for repo in sorted(
            self.repositories.values(),
            key=lambda r: r.last_accessed
        ):
            if repo.status == RepositoryStatus.AVAILABLE:
                lru_repo = repo
                break
        
        if lru_repo:
            logger.info(f"Evicting repository {lru_repo.repository_key}")
            await self._remove_repository(lru_repo.repository_key)
    
    async def _remove_repository(self, repository_key: str):
        """Remove a repository from the pool."""
        if repository_key not in self.repositories:
            return
        
        repo_info = self.repositories[repository_key]
        
        # Remove from disk
        if repo_info.local_path.exists():
            shutil.rmtree(repo_info.local_path, ignore_errors=True)
        
        # Remove from tracking
        del self.repositories[repository_key]
        
        # Remove associated workspaces
        workspace_ids_to_remove = [
            ws_id for ws_id, ws in self.workspaces.items()
            if ws.repository_info.repository_key == repository_key
        ]
        for ws_id in workspace_ids_to_remove:
            del self.workspaces[ws_id]
    
    def get_statistics(self) -> Dict[str, any]:
        """Get pool statistics."""
        total_size = sum(repo.size_bytes for repo in self.repositories.values())
        cache_hit_rate = (
            self.cache_hits / self.total_acquisitions
            if self.total_acquisitions > 0 else 0
        )
        
        return {
            "total_repositories": len(self.repositories),
            "available_repositories": len([
                r for r in self.repositories.values()
                if r.status == RepositoryStatus.AVAILABLE
            ]),
            "in_use_repositories": len([
                r for r in self.repositories.values()
                if r.status == RepositoryStatus.IN_USE
            ]),
            "total_size_gb": total_size / (1024 ** 3),
            "cache_hit_rate": cache_hit_rate,
            "total_acquisitions": self.total_acquisitions,
            "active_workspaces": len([
                ws for ws in self.workspaces.values()
                if ws.status == BranchStatus.ACTIVE
            ])
        }