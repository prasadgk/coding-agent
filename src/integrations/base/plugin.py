"""Base plugin interface and metadata."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
import asyncio
from pathlib import Path


class PluginStatus(str, Enum):
    """Plugin lifecycle status."""
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class PluginMetadata:
    """Metadata for a plugin."""
    name: str
    version: str
    description: str
    author: str
    integration_type: str
    supported_platforms: List[str]
    required_config: List[str]
    optional_config: List[str] = None
    dependencies: List[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "integration_type": self.integration_type,
            "supported_platforms": self.supported_platforms,
            "required_config": self.required_config,
            "optional_config": self.optional_config or [],
            "dependencies": self.dependencies or []
        }


class Plugin(ABC):
    """Base class for all plugins."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize plugin with configuration."""
        self.config = config
        self.status = PluginStatus.UNLOADED
        self._metadata: Optional[PluginMetadata] = None
        self._health_check_interval = 60  # seconds
        self._health_check_task: Optional[asyncio.Task] = None
        self._initialized = False
        self._error_message: Optional[str] = None
    
    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the plugin."""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the plugin gracefully."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the plugin is healthy."""
        pass
    
    @abstractmethod
    async def validate_config(self) -> bool:
        """Validate plugin configuration."""
        pass
    
    async def start(self) -> None:
        """Start the plugin."""
        try:
            self.status = PluginStatus.LOADING
            
            # Validate configuration
            if not await self.validate_config():
                raise ValueError("Invalid plugin configuration")
            
            # Initialize the plugin
            await self.initialize()
            self._initialized = True
            
            # Start health check task
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            self.status = PluginStatus.READY
            
        except Exception as e:
            self.status = PluginStatus.ERROR
            self._error_message = str(e)
            raise
    
    async def stop(self) -> None:
        """Stop the plugin."""
        try:
            # Cancel health check task
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            
            # Shutdown the plugin
            if self._initialized:
                await self.shutdown()
                self._initialized = False
            
            self.status = PluginStatus.DISABLED
            
        except Exception as e:
            self.status = PluginStatus.ERROR
            self._error_message = str(e)
            raise
    
    async def _health_check_loop(self) -> None:
        """Periodic health check loop."""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                
                if not await self.health_check():
                    self.status = PluginStatus.ERROR
                    self._error_message = "Health check failed"
                elif self.status == PluginStatus.ERROR and self._error_message == "Health check failed":
                    # Recovered from health check failure
                    self.status = PluginStatus.READY
                    self._error_message = None
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.status = PluginStatus.ERROR
                self._error_message = f"Health check error: {str(e)}"
    
    def get_status(self) -> Dict[str, Any]:
        """Get current plugin status."""
        return {
            "name": self.metadata.name,
            "status": self.status.value,
            "initialized": self._initialized,
            "error_message": self._error_message,
            "metadata": self.metadata.to_dict()
        }
    
    def is_ready(self) -> bool:
        """Check if plugin is ready to use."""
        return self.status == PluginStatus.READY and self._initialized
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get configuration value safely."""
        return self.config.get(key, default)
    
    def require_config_value(self, key: str) -> Any:
        """Get required configuration value."""
        if key not in self.config:
            raise ValueError(f"Required configuration key missing: {key}")
        return self.config[key]