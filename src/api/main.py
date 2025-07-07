"""Main API application with webhook endpoints."""

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime

from src.config.settings import get_settings
from src.core.agent import UniversalCodingAgent
from src.utils.logging import get_logger
from src.utils.exceptions import IntegrationError
from src.api.webhooks import router as webhook_router
from src.api.rest import router as rest_router

logger = get_logger(__name__)
settings = get_settings()

# Global agent instance
agent: Optional[UniversalCodingAgent] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global agent
    
    logger.info("Starting AI Coding Agent API...")
    
    # Initialize agent
    try:
        agent_config = settings.get_agent_config()
        agent = UniversalCodingAgent(agent_config)
        logger.info("Agent initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down AI Coding Agent API...")
    if agent:
        await agent.shutdown()
    

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Universal AI Coding Agent API",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(IntegrationError)
async def integration_error_handler(request: Request, exc: IntegrationError):
    """Handle integration errors."""
    logger.error(f"Integration error: {exc}")
    return JSONResponse(
        status_code=400,
        content={"error": str(exc), "type": "integration_error"}
    )


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    """Handle general errors."""
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "type": "internal_error"}
    )


# Include routers
app.include_router(webhook_router, prefix="/webhooks", tags=["webhooks"])
app.include_router(rest_router, prefix="/api/v1", tags=["api"])


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.version,
        "status": "running",
        "timestamp": datetime.utcnow().isoformat()
    }


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.version,
        "environment": settings.environment
    }
    
    # Check agent status
    if agent:
        health_status["agent"] = {
            "status": "initialized",
            "active_workflows": len(agent.workflow_engine.active_workflows)
        }
    else:
        health_status["agent"] = {"status": "not_initialized"}
        health_status["status"] = "degraded"
    
    # Check repository manager
    if agent and agent.repository_manager:
        health_status["repository_manager"] = {
            "status": "healthy",
            "active_repositories": len(agent.repository_manager.pool.active_repositories)
        }
    
    return health_status


# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    if not agent:
        return ""
    
    metrics_lines = [
        "# HELP ai_agent_active_workflows Number of active workflows",
        "# TYPE ai_agent_active_workflows gauge",
        f"ai_agent_active_workflows {len(agent.workflow_engine.active_workflows)}",
        "",
        "# HELP ai_agent_completed_workflows Number of completed workflows",
        "# TYPE ai_agent_completed_workflows counter",
        f"ai_agent_completed_workflows {len(agent.workflow_engine.completed_workflows)}",
        "",
        "# HELP ai_agent_active_repositories Number of active repository clones",
        "# TYPE ai_agent_active_repositories gauge",
        f"ai_agent_active_repositories {len(agent.repository_manager.pool.active_repositories)}"
    ]
    
    return "\n".join(metrics_lines)


# API key dependency (optional)
async def verify_api_key(request: Request):
    """Verify API key if authentication is enabled."""
    if not settings.enable_auth:
        return True
        
    api_key = request.headers.get(settings.api_key_header)
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
        
    # Verify API key (implement your logic here)
    # For now, just check if it's provided
    return True


# Startup event
@app.on_event("startup")
async def startup_event():
    """Handle startup tasks."""
    logger.info(f"Starting {settings.app_name} v{settings.version}")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"API running on http://{settings.api_host}:{settings.api_port}")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Handle shutdown tasks."""
    logger.info("Shutting down API...")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
        log_level=settings.monitoring.log_level.lower()
    )