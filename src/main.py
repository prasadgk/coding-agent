"""Main entry point for the Universal AI Coding Agent."""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import get_settings
from src.core.plugin_loader import PluginLoader
from src.core.workflow_engine import WorkflowEngine
from src.utils.logging import setup_logging
from src.utils.metrics import MetricsCollector
from src.api.webhooks import router as webhook_router
from src.api.rest import router as api_router


logger = structlog.get_logger(__name__)

# Global agent instance for API routes
_global_agent: Optional['UniversalAICodingAgent'] = None


def get_agent() -> Optional['UniversalAICodingAgent']:
    """Get the global agent instance."""
    return _global_agent


class RepositoryManagerStub:
    """Stub repository manager for API compatibility."""
    
    def __init__(self):
        self.pool = RepositoryPoolStub()
        self.cleaner = CleanerStub()


class RepositoryPoolStub:
    """Stub repository pool for API compatibility."""
    
    def __init__(self):
        self.active_repositories = {}


class CleanerStub:
    """Stub cleaner for API compatibility."""
    
    async def cleanup_inactive_repositories(self, force=False):
        """Stub cleanup method."""
        return []


class UniversalAICodingAgent:
    """Main application class."""
    
    def __init__(self):
        self.settings = get_settings()
        self.metrics = MetricsCollector()
        self.plugin_loader: Optional[PluginLoader] = None
        self.workflow_engine: Optional[WorkflowEngine] = None
        self.app: Optional[FastAPI] = None
        self._shutdown_event = asyncio.Event()
        
        # Initialize repository manager stub
        self.repository_manager = RepositoryManagerStub()
        
        # Initialize integrations stub
        self.integrations = {
            "project_management": {},
            "version_control": {},
            "communication": {},
            "cicd": {}
        }
    
    async def initialize(self):
        """Initialize the application."""
        logger.info("Initializing Universal AI Coding Agent", version=self.settings.version)
        
        # Setup logging
        setup_logging(
            log_level=self.settings.monitoring.log_level,
            structured=self.settings.monitoring.structured_logging
        )
        
        # Initialize plugin loader
        self.plugin_loader = PluginLoader(self.settings.plugin_directories)
        await self.plugin_loader.discover_plugins()
        
        # Load configured plugins
        await self.plugin_loader.load_plugins_from_config(
            self.settings.enabled_integrations
        )
        
        # Initialize workflow engine
        self.workflow_engine = WorkflowEngine(
            max_concurrent_workflows=self.settings.workflow.concurrent_workflows
        )
        
        # Ensure workflow engine has required attributes for API
        if not hasattr(self.workflow_engine, 'active_workflows'):
            self.workflow_engine.active_workflows = {}
        if not hasattr(self.workflow_engine, 'completed_workflows'):
            self.workflow_engine.completed_workflows = {}
        
        # Register workflow steps
        await self._register_workflow_steps()
        
        # Initialize FastAPI app
        self.app = self._create_app()
        
        logger.info("Application initialized successfully")
    
    def _create_app(self) -> FastAPI:
        """Create FastAPI application."""
        app = FastAPI(
            title="Universal AI Coding Agent",
            version=self.settings.version,
            docs_url="/docs" if self.settings.is_development else None,
            redoc_url="/redoc" if self.settings.is_development else None
        )
        
        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.settings.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"]
        )
        
        # Add routers
        app.include_router(
            webhook_router,
            prefix=self.settings.webhook_base_path,
            tags=["webhooks"]
        )
        app.include_router(
            api_router,
            prefix=self.settings.api_base_path,
            tags=["api"]
        )
        
        # Add startup and shutdown events
        app.add_event_handler("startup", self._on_startup)
        app.add_event_handler("shutdown", self._on_shutdown)
        
        # Add basic endpoints
        @app.get("/")
        async def root():
            """Root endpoint."""
            from datetime import datetime
            return {
                "name": self.settings.app_name,
                "version": self.settings.version,
                "status": "running",
                "timestamp": datetime.utcnow().isoformat()
            }

        @app.get("/health")
        async def health_check():
            """Health check endpoint."""
            from datetime import datetime
            health_status = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "version": self.settings.version,
                "environment": self.settings.environment
            }
            
            # Check agent status
            if self.workflow_engine:
                health_status["agent"] = {
                    "status": "initialized",
                    "active_workflows": len(self.workflow_engine.active_workflows)
                }
            else:
                health_status["agent"] = {"status": "not_initialized"}
                health_status["status"] = "degraded"
            
            # Check plugin loader
            if self.plugin_loader:
                health_status["plugin_loader"] = {
                    "status": "healthy",
                    "loaded_plugins": len(self.plugin_loader.loaded_plugins) if hasattr(self.plugin_loader, 'loaded_plugins') else 0
                }
            
            return health_status

        @app.get("/metrics")
        async def metrics():
            """Prometheus-compatible metrics endpoint."""
            metrics_lines = [
                "# HELP ai_agent_active_workflows Number of active workflows",
                "# TYPE ai_agent_active_workflows gauge",
                f"ai_agent_active_workflows {len(self.workflow_engine.active_workflows) if self.workflow_engine else 0}",
                "",
                "# HELP ai_agent_plugin_count Number of loaded plugins",
                "# TYPE ai_agent_plugin_count gauge",
                f"ai_agent_plugin_count {len(self.plugin_loader.loaded_plugins) if self.plugin_loader and hasattr(self.plugin_loader, 'loaded_plugins') else 0}"
            ]
            
            return "\n".join(metrics_lines)
        
        return app
    
    async def _register_workflow_steps(self):
        """Register workflow steps with the engine."""
        # This will be implemented when we have the actual workflow steps
        logger.info("Registering workflow steps")
        # Example:
        # self.workflow_engine.register_step(
        #     WorkflowStep(
        #         name="fetch_ticket",
        #         handler=self._fetch_ticket_details,
        #         required=True
        #     )
        # )
    
    async def _on_startup(self):
        """Handle application startup."""
        logger.info("Application startup")
        
        # Perform health checks
        health_results = await self.plugin_loader.health_check()
        for plugin, healthy in health_results.items():
            self.metrics.set_health_status(plugin, healthy)
    
    async def _on_shutdown(self):
        """Handle application shutdown."""
        logger.info("Application shutdown initiated")
        
        # Shutdown workflow engine
        if self.workflow_engine:
            await self.workflow_engine.shutdown()
        
        # Shutdown plugins
        if self.plugin_loader:
            await self.plugin_loader.shutdown()
        
        logger.info("Application shutdown complete")
    
    async def process_ticket_assignment(self, platform: str, ticket_data: dict):
        """Process ticket assignment (stub implementation)."""
        logger.info(f"Processing ticket assignment for platform: {platform}, ticket: {ticket_data.get('id', 'unknown')}")
        # TODO: Implement actual ticket processing
        pass
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("Received shutdown signal", signal=signum)
        self._shutdown_event.set()
        sys.exit(0)


def create_app():
    """Factory function to create the FastAPI app."""
    global _global_agent
    
    agent = UniversalAICodingAgent()
    _global_agent = agent  # Set global agent for API routes
    
    # Initialize the agent synchronously
    import asyncio
    try:
        # Try to get the current loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a new thread for initialization if loop is running
            import threading
            import concurrent.futures
            
            def init_agent():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(agent.initialize())
                new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(init_agent)
                future.result()
        else:
            loop.run_until_complete(agent.initialize())
    except RuntimeError:
        # No event loop exists
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(agent.initialize())
    
    return agent.app


def main():
    """Main entry point."""
    import uvicorn
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    
    settings = get_settings()
    
    # Run the application using factory pattern
    uvicorn.run(
        "src.main:create_app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.monitoring.log_level.lower(),
        factory=True
    )


if __name__ == "__main__":
    main()