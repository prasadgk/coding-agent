"""Advanced locking mechanisms for repository concurrent access control."""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
import uuid

from .models import RepositoryLockInfo
from ...utils.exceptions import RepositoryLockError


logger = logging.getLogger(__name__)


class DistributedLockManager:
    """Manages distributed locks for repository access across multiple workers."""
    
    def __init__(self, default_timeout_seconds: int = 300):
        """Initialize the distributed lock manager.
        
        Args:
            default_timeout_seconds: Default timeout for locks
        """
        self.default_timeout_seconds = default_timeout_seconds
        
        # In-memory lock tracking (in production, use Redis or similar)
        self.locks: Dict[str, RepositoryLockInfo] = {}
        self.lock_waiters: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.active_tickets_per_repo: Dict[str, Set[str]] = defaultdict(set)
        
        # Lock acquisition metrics
        self.lock_wait_times: Dict[str, list] = defaultdict(list)
        self.lock_acquisition_count: Dict[str, int] = defaultdict(int)
        self.lock_timeout_count: Dict[str, int] = defaultdict(int)
    
    async def acquire_lock(
        self,
        repository_key: str,
        ticket_id: str,
        timeout_seconds: Optional[int] = None,
        priority: int = 0
    ) -> RepositoryLockInfo:
        """Acquire a lock for a repository.
        
        Args:
            repository_key: Unique key for the repository
            ticket_id: ID of the ticket requesting the lock
            timeout_seconds: Lock timeout (uses default if None)
            priority: Priority for lock acquisition (higher = more priority)
            
        Returns:
            RepositoryLockInfo instance
            
        Raises:
            RepositoryLockError: If lock cannot be acquired
        """
        timeout = timeout_seconds or self.default_timeout_seconds
        start_time = datetime.utcnow()
        
        # Check if we already have an active lock
        if repository_key in self.locks:
            existing_lock = self.locks[repository_key]
            
            # If lock is expired, we can take it
            if existing_lock.is_expired:
                logger.warning(
                    f"Forcefully taking expired lock for {repository_key} "
                    f"(was held by ticket {existing_lock.ticket_id})"
                )
                await self.release_lock(repository_key, existing_lock.ticket_id)
            
            # If same ticket already has the lock, extend it
            elif existing_lock.ticket_id == ticket_id:
                existing_lock.expires_at = datetime.utcnow() + timedelta(seconds=timeout)
                logger.debug(f"Extended lock for {repository_key} by ticket {ticket_id}")
                return existing_lock
            
            # Otherwise, we need to wait
            else:
                logger.info(
                    f"Ticket {ticket_id} waiting for lock on {repository_key} "
                    f"(currently held by {existing_lock.ticket_id})"
                )
                
                # Add to wait queue
                waiter_event = asyncio.Event()
                await self.lock_waiters[repository_key].put((priority, ticket_id, waiter_event))
                
                # Wait for our turn
                try:
                    await asyncio.wait_for(waiter_event.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    self.lock_timeout_count[repository_key] += 1
                    raise RepositoryLockError(
                        f"Timeout waiting for lock on {repository_key} after {timeout}s"
                    )
        
        # Create new lock
        lock_info = RepositoryLockInfo(
            repository_key=repository_key,
            ticket_id=ticket_id,
            acquired_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=timeout)
        )
        
        self.locks[repository_key] = lock_info
        self.active_tickets_per_repo[repository_key].add(ticket_id)
        
        # Track metrics
        wait_time = (datetime.utcnow() - start_time).total_seconds()
        self.lock_wait_times[repository_key].append(wait_time)
        self.lock_acquisition_count[repository_key] += 1
        
        logger.info(
            f"Lock acquired for {repository_key} by ticket {ticket_id} "
            f"(waited {wait_time:.1f}s)"
        )
        
        return lock_info
    
    async def release_lock(self, repository_key: str, ticket_id: str):
        """Release a lock for a repository.
        
        Args:
            repository_key: Unique key for the repository
            ticket_id: ID of the ticket releasing the lock
        """
        if repository_key not in self.locks:
            logger.warning(f"Attempted to release non-existent lock for {repository_key}")
            return
        
        lock_info = self.locks[repository_key]
        
        # Verify the ticket owns the lock
        if lock_info.ticket_id != ticket_id:
            logger.warning(
                f"Ticket {ticket_id} attempted to release lock for {repository_key} "
                f"owned by {lock_info.ticket_id}"
            )
            return
        
        # Remove lock
        del self.locks[repository_key]
        self.active_tickets_per_repo[repository_key].discard(ticket_id)
        
        logger.info(f"Lock released for {repository_key} by ticket {ticket_id}")
        
        # Process waiting tickets
        await self._process_lock_waiters(repository_key)
    
    async def _process_lock_waiters(self, repository_key: str):
        """Process waiting tickets for a repository lock."""
        if repository_key not in self.lock_waiters:
            return
        
        queue = self.lock_waiters[repository_key]
        
        if queue.empty():
            return
        
        # Get highest priority waiter
        waiters = []
        while not queue.empty():
            try:
                waiter = queue.get_nowait()
                waiters.append(waiter)
            except asyncio.QueueEmpty:
                break
        
        if waiters:
            # Sort by priority (descending) then by order
            waiters.sort(key=lambda x: (-x[0], x[1]))
            
            # Signal the first waiter
            priority, ticket_id, event = waiters[0]
            event.set()
            logger.debug(f"Signaled ticket {ticket_id} to acquire lock for {repository_key}")
            
            # Put the rest back in queue
            for waiter in waiters[1:]:
                await queue.put(waiter)
    
    async def extend_lock(
        self,
        repository_key: str,
        ticket_id: str,
        additional_seconds: int
    ) -> bool:
        """Extend an existing lock.
        
        Args:
            repository_key: Unique key for the repository
            ticket_id: ID of the ticket holding the lock
            additional_seconds: Seconds to add to current expiration
            
        Returns:
            True if lock was extended, False otherwise
        """
        if repository_key not in self.locks:
            return False
        
        lock_info = self.locks[repository_key]
        
        if lock_info.ticket_id != ticket_id:
            logger.warning(
                f"Ticket {ticket_id} attempted to extend lock for {repository_key} "
                f"owned by {lock_info.ticket_id}"
            )
            return False
        
        if lock_info.is_expired:
            logger.warning(f"Cannot extend expired lock for {repository_key}")
            return False
        
        lock_info.expires_at += timedelta(seconds=additional_seconds)
        logger.debug(
            f"Extended lock for {repository_key} by {additional_seconds}s "
            f"(new expiration: {lock_info.expires_at})"
        )
        
        return True
    
    async def check_lock_health(self, repository_key: str) -> Optional[RepositoryLockInfo]:
        """Check the health of a lock and clean up if expired.
        
        Args:
            repository_key: Unique key for the repository
            
        Returns:
            Current lock info if healthy, None if expired/not found
        """
        if repository_key not in self.locks:
            return None
        
        lock_info = self.locks[repository_key]
        
        if lock_info.is_expired:
            logger.warning(
                f"Cleaning up expired lock for {repository_key} "
                f"(was held by ticket {lock_info.ticket_id})"
            )
            await self.release_lock(repository_key, lock_info.ticket_id)
            return None
        
        return lock_info
    
    def get_lock_statistics(self) -> Dict[str, any]:
        """Get lock manager statistics."""
        stats = {
            "active_locks": len(self.locks),
            "total_waiters": sum(q.qsize() for q in self.lock_waiters.values()),
            "repositories_with_waiters": len([q for q in self.lock_waiters.values() if not q.empty()]),
            "average_wait_times": {},
            "lock_acquisition_counts": dict(self.lock_acquisition_count),
            "lock_timeout_counts": dict(self.lock_timeout_count),
            "active_tickets_per_repo": {
                k: len(v) for k, v in self.active_tickets_per_repo.items()
            }
        }
        
        # Calculate average wait times
        for repo_key, wait_times in self.lock_wait_times.items():
            if wait_times:
                stats["average_wait_times"][repo_key] = sum(wait_times) / len(wait_times)
        
        return stats
    
    async def cleanup_expired_locks(self):
        """Clean up all expired locks."""
        repository_keys = list(self.locks.keys())
        cleaned_count = 0
        
        for repo_key in repository_keys:
            lock_info = await self.check_lock_health(repo_key)
            if lock_info is None:
                cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} expired locks")
        
        return cleaned_count


class LocalLockManager:
    """Simple local lock manager using asyncio locks."""
    
    def __init__(self):
        """Initialize the local lock manager."""
        self.locks: Dict[str, asyncio.Lock] = {}
        self.lock_holders: Dict[str, str] = {}  # repo_key -> ticket_id
    
    async def acquire(self, repository_key: str, ticket_id: str) -> asyncio.Lock:
        """Acquire a local asyncio lock.
        
        Args:
            repository_key: Unique key for the repository
            ticket_id: ID of the ticket requesting the lock
            
        Returns:
            asyncio.Lock instance
        """
        if repository_key not in self.locks:
            self.locks[repository_key] = asyncio.Lock()
        
        lock = self.locks[repository_key]
        await lock.acquire()
        self.lock_holders[repository_key] = ticket_id
        
        return lock
    
    def release(self, repository_key: str, ticket_id: str):
        """Release a local lock.
        
        Args:
            repository_key: Unique key for the repository
            ticket_id: ID of the ticket releasing the lock
        """
        if repository_key in self.locks and repository_key in self.lock_holders:
            if self.lock_holders[repository_key] == ticket_id:
                lock = self.locks[repository_key]
                if lock.locked():
                    lock.release()
                del self.lock_holders[repository_key]