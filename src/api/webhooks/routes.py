"""Webhook routes for external service integrations."""

from fastapi import APIRouter, Request, BackgroundTasks, HTTPException, Header
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
import hashlib
import hmac
import json
from datetime import datetime

from src.utils.logging import get_logger
from src.utils.exceptions import IntegrationError

logger = get_logger(__name__)

router = APIRouter()


def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str,
    algorithm: str = "sha256"
) -> bool:
    """Verify webhook signature."""
    if not secret:
        return True  # Skip verification if no secret configured
        
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        getattr(hashlib, algorithm)
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


@router.post("/jira")
async def jira_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_atlassian_webhook_signature: Optional[str] = Header(None)
):
    """Handle JIRA webhook events."""
    try:
        # Get raw payload for signature verification
        payload = await request.body()
        data = await request.json()
        
        # Log webhook event
        logger.info(f"Received JIRA webhook: {data.get('webhookEvent', 'unknown')}")
        
        # Verify signature if configured
        # TODO: Implement JIRA webhook signature verification
        
        # Extract event type
        event_type = data.get("webhookEvent", "")
        issue_event = data.get("issue_event_type_name", "")
        
        # Check if this is an issue assignment event
        if event_type == "jira:issue_updated" and issue_event == "issue_assigned":
            issue = data.get("issue", {})
            assignee = issue.get("fields", {}).get("assignee", {})
            
            # Check if assigned to AI agent
            ai_agent_account_ids = ["ai-agent", "ai-coding-agent"]  # Configure these
            if assignee and (
                assignee.get("accountId") in ai_agent_account_ids or
                assignee.get("emailAddress", "").startswith("ai-agent")
            ):
                # Process in background
                background_tasks.add_task(
                    process_jira_assignment,
                    issue_data=issue,
                    webhook_data=data
                )
                
                return JSONResponse(
                    content={
                        "status": "accepted",
                        "message": "Webhook received and queued for processing",
                        "issue_key": issue.get("key")
                    },
                    status_code=200
                )
        
        # Not an assignment event we care about
        return JSONResponse(
            content={
                "status": "ignored",
                "message": "Event type not handled",
                "event": event_type
            },
            status_code=200
        )
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error(f"Error processing JIRA webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bitbucket")
async def bitbucket_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature: Optional[str] = Header(None)
):
    """Handle Bitbucket webhook events."""
    try:
        # Get raw payload for signature verification
        payload = await request.body()
        data = await request.json()
        
        # Log webhook event
        event_key = data.get("eventKey", "unknown")
        logger.info(f"Received Bitbucket webhook: {event_key}")
        
        # Verify signature if configured
        # TODO: Implement Bitbucket webhook signature verification
        
        # Handle different event types
        if event_key == "pullrequest:comment_created":
            # Check if comment mentions AI agent
            comment = data.get("comment", {})
            if "@ai-agent" in comment.get("text", ""):
                pr = data.get("pullRequest", {})
                background_tasks.add_task(
                    process_bitbucket_pr_comment,
                    pr_data=pr,
                    comment_data=comment
                )
                
        elif event_key == "repo:push":
            # Handle push events if needed
            pass
            
        return JSONResponse(
            content={
                "status": "accepted",
                "message": "Webhook received",
                "event": event_key
            },
            status_code=200
        )
        
    except Exception as e:
        logger.error(f"Error processing Bitbucket webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None)
):
    """Handle GitHub webhook events."""
    try:
        # Get raw payload
        payload = await request.body()
        data = await request.json()
        
        # Log webhook event
        logger.info(f"Received GitHub webhook: {x_github_event}")
        
        # Verify signature
        # TODO: Implement GitHub webhook signature verification
        
        # Handle different event types
        if x_github_event == "issues":
            action = data.get("action")
            if action == "assigned":
                issue = data.get("issue", {})
                assignee = issue.get("assignee", {})
                
                # Check if assigned to AI agent
                if assignee and assignee.get("login") == "ai-coding-agent":
                    background_tasks.add_task(
                        process_github_issue_assignment,
                        issue_data=issue,
                        repository=data.get("repository", {})
                    )
                    
        elif x_github_event == "issue_comment":
            # Handle comments mentioning the AI agent
            comment = data.get("comment", {})
            if "@ai-coding-agent" in comment.get("body", ""):
                issue = data.get("issue", {})
                background_tasks.add_task(
                    process_github_issue_comment,
                    issue_data=issue,
                    comment_data=comment,
                    repository=data.get("repository", {})
                )
                
        return JSONResponse(
            content={
                "status": "accepted",
                "message": "Webhook received",
                "event": x_github_event
            },
            status_code=200
        )
        
    except Exception as e:
        logger.error(f"Error processing GitHub webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/azure-devops")
