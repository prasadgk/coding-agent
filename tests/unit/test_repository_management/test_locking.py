"""Tests for repository locking mechanisms."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.core.repository_management.locking import (
    DistributedLockManager,
    LocalLockManager
)
from src.core.repository_management.models import RepositoryLockInfo
from src.utils.exceptions import RepositoryLockError


class TestDistributedLockManager:
    """Test DistributedLockManager functionality."""
    
    @pytest.fixture
    def lock_manager(self):
        """Create a lock manager instance."""
        return DistributedLockManager(default_timeout_seconds=5)
    
    @pytest.mark.asyncio
    async def test_acquire_new_lock(self, lock_manager):
        """Test acquiring a new lock."""
        lock_info = await lock_manager.acquire_lock(
            repository_key="test_repo",
            ticket_id="TICKET-123",
            timeout_seconds=10
        )
        
        assert lock_info.repository_key == "test_repo"
        assert lock_info.ticket_id == "TICKET-123"
        assert not lock_info.is_expired
        assert lock_info.time_remaining_seconds > 9
        assert "test_repo" in lock_manager.locks
        assert "TICKET-123" in lock_manager.active_tickets_per_repo["test_repo"]
    
    @pytest.mark.asyncio
    async def test_extend_existing_lock_same_ticket(self, lock_manager):
        """Test extending a lock for the same ticket."""
        # Acquire initial lock
        lock1 = await lock_manager.acquire_lock(
            repository_key="test_repo",
            ticket_id="TICKET-123",
            timeout_seconds=5
        )
        
        initial_expiry = lock1.expires_at
        
        # Acquire again with same ticket (should extend)
        lock2 = await lock_manager.acquire_lock(
            repository_key="test_repo",
            ticket_id="TICKET-123",
            timeout_seconds=10
        )
        
        assert lock2.lock_id == lock1.lock_id  # Same lock
        assert lock2.expires_at > initial_expiry
    
    @pytest.mark.asyncio
    async def test_wait_for_lock_release(self, lock_manager):
        """Test waiting for lock release."""
        # Acquire lock for first ticket
        await lock_manager.acquire_lock(
            repository_key="test_repo",
            ticket_id="TICKET-123",
            timeout_seconds=1
        )
        
        # Try to acquire for second ticket in background
        async def acquire_second():
            return await lock_manager.acquire_lock(
                repository_key="test_repo",
                ticket_id="TICKET-456",
                timeout_seconds=5
            )
        
        # Start acquisition in background
        task = asyncio.create_task(acquire_second())
        
        # Wait a bit then release first lock
        await asyncio.sleep(0.1)
        await lock_manager.release_lock("test_repo", "TICKET-123")
        
        # Second acquisition should succeed
        lock2 = await task
        assert lock2.ticket_id == "TICKET-456"
    
    @pytest.mark.asyncio
    async def test_lock_timeout_while_waiting(self, lock_manager):
        """Test timeout while waiting for lock."""
        # Acquire lock for first ticket with long timeout
        await lock_manager.acquire_lock(
            repository_key="test_repo",
            ticket_id="TICKET-123",
            timeout_seconds=10
        )
        
        # Try to acquire for second ticket with short timeout
        with pytest.raises(RepositoryLockError) as exc_info:
            await lock_manager.acquire_lock(
                repository_key="test_repo",
                ticket_id="TICKET-456",
                timeout_seconds=0.1  # Very short timeout
            )
        
        assert "Timeout waiting for lock" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_release_lock(self, lock_manager):
        """Test releasing a lock."""
        # Acquire lock
        await lock_manager.acquire_lock(
            repository_key="test_repo",
            ticket_id="TICKET-123"
        )
        
        # Release lock
        await lock_manager.release_lock("test_repo", "TICKET-123")
        
        assert "test_repo" not in lock_manager.locks
        assert "TICKET-123" not in lock_manager.active_tickets_per_repo["test_repo"]
    
    @pytest.mark.asyncio
    async def test_release_nonexistent_lock(self, lock_manager):
        """Test releasing a non-existent lock."""
        # Should not raise error, just log warning
        await lock_manager.release_lock("nonexistent_repo", "TICKET-999")
    
    @pytest.mark.asyncio
    async def test_release_lock_wrong_ticket(self, lock_manager):
        """Test releasing a lock with wrong ticket ID."""
        # Acquire lock
        await lock_manager.acquire_lock(
            repository_key="test_repo",
            ticket_id="TICKET-123"
        )
        
        # Try to release with different ticket
        await lock_manager.release_lock("test_repo", "TICKET-456")
        
        # Lock should still exist
        assert "test_repo" in lock_manager.locks
    
    @pytest.mark.asyncio
    async def test_extend_lock(self, lock_manager):
        """Test extending an existing lock."""
        # Acquire lock
        lock = await lock_manager.acquire_lock(
            repository_key="test_repo",
            ticket_id="TICKET-123",
            timeout_seconds=5
        )
        
        initial_expiry = lock.expires_at
        
        # Extend lock
        success = await lock_manager.extend_lock(
            repository_key="test_repo",
            ticket_id="TICKET-123",
            additional_seconds=10
        )
        
        assert success
        assert lock_manager.locks["test_repo"].expires_at > initial_expiry
    
    @pytest.mark.asyncio
    async def test_extend_expired_lock(self, lock_manager):
        """Test extending an expired lock."""
        # Create expired lock manually
        past = datetime.utcnow() - timedelta(seconds=60)
        lock = RepositoryLockInfo(
            repository_key="test_repo",
            ticket_id="TICKET-123",
            acquired_at=past - timedelta(seconds=300),
            expires_at=past
        )
        lock_manager.locks["test_repo"] = lock
        
        # Try to extend
        success = await lock_manager.extend_lock(
            repository_key="test_repo",
            ticket_id="TICKET-123",
            additional_seconds=10
        )
        
        assert not success
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_locks(self, lock_manager):
        """Test cleaning up expired locks."""
        # Create mix of valid and expired locks
        now = datetime.utcnow()
        
        # Valid lock
        lock_manager.locks["repo1"] = RepositoryLockInfo(
            repository_key="repo1",
            ticket_id="TICKET-1",
            acquired_at=now,
            expires_at=now + timedelta(seconds=300)
        )
        
        # Expired lock
        lock_manager.locks["repo2"] = RepositoryLockInfo(
            repository_key="repo2",
            ticket_id="TICKET-2",
            acquired_at=now - timedelta(seconds=600),
            expires_at=now - timedelta(seconds=300)
        )
        
        # Clean up
        cleaned = await lock_manager.cleanup_expired_locks()
        
        assert cleaned == 1
        assert "repo1" in lock_manager.locks
        assert "repo2" not in lock_manager.locks
    
    def test_get_lock_statistics(self, lock_manager):
        """Test getting lock statistics."""
        # Add some data
        lock_manager.locks["repo1"] = Mock()
        lock_manager.lock_waiters["repo2"].put_nowait((0, "ticket1", Mock()))
        lock_manager.lock_wait_times["repo1"] = [1.5, 2.0, 3.5]
        lock_manager.lock_acquisition_count["repo1"] = 3
        lock_manager.lock_timeout_count["repo2"] = 2
        lock_manager.active_tickets_per_repo["repo1"] = {"T1", "T2"}
        
        stats = lock_manager.get_lock_statistics()
        
        assert stats["active_locks"] == 1
        assert stats["repositories_with_waiters"] == 1
        assert stats["average_wait_times"]["repo1"] == 7.0 / 3
        assert stats["lock_acquisition_counts"]["repo1"] == 3
        assert stats["lock_timeout_counts"]["repo2"] == 2
        assert stats["active_tickets_per_repo"]["repo1"] == 2
    
    @pytest.mark.asyncio
    async def test_priority_based_waiting(self, lock_manager):
        """Test priority-based lock acquisition."""
        # Acquire initial lock
        await lock_manager.acquire_lock(
            repository_key="test_repo",
            ticket_id="TICKET-HOLDER"
        )
        
        # Queue multiple waiters with different priorities
        tasks = []
        results = []
        
        async def acquire_with_priority(ticket_id, priority):
            try:
                lock = await lock_manager.acquire_lock(
                    repository_key="test_repo",
                    ticket_id=ticket_id,
                    priority=priority,
                    timeout_seconds=5
                )
                results.append((ticket_id, priority))
                await lock_manager.release_lock("test_repo", ticket_id)
            except Exception:
                pass
        
        # Start tasks with different priorities
        tasks.append(asyncio.create_task(acquire_with_priority("LOW", 1)))
        await asyncio.sleep(0.01)
        tasks.append(asyncio.create_task(acquire_with_priority("HIGH", 10)))
        await asyncio.sleep(0.01)
        tasks.append(asyncio.create_task(acquire_with_priority("MED", 5)))
        
        # Release initial lock
        await asyncio.sleep(0.1)
        await lock_manager.release_lock("test_repo", "TICKET-HOLDER")
        
        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # High priority should be processed first
        if results:
            assert results[0][0] == "HIGH"


class TestLocalLockManager:
    """Test LocalLockManager functionality."""
    
    @pytest.fixture
    def local_manager(self):
        """Create a local lock manager instance."""
        return LocalLockManager()
    
    @pytest.mark.asyncio
    async def test_acquire_local_lock(self, local_manager):
        """Test acquiring a local lock."""
        lock = await local_manager.acquire("test_repo", "TICKET-123")
        
        assert isinstance(lock, asyncio.Lock)
        assert lock.locked()
        assert local_manager.lock_holders["test_repo"] == "TICKET-123"
    
    @pytest.mark.asyncio
    async def test_release_local_lock(self, local_manager):
        """Test releasing a local lock."""
        # Acquire lock
        lock = await local_manager.acquire("test_repo", "TICKET-123")
        
        # Release lock
        local_manager.release("test_repo", "TICKET-123")
        
        assert not lock.locked()
        assert "test_repo" not in local_manager.lock_holders
    
    @pytest.mark.asyncio
    async def test_concurrent_local_locks(self, local_manager):
        """Test concurrent access to local locks."""
        results = []
        
        async def access_with_lock(ticket_id):
            lock = await local_manager.acquire("test_repo", ticket_id)
            results.append(f"start_{ticket_id}")
            await asyncio.sleep(0.01)
            results.append(f"end_{ticket_id}")
            local_manager.release("test_repo", ticket_id)
        
        # Run concurrently
        await asyncio.gather(
            access_with_lock("TICKET-1"),
            access_with_lock("TICKET-2")
        )
        
        # Should be serialized
        assert results == ["start_TICKET-1", "end_TICKET-1", "start_TICKET-2", "end_TICKET-2"]