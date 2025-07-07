"""Retry and error handling utilities."""

import asyncio
import functools
import random
from typing import TypeVar, Callable, Optional, Union, Type, Tuple, Any
from datetime import datetime, timedelta
import logging

from .exceptions import IntegrationError, AuthenticationError, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Tuple[Type[Exception], ...] = (IntegrationError,),
        non_retryable_exceptions: Tuple[Type[Exception], ...] = (
            AuthenticationError,
            ValidationError,
        )
    ):
        """Initialize retry configuration.
        
        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Base delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            exponential_base: Base for exponential backoff
            jitter: Whether to add random jitter to delays
            retryable_exceptions: Exceptions that should trigger retry
            non_retryable_exceptions: Exceptions that should not be retried
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions
        self.non_retryable_exceptions = non_retryable_exceptions


class RetryManager:
    """Manages retry logic with exponential backoff and jitter."""
    
    def __init__(self, config: Optional[RetryConfig] = None):
        """Initialize retry manager.
        
        Args:
            config: Retry configuration (uses defaults if not provided)
        """
        self.config = config or RetryConfig()
        
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number.
        
        Args:
            attempt: Current attempt number (0-based)
            
        Returns:
            Delay in seconds
        """
        # Exponential backoff
        delay = min(
            self.config.base_delay * (self.config.exponential_base ** attempt),
            self.config.max_delay
        )
        
        # Add jitter if enabled
        if self.config.jitter:
            delay *= (0.5 + random.random())
            
        return delay
        
    def should_retry(self, exception: Exception) -> bool:
        """Determine if an exception should trigger a retry.
        
        Args:
            exception: The exception that occurred
            
        Returns:
            True if should retry, False otherwise
        """
        # Check if it's explicitly non-retryable
        if isinstance(exception, self.config.non_retryable_exceptions):
            return False
            
        # Check if it's explicitly retryable
        if isinstance(exception, self.config.retryable_exceptions):
            return True
            
        # Default to not retrying unknown exceptions
        return False
        
    async def execute_with_retry(
        self,
        func: Callable[..., T],
        *args,
        **kwargs
    ) -> T:
        """Execute a function with retry logic.
        
        Args:
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result of the function
            
        Raises:
            The last exception if all retries fail
        """
        last_exception = None
        
        for attempt in range(self.config.max_attempts):
            try:
                # Execute the function
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
                    
            except Exception as e:
                last_exception = e
                
                # Check if we should retry
                if not self.should_retry(e):
                    logger.error(
                        f"Non-retryable exception in {func.__name__}: {type(e).__name__}: {str(e)}"
                    )
                    raise
                    
                # Check if we have attempts left
                if attempt >= self.config.max_attempts - 1:
                    logger.error(
                        f"Max retries ({self.config.max_attempts}) exceeded for {func.__name__}: "
                        f"{type(e).__name__}: {str(e)}"
                    )
                    raise
                    
                # Calculate delay
                delay = self.calculate_delay(attempt)
                
                logger.warning(
                    f"Retryable exception in {func.__name__} (attempt {attempt + 1}/{self.config.max_attempts}): "
                    f"{type(e).__name__}: {str(e)}. Retrying in {delay:.1f}s..."
                )
                
                # Wait before retrying
                await asyncio.sleep(delay)
                
        # This should never be reached, but just in case
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError("Unexpected retry loop exit")


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (IntegrationError,),
    non_retryable_exceptions: Tuple[Type[Exception], ...] = (
        AuthenticationError,
        ValidationError,
    )
):
    """Decorator to add retry logic to a function.
    
    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter to delays
        retryable_exceptions: Exceptions that should trigger retry
        non_retryable_exceptions: Exceptions that should not be retried
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        config = RetryConfig(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=max_delay,
            exponential_base=exponential_base,
            jitter=jitter,
            retryable_exceptions=retryable_exceptions,
            non_retryable_exceptions=non_retryable_exceptions
        )
        
        retry_manager = RetryManager(config)
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await retry_manager.execute_with_retry(func, *args, **kwargs)
            
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, we need to run in an event loop
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                retry_manager.execute_with_retry(func, *args, **kwargs)
            )
            
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    return decorator


class CircuitBreaker:
    """Circuit breaker pattern implementation for fault tolerance."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time in seconds before attempting to close circuit
            expected_exception: Exception type to count as failure
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open
        
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function through circuit breaker.
        
        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function result
            
        Raises:
            IntegrationError: If circuit is open
            Original exception: If function fails
        """
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
            else:
                raise IntegrationError(
                    f"Circuit breaker is open. Service unavailable until "
                    f"{self.last_failure_time + timedelta(seconds=self.recovery_timeout)}"
                )
                
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            raise
            
    async def async_call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute async function through circuit breaker.
        
        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function result
            
        Raises:
            IntegrationError: If circuit is open
            Original exception: If function fails
        """
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
            else:
                raise IntegrationError(
                    f"Circuit breaker is open. Service unavailable until "
                    f"{self.last_failure_time + timedelta(seconds=self.recovery_timeout)}"
                )
                
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            raise
            
    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt reset."""
        if self.last_failure_time is None:
            return True
            
        return (
            datetime.utcnow() - self.last_failure_time
        ).total_seconds() >= self.recovery_timeout
        
    def _on_success(self):
        """Handle successful call."""
        if self.state == "half-open":
            self.state = "closed"
            self.failure_count = 0
            logger.info("Circuit breaker closed after successful call")
            
    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )
        elif self.state == "half-open":
            self.state = "open"
            logger.warning("Circuit breaker reopened after failure in half-open state")


class ErrorRecoveryHandler:
    """Handles error recovery strategies."""
    
    def __init__(self):
        """Initialize error recovery handler."""
        self.recovery_strategies = {}
        
    def register_recovery_strategy(
        self,
        error_type: Type[Exception],
        strategy: Callable[[Exception, Any], Any]
    ):
        """Register a recovery strategy for an error type.
        
        Args:
            error_type: Exception type to handle
            strategy: Recovery function that takes exception and context
        """
        self.recovery_strategies[error_type] = strategy
        
    async def handle_error(
        self,
        error: Exception,
        context: Dict[str, Any]
    ) -> Optional[Any]:
        """Handle an error with appropriate recovery strategy.
        
        Args:
            error: The exception that occurred
            context: Context information for recovery
            
        Returns:
            Recovery result if applicable, None otherwise
        """
        for error_type, strategy in self.recovery_strategies.items():
            if isinstance(error, error_type):
                logger.info(
                    f"Applying recovery strategy for {type(error).__name__}"
                )
                
                if asyncio.iscoroutinefunction(strategy):
                    return await strategy(error, context)
                else:
                    return strategy(error, context)
                    
        logger.warning(
            f"No recovery strategy found for {type(error).__name__}"
        )
        return None
        
    def with_recovery(self, context: Dict[str, Any]):
        """Decorator to add error recovery to a function.
        
        Args:
            context: Context information for recovery
            
        Returns:
            Decorated function
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    recovery_result = await self.handle_error(e, context)
                    if recovery_result is not None:
                        return recovery_result
                    raise
                    
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    loop = asyncio.get_event_loop()
                    recovery_result = loop.run_until_complete(
                        self.handle_error(e, context)
                    )
                    if recovery_result is not None:
                        return recovery_result
                    raise
                    
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
                
        return decorator


# Global error recovery handler instance
error_recovery = ErrorRecoveryHandler()


# Example recovery strategies
async def retry_with_exponential_backoff(error: Exception, context: Dict[str, Any]):
    """Recovery strategy that retries with exponential backoff."""
    retry_config = context.get("retry_config", RetryConfig())
    retry_manager = RetryManager(retry_config)
    
    func = context.get("function")
    args = context.get("args", ())
    kwargs = context.get("kwargs", {})
    
    if func:
        return await retry_manager.execute_with_retry(func, *args, **kwargs)
    

async def fallback_to_default(error: Exception, context: Dict[str, Any]):
    """Recovery strategy that returns a default value."""
    return context.get("default_value")


async def log_and_continue(error: Exception, context: Dict[str, Any]):
    """Recovery strategy that logs error and continues."""
    logger.error(
        f"Error occurred but continuing: {type(error).__name__}: {str(error)}"
    )
    return context.get("continue_value")