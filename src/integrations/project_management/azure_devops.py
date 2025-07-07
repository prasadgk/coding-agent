"""Azure DevOps integration for project management."""

import asyncio
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
import aiohttp
from urllib.parse import quote

from ..base.project_management import (
    ProjectManagementIntegration,
    Ticket,
    TicketStatus,
    TicketPriority,
    User,
    Comment,
    Attachment,
    TicketType,
    TicketLabel,
    WebhookEvent,
    WebhookEventType
)
from ...utils.exceptions import IntegrationError, AuthenticationError, ValidationError
from ...utils.logging import get_logger

logger = get_logger(__name__)


class AzureDevOpsIntegration(ProjectManagementIntegration):
    """Azure DevOps integration implementation."""
    
    PLUGIN_ID = "azure_devops"
    DISPLAY_NAME = "Azure DevOps"
    VERSION = "1.0.0"
    
    # Azure DevOps API version
    API_VERSION = "7.0"
    
    # Work item type mappings
    WORK_ITEM_TYPE_MAP = {
        "User Story": TicketType.STORY,
        "Bug": TicketType.BUG,
        "Task": TicketType.TASK,
        "Feature": TicketType.EPIC,
        "Epic": TicketType.EPIC,
        "Issue": TicketType.BUG
    }
    
    # State to status mappings
    STATE_TO_STATUS_MAP = {
        "New": TicketStatus.TODO,
        "Active": TicketStatus.IN_PROGRESS,
        "Resolved": TicketStatus.IN_REVIEW,
        "Closed": TicketStatus.DONE,
        "Removed": TicketStatus.CANCELLED,
        "Approved": TicketStatus.TODO,
        "Committed": TicketStatus.TODO,
        "Started": TicketStatus.IN_PROGRESS,
        "In Progress": TicketStatus.IN_PROGRESS,
        "To Do": TicketStatus.TODO,
        "Doing": TicketStatus.IN_PROGRESS,
        "Done": TicketStatus.DONE
    }
    
    # Priority mappings
    PRIORITY_MAP = {
        1: TicketPriority.CRITICAL,
        2: TicketPriority.HIGH,
        3: TicketPriority.MEDIUM,
        4: TicketPriority.LOW
    }
    
    def __init__(self, organization: str, project: str, personal_access_token: str, 
                 api_base_url: Optional[str] = None):
        """Initialize Azure DevOps integration.
        
        Args:
            organization: Azure DevOps organization name
            project: Project name
            personal_access_token: Personal access token for authentication
            api_base_url: Optional custom API base URL
        """
        super().__init__()
        self.organization = organization
        self.project = project
        self.pat = personal_access_token
        self.api_base_url = api_base_url or f"https://dev.azure.com/{organization}"
        self.project_api_base = f"{self.api_base_url}/{quote(project)}"
        self._session: Optional[aiohttp.ClientSession] = None
        self._areas: Optional[Dict[str, Any]] = None
        self._iterations: Optional[Dict[str, Any]] = None
        
    async def initialize(self) -> None:
        """Initialize the integration."""
        await super().initialize()
        self._session = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth("", self.pat),
            headers={
                "Content-Type": "application/json-patch+json",
                "Accept": "application/json"
            }
        )
        logger.info(f"Azure DevOps integration initialized for {self.organization}/{self.project}")
        
    async def cleanup(self) -> None:
        """Cleanup integration resources."""
        if self._session:
            await self._session.close()
            self._session = None
        await super().cleanup()
        
    async def health_check(self) -> Dict[str, Any]:
        """Check integration health."""
        try:
            # Try to access project information
            url = f"{self.project_api_base}/_apis/projects/{self.project}?api-version={self.API_VERSION}"
            async with self._session.get(url) as response:
                if response.status == 200:
                    project_data = await response.json()
                    return {
                        "healthy": True,
                        "message": f"Connected to project: {project_data['name']}",
                        "details": {
                            "organization": self.organization,
                            "project": self.project,
                            "project_id": project_data['id']
                        }
                    }
                else:
                    return {
                        "healthy": False,
                        "message": f"Failed to connect: HTTP {response.status}",
                        "error": await response.text()
                    }
        except Exception as e:
            return {
                "healthy": False,
                "message": f"Health check failed: {str(e)}",
                "error": str(e)
            }
            
    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate integration configuration."""
        required_fields = ["organization", "project", "personal_access_token"]
        return all(field in config for field in required_fields)
        
    async def get_ticket(self, ticket_id: str) -> Ticket:
        """Get a work item by ID."""
        try:
            url = f"{self.project_api_base}/_apis/wit/workitems/{ticket_id}?api-version={self.API_VERSION}&$expand=All"
            
            async with self._session.get(url) as response:
                if response.status == 404:
                    raise IntegrationError(f"Work item {ticket_id} not found")
                elif response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to get work item: {error_text}")
                    
                data = await response.json()
                return self._convert_work_item_to_ticket(data)
                
        except Exception as e:
            logger.error(f"Error getting work item {ticket_id}: {str(e)}")
            raise IntegrationError(f"Failed to get work item: {str(e)}")
            
    async def create_ticket(self, ticket: Ticket) -> Ticket:
        """Create a new work item."""
        try:
            # Determine work item type
            work_item_type = self._get_work_item_type(ticket.type)
            
            # Build patch document
            patch_doc = [
                {
                    "op": "add",
                    "path": "/fields/System.Title",
                    "value": ticket.title
                }
            ]
            
            if ticket.description:
                patch_doc.append({
                    "op": "add",
                    "path": "/fields/System.Description",
                    "value": ticket.description
                })
                
            if ticket.assignee:
                user = await self.get_user(ticket.assignee)
                if user:
                    patch_doc.append({
                        "op": "add",
                        "path": "/fields/System.AssignedTo",
                        "value": user.email
                    })
                    
            if ticket.priority:
                priority_value = self._get_priority_value(ticket.priority)
                patch_doc.append({
                    "op": "add",
                    "path": "/fields/Microsoft.VSTS.Common.Priority",
                    "value": priority_value
                })
                
            if ticket.labels:
                patch_doc.append({
                    "op": "add",
                    "path": "/fields/System.Tags",
                    "value": "; ".join(ticket.labels)
                })
                
            # Add acceptance criteria if present
            if ticket.acceptance_criteria:
                criteria_text = "\n".join(f"- {criterion}" for criterion in ticket.acceptance_criteria)
                patch_doc.append({
                    "op": "add",
                    "path": "/fields/Microsoft.VSTS.Common.AcceptanceCriteria",
                    "value": criteria_text
                })
                
            url = f"{self.project_api_base}/_apis/wit/workitems/${work_item_type}?api-version={self.API_VERSION}"
            
            async with self._session.patch(url, json=patch_doc) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to create work item: {error_text}")
                    
                data = await response.json()
                return self._convert_work_item_to_ticket(data)
                
        except Exception as e:
            logger.error(f"Error creating work item: {str(e)}")
            raise IntegrationError(f"Failed to create work item: {str(e)}")
            
    async def update_ticket(self, ticket_id: str, updates: Dict[str, Any]) -> Ticket:
        """Update a work item."""
        try:
            patch_doc = []
            
            if "title" in updates:
                patch_doc.append({
                    "op": "replace",
                    "path": "/fields/System.Title",
                    "value": updates["title"]
                })
                
            if "description" in updates:
                patch_doc.append({
                    "op": "replace",
                    "path": "/fields/System.Description",
                    "value": updates["description"]
                })
                
            if "assignee" in updates:
                user = await self.get_user(updates["assignee"]) if updates["assignee"] else None
                patch_doc.append({
                    "op": "replace",
                    "path": "/fields/System.AssignedTo",
                    "value": user.email if user else ""
                })
                
            if "priority" in updates:
                priority_value = self._get_priority_value(updates["priority"])
                patch_doc.append({
                    "op": "replace",
                    "path": "/fields/Microsoft.VSTS.Common.Priority",
                    "value": priority_value
                })
                
            if "labels" in updates:
                patch_doc.append({
                    "op": "replace",
                    "path": "/fields/System.Tags",
                    "value": "; ".join(updates["labels"])
                })
                
            if not patch_doc:
                return await self.get_ticket(ticket_id)
                
            url = f"{self.project_api_base}/_apis/wit/workitems/{ticket_id}?api-version={self.API_VERSION}"
            
            async with self._session.patch(url, json=patch_doc) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to update work item: {error_text}")
                    
                data = await response.json()
                return self._convert_work_item_to_ticket(data)
                
        except Exception as e:
            logger.error(f"Error updating work item {ticket_id}: {str(e)}")
            raise IntegrationError(f"Failed to update work item: {str(e)}")
            
    async def update_ticket_status(self, ticket_id: str, status: TicketStatus, 
                                 comment: Optional[str] = None) -> Ticket:
        """Update work item state."""
        try:
            # Get current work item to determine type
            current = await self.get_ticket(ticket_id)
            
            # Map status to state based on work item type
            state = self._get_state_for_status(status, current.type)
            
            patch_doc = [{
                "op": "replace",
                "path": "/fields/System.State",
                "value": state
            }]
            
            url = f"{self.project_api_base}/_apis/wit/workitems/{ticket_id}?api-version={self.API_VERSION}"
            
            async with self._session.patch(url, json=patch_doc) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to update work item state: {error_text}")
                    
                data = await response.json()
                updated_ticket = self._convert_work_item_to_ticket(data)
                
                # Add comment if provided
                if comment:
                    await self.add_comment(ticket_id, comment)
                    
                return updated_ticket
                
        except Exception as e:
            logger.error(f"Error updating work item status {ticket_id}: {str(e)}")
            raise IntegrationError(f"Failed to update work item status: {str(e)}")
            
    async def add_comment(self, ticket_id: str, comment: str, author: Optional[str] = None) -> Comment:
        """Add a comment to a work item."""
        try:
            url = f"{self.project_api_base}/_apis/wit/workitems/{ticket_id}/comments?api-version={self.API_VERSION}-preview"
            
            data = {
                "text": comment
            }
            
            async with self._session.post(url, json=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to add comment: {error_text}")
                    
                comment_data = await response.json()
                
                return Comment(
                    id=str(comment_data["id"]),
                    content=comment_data["text"],
                    author=comment_data["createdBy"]["displayName"],
                    created_at=datetime.fromisoformat(comment_data["createdDate"].rstrip("Z")),
                    updated_at=datetime.fromisoformat(comment_data["modifiedDate"].rstrip("Z"))
                )
                
        except Exception as e:
            logger.error(f"Error adding comment to work item {ticket_id}: {str(e)}")
            raise IntegrationError(f"Failed to add comment: {str(e)}")
            
    async def get_comments(self, ticket_id: str) -> List[Comment]:
        """Get comments for a work item."""
        try:
            url = f"{self.project_api_base}/_apis/wit/workitems/{ticket_id}/comments?api-version={self.API_VERSION}-preview"
            
            async with self._session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to get comments: {error_text}")
                    
                data = await response.json()
                comments = []
                
                for comment_data in data.get("comments", []):
                    comments.append(Comment(
                        id=str(comment_data["id"]),
                        content=comment_data["text"],
                        author=comment_data["createdBy"]["displayName"],
                        created_at=datetime.fromisoformat(comment_data["createdDate"].rstrip("Z")),
                        updated_at=datetime.fromisoformat(comment_data["modifiedDate"].rstrip("Z"))
                    ))
                    
                return comments
                
        except Exception as e:
            logger.error(f"Error getting comments for work item {ticket_id}: {str(e)}")
            raise IntegrationError(f"Failed to get comments: {str(e)}")
            
    async def search_tickets(self, query: str, max_results: int = 50) -> List[Ticket]:
        """Search work items using WIQL."""
        try:
            wiql_query = {
                "query": f"""
                    SELECT [System.Id], [System.Title], [System.State], [System.AssignedTo]
                    FROM WorkItems
                    WHERE [System.TeamProject] = '{self.project}'
                    AND ({query})
                    ORDER BY [System.ChangedDate] DESC
                """
            }
            
            url = f"{self.project_api_base}/_apis/wit/wiql?api-version={self.API_VERSION}"
            
            async with self._session.post(url, json=wiql_query) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to search work items: {error_text}")
                    
                data = await response.json()
                work_item_ids = [item["id"] for item in data.get("workItems", [])][:max_results]
                
                if not work_item_ids:
                    return []
                    
                # Fetch work items in batches
                tickets = []
                batch_size = 20
                
                for i in range(0, len(work_item_ids), batch_size):
                    batch_ids = work_item_ids[i:i + batch_size]
                    batch_url = f"{self.project_api_base}/_apis/wit/workitems?ids={','.join(map(str, batch_ids))}&api-version={self.API_VERSION}"
                    
                    async with self._session.get(batch_url) as batch_response:
                        if batch_response.status == 200:
                            batch_data = await batch_response.json()
                            for work_item in batch_data.get("value", []):
                                tickets.append(self._convert_work_item_to_ticket(work_item))
                                
                return tickets
                
        except Exception as e:
            logger.error(f"Error searching work items: {str(e)}")
            raise IntegrationError(f"Failed to search work items: {str(e)}")
            
    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user information."""
        try:
            # Try to search for user by display name or email
            url = f"{self.api_base_url}/_apis/identities?searchFilter=General&filterValue={quote(user_id)}&api-version={self.API_VERSION}"
            
            async with self._session.get(url) as response:
                if response.status != 200:
                    return None
                    
                data = await response.json()
                if data.get("count", 0) > 0:
                    user_data = data["value"][0]
                    return User(
                        id=user_data.get("id", user_id),
                        username=user_data.get("principalName", user_id),
                        email=user_data.get("mailAddress", user_id),
                        display_name=user_data.get("displayName", user_id)
                    )
                    
                # Fallback to basic user object
                return User(
                    id=user_id,
                    username=user_id,
                    email=user_id,
                    display_name=user_id
                )
                
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {str(e)}")
            return None
            
    async def link_pull_request(self, ticket_id: str, pr_url: str, pr_id: str) -> bool:
        """Link a pull request to a work item."""
        try:
            patch_doc = [{
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "ArtifactLink",
                    "url": pr_url,
                    "attributes": {
                        "name": "Pull Request",
                        "comment": f"Linked PR #{pr_id}"
                    }
                }
            }]
            
            url = f"{self.project_api_base}/_apis/wit/workitems/{ticket_id}?api-version={self.API_VERSION}"
            
            async with self._session.patch(url, json=patch_doc) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to link PR: {error_text}")
                    return False
                    
                await self.add_comment(ticket_id, f"Pull Request #{pr_id} has been linked to this work item.")
                return True
                
        except Exception as e:
            logger.error(f"Error linking PR to work item {ticket_id}: {str(e)}")
            return False
            
    async def setup_webhook(self, callback_url: str, events: Optional[List[str]] = None) -> str:
        """Setup webhook for work item updates."""
        try:
            # Azure DevOps uses Service Hooks for webhooks
            if events is None:
                events = ["workitem.created", "workitem.updated"]
                
            webhook_data = {
                "publisherId": "tfs",
                "eventType": "workitem.updated",
                "resourceVersion": "1.0",
                "consumerId": "webHooks",
                "consumerActionId": "httpRequest",
                "publisherInputs": {
                    "projectId": self.project,
                    "areaPath": "",
                    "workItemType": "",
                    "changedFields": "System.State,System.AssignedTo"
                },
                "consumerInputs": {
                    "url": callback_url,
                    "httpHeaders": "Content-Type:application/json",
                    "basicAuthUsername": "",
                    "basicAuthPassword": ""
                }
            }
            
            url = f"{self.api_base_url}/_apis/hooks/subscriptions?api-version={self.API_VERSION}"
            
            async with self._session.post(url, json=webhook_data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to setup webhook: {error_text}")
                    
                data = await response.json()
                return data["id"]
                
        except Exception as e:
            logger.error(f"Error setting up webhook: {str(e)}")
            raise IntegrationError(f"Failed to setup webhook: {str(e)}")
            
    async def validate_webhook(self, headers: Dict[str, str], body: bytes) -> bool:
        """Validate webhook request."""
        # Azure DevOps doesn't use webhook signatures by default
        # You can implement custom validation based on your security requirements
        return True
        
    async def parse_webhook_event(self, headers: Dict[str, str], body: Dict[str, Any]) -> WebhookEvent:
        """Parse webhook event data."""
        try:
            event_type = body.get("eventType", "")
            resource = body.get("resource", {})
            
            if event_type == "workitem.created":
                webhook_type = WebhookEventType.TICKET_CREATED
            elif event_type == "workitem.updated":
                # Check if assignee changed
                if "System.AssignedTo" in resource.get("fields", {}):
                    webhook_type = WebhookEventType.TICKET_ASSIGNED
                else:
                    webhook_type = WebhookEventType.TICKET_UPDATED
            else:
                webhook_type = WebhookEventType.OTHER
                
            # Extract work item ID
            work_item_id = resource.get("id", "")
            if not work_item_id and resource.get("workItemId"):
                work_item_id = resource["workItemId"]
                
            return WebhookEvent(
                id=body.get("id", ""),
                type=webhook_type,
                ticket_id=str(work_item_id),
                data=body,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Error parsing webhook event: {str(e)}")
            raise IntegrationError(f"Failed to parse webhook event: {str(e)}")
            
    def _convert_work_item_to_ticket(self, work_item: Dict[str, Any]) -> Ticket:
        """Convert Azure DevOps work item to Ticket object."""
        fields = work_item.get("fields", {})
        
        # Extract basic fields
        ticket_id = str(work_item["id"])
        title = fields.get("System.Title", "")
        description = fields.get("System.Description", "")
        state = fields.get("System.State", "New")
        work_item_type = fields.get("System.WorkItemType", "Task")
        
        # Map to our ticket model
        status = self.STATE_TO_STATUS_MAP.get(state, TicketStatus.TODO)
        ticket_type = self.WORK_ITEM_TYPE_MAP.get(work_item_type, TicketType.TASK)
        
        # Extract priority
        priority_value = fields.get("Microsoft.VSTS.Common.Priority", 3)
        priority = self.PRIORITY_MAP.get(priority_value, TicketPriority.MEDIUM)
        
        # Extract assignee
        assignee = None
        assigned_to = fields.get("System.AssignedTo")
        if assigned_to:
            assignee = assigned_to.get("displayName", assigned_to.get("uniqueName", ""))
            
        # Extract labels from tags
        tags = fields.get("System.Tags", "")
        labels = [tag.strip() for tag in tags.split(";") if tag.strip()] if tags else []
        
        # Extract dates
        created_date = fields.get("System.CreatedDate", "")
        changed_date = fields.get("System.ChangedDate", "")
        
        created_at = datetime.fromisoformat(created_date.rstrip("Z")) if created_date else datetime.utcnow()
        updated_at = datetime.fromisoformat(changed_date.rstrip("Z")) if changed_date else created_at
        
        # Extract acceptance criteria
        acceptance_criteria = []
        criteria_text = fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", "")
        if criteria_text:
            # Parse acceptance criteria (assuming bullet points)
            criteria_lines = criteria_text.strip().split("\n")
            for line in criteria_lines:
                line = line.strip()
                if line.startswith("-") or line.startswith("*"):
                    acceptance_criteria.append(line[1:].strip())
                elif line:
                    acceptance_criteria.append(line)
                    
        # Extract repository info from description or custom fields
        repository = fields.get("Custom.Repository", "")
        
        return Ticket(
            id=ticket_id,
            title=title,
            description=description,
            status=status,
            type=ticket_type,
            priority=priority,
            assignee=assignee,
            labels=labels,
            created_at=created_at,
            updated_at=updated_at,
            repository=repository if repository else None,
            acceptance_criteria=acceptance_criteria,
            metadata={
                "state": state,
                "work_item_type": work_item_type,
                "area_path": fields.get("System.AreaPath", ""),
                "iteration_path": fields.get("System.IterationPath", ""),
                "url": work_item.get("url", "")
            }
        )
        
    def _get_work_item_type(self, ticket_type: TicketType) -> str:
        """Get Azure DevOps work item type from ticket type."""
        type_map = {
            TicketType.BUG: "Bug",
            TicketType.TASK: "Task",
            TicketType.STORY: "User Story",
            TicketType.EPIC: "Epic"
        }
        return type_map.get(ticket_type, "Task")
        
    def _get_priority_value(self, priority: TicketPriority) -> int:
        """Get Azure DevOps priority value from ticket priority."""
        priority_map = {
            TicketPriority.CRITICAL: 1,
            TicketPriority.HIGH: 2,
            TicketPriority.MEDIUM: 3,
            TicketPriority.LOW: 4
        }
        return priority_map.get(priority, 3)
        
    def _get_state_for_status(self, status: TicketStatus, ticket_type: TicketType) -> str:
        """Map ticket status to Azure DevOps state based on work item type."""
        # Basic mapping that works for most work item types
        status_map = {
            TicketStatus.TODO: "New",
            TicketStatus.IN_PROGRESS: "Active",
            TicketStatus.IN_REVIEW: "Resolved",
            TicketStatus.DONE: "Closed",
            TicketStatus.CANCELLED: "Removed"
        }
        
        # Adjust for specific work item types if needed
        if ticket_type == TicketType.BUG:
            if status == TicketStatus.IN_PROGRESS:
                return "Active"
        elif ticket_type == TicketType.STORY:
            if status == TicketStatus.TODO:
                return "New"
                
        return status_map.get(status, "New")