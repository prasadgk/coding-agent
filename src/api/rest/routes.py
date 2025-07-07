"""REST API routes for agent management and monitoring."""

from fastapi import APIRouter, HTTPException, Query, Path
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.utils.logging import get_logger
from src.core.workflow_engine import WorkflowState

logger = get_logger(__name__)

router = APIRouter()


@router.get("/workflows")
async def list_workflows(
    status: Optional[WorkflowState] = Query(None, description="Filter by workflow status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of workflows to return"),
    offset: int = Query(0, ge=0, description="Number of workflows to skip")
) -> Dict[str, Any]:
    """List workflows with optional filtering."""
    try:
        from src.main import get_agent
        
        agent = get_agent()
        
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        # Get all workflows
        all_workflows = (
            list(agent.workflow_engine.active_workflows.values()) +
            list(agent.workflow_engine.completed_workflows.values())
        )
        
        # Filter by status if provided
        if status:
            all_workflows = [w for w in all_workflows if w.state == status]
        
        # Sort by start time (newest first)
        all_workflows.sort(key=lambda w: w.started_at, reverse=True)
        
        # Apply pagination
        total = len(all_workflows)
        workflows = all_workflows[offset:offset + limit]
        
        return {
            "workflows": [
                {
                    "id": w.id,
                    "ticket_id": w.ticket_id,
                    "state": w.state,
                    "started_at": w.started_at.isoformat(),
                    "completed_at": w.completed_at.isoformat() if w.completed_at else None,
                    "error": w.error
                }
                for w in workflows
            ],
            "total": total,
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"Error listing workflows: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str = Path(..., description="Workflow ID")) -> Dict[str, Any]:
    """Get detailed information about a specific workflow."""
    try:
        from src.main import get_agent
        
        agent = get_agent()
        
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        workflow = agent.workflow_engine.get_workflow_status(workflow_id)
        
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        return {
            "id": workflow.id,
            "ticket_id": workflow.ticket_id,
            "state": workflow.state,
            "started_at": workflow.started_at.isoformat(),
            "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
            "error": workflow.error,
            "steps": [
                {
                    "name": step.step_name,
                    "status": step.status,
                    "started_at": step.started_at.isoformat(),
                    "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                    "error": step.error,
                    "retries": step.retries
                }
                for step in workflow.steps
            ],
            "context": {
                "repository_url": workflow.context.repository_url if workflow.context else None,
                "branch_name": workflow.context.branch_name if workflow.context else None,
                "pull_request_url": workflow.context.pull_request_url if workflow.context else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/workflows/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: str = Path(..., description="Workflow ID")) -> Dict[str, Any]:
    """Cancel a running workflow."""
    try:
        from src.main import get_agent
        
        agent = get_agent()
        
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        workflow = agent.workflow_engine.get_workflow_status(workflow_id)
        
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
            
        if workflow.state not in [WorkflowState.PENDING, WorkflowState.RUNNING]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel workflow in state: {workflow.state}"
            )
        
        await agent.workflow_engine.cancel_workflow(workflow_id)
        
        return {
            "id": workflow_id,
            "status": "cancelled",
            "message": "Workflow cancelled successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/repositories")
async def list_repositories() -> Dict[str, Any]:
    """List active repository clones."""
    try:
        from src.main import get_agent
        
        agent = get_agent()
        
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        repos = agent.repository_manager.pool.active_repositories
        
        return {
            "repositories": [
                {
                    "url": repo_info.url,
                    "path": str(repo_info.local_path),
                    "last_used": repo_info.last_used.isoformat(),
                    "created_at": repo_info.created_at.isoformat(),
                    "size_bytes": repo_info.size_bytes,
                    "active_branches": list(repo_info.active_branches),
                    "lock_status": "locked" if repo_info.is_locked else "unlocked"
                }
                for repo_info in repos.values()
            ],
            "total": len(repos),
            "disk_usage_gb": sum(r.size_bytes for r in repos.values()) / (1024**3)
        }
        
    except Exception as e:
        logger.error(f"Error listing repositories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/repositories/cleanup")
async def cleanup_repositories(
    force: bool = Query(False, description="Force cleanup even if repositories are active")
) -> Dict[str, Any]:
    """Trigger repository cleanup."""
    try:
        from src.main import get_agent
        
        agent = get_agent()
        
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        # Run cleanup
        cleaned = await agent.repository_manager.cleaner.cleanup_inactive_repositories(
            force=force
        )
        
        return {
            "status": "completed",
            "repositories_cleaned": len(cleaned),
            "cleaned_repositories": cleaned
        }
        
    except Exception as e:
        logger.error(f"Error cleaning repositories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/integrations")
async def list_integrations() -> Dict[str, Any]:
    """List configured integrations."""
    try:
        from src.main import get_agent
        
        agent = get_agent()
        
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        integrations = {
            "project_management": [],
            "version_control": [],
            "communication": [],
            "cicd": []
        }
        
        for category, platforms in agent.integrations.items():
            for platform_name, integration in platforms.items():
                integrations[category].append({
                    "name": platform_name,
                    "enabled": True,
                    "type": integration.__class__.__name__
                })
        
        return integrations
        
    except Exception as e:
        logger.error(f"Error listing integrations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats")
async def get_statistics() -> Dict[str, Any]:
    """Get agent statistics."""
    try:
        from src.main import get_agent
        
        agent = get_agent()
        
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        # Calculate statistics
        completed_workflows = list(agent.workflow_engine.completed_workflows.values())
        successful_workflows = [w for w in completed_workflows if w.state == WorkflowState.COMPLETED]
        failed_workflows = [w for w in completed_workflows if w.state == WorkflowState.FAILED]
        
        # Calculate average duration
        durations = []
        for w in successful_workflows:
            if w.completed_at and w.started_at:
                duration = (w.completed_at - w.started_at).total_seconds()
                durations.append(duration)
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return {
            "workflows": {
                "total": len(completed_workflows) + len(agent.workflow_engine.active_workflows),
                "active": len(agent.workflow_engine.active_workflows),
                "completed": len(successful_workflows),
                "failed": len(failed_workflows),
                "cancelled": len([w for w in completed_workflows if w.state == WorkflowState.CANCELLED]),
                "success_rate": len(successful_workflows) / len(completed_workflows) if completed_workflows else 0,
                "average_duration_seconds": avg_duration
            },
            "repositories": {
                "active": len(agent.repository_manager.pool.active_repositories),
                "total_disk_usage_gb": sum(
                    r.size_bytes for r in agent.repository_manager.pool.active_repositories.values()
                ) / (1024**3)
            },
            "uptime": {
                "started_at": datetime.utcnow().isoformat(),  # TODO: Track actual start time
                "environment": agent.settings.environment if hasattr(agent, 'settings') and hasattr(agent.settings, 'environment') else "unknown"
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting statistics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/test/trigger-workflow")
async def trigger_test_workflow(
    ticket_id: str = Query(..., description="Test ticket ID"),
    platform: str = Query("jira", description="Platform type")
) -> Dict[str, Any]:
    """Trigger a test workflow (development only)."""
    try:
        from src.main import get_agent
        
        agent = get_agent()
        from src.config.settings import get_settings
        
        settings = get_settings()
        if not settings.is_development:
            raise HTTPException(status_code=403, detail="Only available in development")
        
        if not agent:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        # Create test ticket data
        test_data = {
            "id": ticket_id,
            "platform": platform,
            "data": {
                "key": ticket_id,
                "fields": {
                    "summary": f"Test ticket {ticket_id}",
                    "description": "This is a test ticket for workflow testing",
                    "assignee": {"accountId": "ai-agent"}
                }
            }
        }
        
        # Process in background
        import asyncio
        asyncio.create_task(agent.process_ticket_assignment(platform, test_data))
        
        return {
            "status": "triggered",
            "ticket_id": ticket_id,
            "platform": platform,
            "message": "Test workflow triggered successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering test workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")