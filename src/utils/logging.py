"""Logging configuration and utilities."""

import structlog
import logging
import sys
from typing import Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    structured: bool = True,
    correlation_id_var: str = "correlation_id"
) -> None:
    """Configure structured logging for the application."""
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper())
    )
    
    # Processors for structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        add_correlation_id,
        add_app_context,
    ]
    
    if structured:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Set up file logging if requested
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(getattr(logging, log_level.upper()))
        
        # Add file handler to root logger
        logging.getLogger().addHandler(file_handler)


def add_correlation_id(logger, method_name, event_dict):
    """Add correlation ID to log entries."""
    import contextvars
    
    correlation_id = contextvars.ContextVar("correlation_id", default=None)
    if correlation_id.get():
        event_dict["correlation_id"] = correlation_id.get()
    return event_dict


def add_app_context(logger, method_name, event_dict):
    """Add application context to log entries."""
    event_dict["service"] = "universal-ai-coding-agent"
    event_dict["environment"] = os.getenv("ENVIRONMENT", "development")
    event_dict["version"] = os.getenv("APP_VERSION", "0.1.0")
    return event_dict


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger instance."""
    return structlog.get_logger(name)


class CorrelationIdMiddleware:
    """Middleware to add correlation ID to requests."""
    
    def __init__(self, app, header_name: str = "X-Correlation-ID"):
        self.app = app
        self.header_name = header_name
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            import uuid
            import contextvars
            
            # Get or create correlation ID
            headers = dict(scope["headers"])
            correlation_id = headers.get(
                self.header_name.lower().encode(),
                str(uuid.uuid4()).encode()
            ).decode()
            
            # Set correlation ID in context
            correlation_id_var = contextvars.ContextVar("correlation_id")
            correlation_id_var.set(correlation_id)
            
            # Add to response headers
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    headers = message.setdefault("headers", [])
                    headers.append(
                        (self.header_name.lower().encode(), correlation_id.encode())
                    )
                await send(message)
            
            await self.app(scope, receive, send_wrapper)
        else:
            await self.app(scope, receive, send)


class LoggingContext:
    """Context manager for adding temporary logging context."""
    
    def __init__(self, **kwargs):
        self.context = kwargs
        self.tokens = []
    
    def __enter__(self):
        import structlog
        for key, value in self.context.items():
            token = structlog.contextvars.bind_contextvars(**{key: value})
            self.tokens.append(token)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import structlog
        for token in self.tokens:
            structlog.contextvars.unbind_contextvars(token)


def log_execution_time(func):
    """Decorator to log function execution time."""
    import functools
    import time
    
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            logger.info(
                "Function executed",
                function=func.__name__,
                execution_time=execution_time,
                status="success"
            )
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            logger.error(
                "Function failed",
                function=func.__name__,
                execution_time=execution_time,
                status="error",
                error=str(e)
            )
            
            raise
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            logger.info(
                "Function executed",
                function=func.__name__,
                execution_time=execution_time,
                status="success"
            )
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            logger.error(
                "Function failed",
                function=func.__name__,
                execution_time=execution_time,
                status="error",
                error=str(e)
            )
            
            raise
    
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


# Import required modules
import os
import asyncio