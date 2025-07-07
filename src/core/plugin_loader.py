"""Plugin loading and management system."""

import asyncio
import importlib
import inspect
from pathlib import Path
from typing import Dict, List, Type, Optional, Any
import structlog

from src.integrations.base import (
    Plugin,
    ProjectManagementPlugin,
    VersionControlPlugin,
    CommunicationPlugin,
    CICDPlugin
)
from src.config import IntegrationType, IntegrationConfig


logger = structlog.get_logger(__name__)


class PluginLoader:
    """Manages loading and lifecycle of plugins."""
    
    # Plugin type mapping
    PLUGIN_TYPES = {
        IntegrationType.PROJECT_MANAGEMENT: ProjectManagementPlugin,
        IntegrationType.VERSION_CONTROL: VersionControlPlugin,
        IntegrationType.COMMUNICATION: CommunicationPlugin,
        IntegrationType.CICD: CICDPlugin
    }
    
    def __init__(self, plugin_directories: List[Path]):
        """Initialize plugin loader with directories to scan."""
        self.plugin_directories = plugin_directories
        self.discovered_plugins: Dict[str, Type[Plugin]] = {}
        self.loaded_plugins: Dict[str, Plugin] = {}
        self.integration_config = IntegrationConfig()
        self._lock = asyncio.Lock()
    
    async def discover_plugins(self) -> Dict[str, Type[Plugin]]:
        """Discover all available plugins in configured directories."""
        logger.info("Discovering plugins", directories=[str(d) for d in self.plugin_directories])
        
        for directory in self.plugin_directories:
            if not directory.exists():
                logger.warning("Plugin directory does not exist", directory=str(directory))
                continue
            
            await self._scan_directory(directory)
        
        logger.info("Plugin discovery complete", count=len(self.discovered_plugins))
        return self.discovered_plugins
    
    async def _scan_directory(self, directory: Path) -> None:
        """Scan a directory for plugin implementations."""
        for integration_type in ["project_management", "version_control", "communication", "cicd"]:
            type_dir = directory / integration_type
            if not type_dir.exists():
                continue
            
            for file_path in type_dir.glob("*.py"):
                if file_path.name.startswith("_"):
                    continue
                
                await self._load_plugin_from_file(file_path, integration_type)
    
    async def _load_plugin_from_file(self, file_path: Path, integration_type: str) -> None:
        """Load plugin class from a Python file."""
        try:
            # Convert file path to module path
            module_name = f"src.integrations.{integration_type}.{file_path.stem}"
            
            # Import the module
            module = importlib.import_module(module_name)
            
            # Find plugin classes in the module
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    issubclass(obj, Plugin) and 
                    obj not in [Plugin, ProjectManagementPlugin, VersionControlPlugin, 
                               CommunicationPlugin, CICDPlugin] and
                    not inspect.isabstract(obj)):
                    
                    plugin_name = file_path.stem
                    self.discovered_plugins[plugin_name] = obj
                    logger.info(
                        "Discovered plugin",
                        name=plugin_name,
                        type=integration_type,
                        class_name=obj.__name__
                    )
                    
        except Exception as e:
            logger.error(
                "Failed to load plugin",
                file=str(file_path),
                error=str(e),
                exc_info=True
            )
    
    async def load_plugin(self, name: str, config: Dict[str, Any]) -> Plugin:
        """Load and initialize a specific plugin."""
        async with self._lock:
            # Check if already loaded
            if name in self.loaded_plugins:
                return self.loaded_plugins[name]
            
            # Check if plugin exists
            if name not in self.discovered_plugins:
                raise ValueError(f"Plugin not found: {name}")
            
            logger.info("Loading plugin", name=name)
            
            try:
                # Create plugin instance
                plugin_class = self.discovered_plugins[name]
                plugin = plugin_class(config)
                
                # Register configuration
                self.integration_config.load_config(name, config)
                
                # Start the plugin
                await plugin.start()
                
                # Store loaded plugin
                self.loaded_plugins[name] = plugin
                
                logger.info(
                    "Plugin loaded successfully",
                    name=name,
                    status=plugin.get_status()
                )
                
                return plugin
                
            except Exception as e:
                logger.error(
                    "Failed to load plugin",
                    name=name,
                    error=str(e),
                    exc_info=True
                )
                raise
    
    async def unload_plugin(self, name: str) -> None:
        """Unload a specific plugin."""
        async with self._lock:
            if name not in self.loaded_plugins:
                logger.warning("Plugin not loaded", name=name)
                return
            
            logger.info("Unloading plugin", name=name)
            
            try:
                plugin = self.loaded_plugins[name]
                await plugin.stop()
                del self.loaded_plugins[name]
                
                logger.info("Plugin unloaded successfully", name=name)
                
            except Exception as e:
                logger.error(
                    "Failed to unload plugin",
                    name=name,
                    error=str(e),
                    exc_info=True
                )
                raise
    
    async def reload_plugin(self, name: str, config: Dict[str, Any]) -> Plugin:
        """Reload a plugin with new configuration."""
        await self.unload_plugin(name)
        return await self.load_plugin(name, config)
    
    async def load_plugins_from_config(self, config: Dict[str, List[str]]) -> None:
        """Load plugins based on configuration."""
        for integration_type, plugin_names in config.items():
            for plugin_name in plugin_names:
                # Get plugin configuration
                plugin_config = self._get_plugin_config(plugin_name)
                if plugin_config:
                    try:
                        await self.load_plugin(plugin_name, plugin_config)
                    except Exception as e:
                        logger.error(
                            "Failed to load plugin from config",
                            plugin=plugin_name,
                            error=str(e)
                        )
    
    def _get_plugin_config(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific plugin."""
        # This would typically load from environment or config file
        # For now, return empty config
        return {}
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a loaded plugin by name."""
        return self.loaded_plugins.get(name)
    
    def get_plugins_by_type(self, plugin_type: IntegrationType) -> List[Plugin]:
        """Get all loaded plugins of a specific type."""
        base_class = self.PLUGIN_TYPES.get(plugin_type)
        if not base_class:
            return []
        
        return [
            plugin for plugin in self.loaded_plugins.values()
            if isinstance(plugin, base_class)
        ]
    
    async def get_plugin_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all plugins."""
        status = {}
        
        # Discovered plugins
        status["discovered"] = list(self.discovered_plugins.keys())
        
        # Loaded plugins
        status["loaded"] = {}
        for name, plugin in self.loaded_plugins.items():
            status["loaded"][name] = plugin.get_status()
        
        return status
    
    async def health_check(self) -> Dict[str, bool]:
        """Perform health check on all loaded plugins."""
        results = {}
        
        for name, plugin in self.loaded_plugins.items():
            try:
                results[name] = await plugin.health_check()
            except Exception as e:
                logger.error(
                    "Plugin health check failed",
                    plugin=name,
                    error=str(e)
                )
                results[name] = False
        
        return results
    
    async def shutdown(self) -> None:
        """Shutdown all loaded plugins."""
        logger.info("Shutting down plugin loader")
        
        # Unload all plugins
        plugin_names = list(self.loaded_plugins.keys())
        for name in plugin_names:
            try:
                await self.unload_plugin(name)
            except Exception as e:
                logger.error(
                    "Error during plugin shutdown",
                    plugin=name,
                    error=str(e)
                )
        
        logger.info("Plugin loader shutdown complete")