async def azure_devops_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """Handle Azure DevOps webhook events."""
    try:
        data = await request.json()
        
        # Log webhook event
        event_type = data.get("eventType", "unknown")
        logger.info(f"Received Azure DevOps webhook: {event_type}")
        
        # Handle work item updates
        if event_type == "workitem.updated":
            resource = data.get("resource", {})
            fields = resource.get("fields", {})
            
            # Check if assigned to AI agent
            assigned_to = fields.get("System.AssignedTo", {})
            if assigned_to.get("uniqueName", "").startswith("ai-agent"):
                background_tasks.add_task(
                    process_azure_devops_assignment,
                    work_item=resource,
                    webhook_data=data
                )
                
        return JSONResponse(
            content={
                "status": "accepted",
                "message": "Webhook received",
                "event": event_type
            },
            status_code=200
        )
        
    except Exception as e:
        logger.error(f"Error processing Azure DevOps webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# Background task functions
async def process_jira_assignment(issue_data: Dict[str, Any], webhook_data: Dict[str, Any]):
    """Process JIRA issue assignment."""
    try:
        from src.main import get_agent
        
        agent = get_agent()
        
        if not agent:
            logger.error("Agent not initialized")
            return
            
        logger.info(f"Processing JIRA assignment for issue: {issue_data.get('key')}")
        
        # Transform JIRA data to common format
        ticket_data = {
            "id": issue_data.get("key"),
            "platform": "jira",
            "data": issue_data,
            "webhook_data": webhook_data
        }
        
        # Process ticket assignment
        await agent.process_ticket_assignment("jira", ticket_data)
        
    except Exception as e:
        logger.error(f"Error processing JIRA assignment: {e}", exc_info=True)


async def process_bitbucket_pr_comment(pr_data: Dict[str, Any], comment_data: Dict[str, Any]):
    """Process Bitbucket PR comment."""
    try:
        logger.info(f"Processing Bitbucket PR comment for PR: {pr_data.get('id')}")
        # Implement PR comment processing logic
        pass
    except Exception as e:
        logger.error(f"Error processing Bitbucket PR comment: {e}", exc_info=True)


async def process_github_issue_assignment(issue_data: Dict[str, Any], repository: Dict[str, Any]):
    """Process GitHub issue assignment."""
    try:
        from src.main import get_agent
        
        agent = get_agent()
        
        if not agent:
            logger.error("Agent not initialized")
            return
            
        logger.info(f"Processing GitHub assignment for issue: #{issue_data.get('number')}")
        
        # Transform GitHub data to common format
        ticket_data = {
            "id": f"{repository.get('name')}#{issue_data.get('number')}",
            "platform": "github",
            "data": issue_data,
            "repository": repository
        }
        
        # Process ticket assignment
        await agent.process_ticket_assignment("github", ticket_data)
        
    except Exception as e:
        logger.error(f"Error processing GitHub assignment: {e}", exc_info=True)


async def process_github_issue_comment(
    issue_data: Dict[str, Any],
    comment_data: Dict[str, Any],
    repository: Dict[str, Any]
):
    """Process GitHub issue comment."""
    try:
        logger.info(f"Processing GitHub comment for issue: #{issue_data.get('number')}")
        # Implement comment processing logic
        pass
    except Exception as e:
        logger.error(f"Error processing GitHub comment: {e}", exc_info=True)


async def process_azure_devops_assignment(work_item: Dict[str, Any], webhook_data: Dict[str, Any]):
    """Process Azure DevOps work item assignment."""
    try:
        from src.main import get_agent
        
        agent = get_agent()
        
        if not agent:
            logger.error("Agent not initialized")
            return
            
        logger.info(f"Processing Azure DevOps assignment for work item: {work_item.get('id')}")
        
        # Transform Azure DevOps data to common format
        ticket_data = {
            "id": str(work_item.get("id")),
            "platform": "azure_devops",
            "data": work_item,
            "webhook_data": webhook_data
        }
        
        # Process ticket assignment
        await agent.process_ticket_assignment("azure_devops", ticket_data)
        
    except Exception as e:
        logger.error(f"Error processing Azure DevOps assignment: {e}", exc_info=True)