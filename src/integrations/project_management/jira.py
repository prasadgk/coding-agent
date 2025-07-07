"""JIRA integration for project management."""

import asyncio
import aiohttp
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

from ..base.project_management import (
    ProjectManagementPlugin,
    Ticket,
    TicketComment,
    TicketStatus,
    TicketPriority,
    TicketType,
    User,
    WebhookEvent
)
from ...utils.exceptions import IntegrationError, AuthenticationError


logger = logging.getLogger(__name__)


class JIRAIntegration(ProjectManagementPlugin):
    """JIRA integration implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize JIRA integration.
        
        Args:
            config: Configuration with keys:
                - server_url: JIRA server URL
                - username: JIRA username (for server) or email (for cloud)
                - api_token: API token or password
                - project_key: Default project key
                - ai_agent_username: Username of AI agent in JIRA
                - webhook_secret: Optional webhook secret
        """
        super().__init__(config)
        self.server_url = config["server_url"].rstrip("/")
        self.username = config["username"]
        self.api_token = config["api_token"]
        self.project_key = config.get("project_key", "")
        self.ai_agent_username = config.get("ai_agent_username", "ai-agent")
        self.webhook_secret = config.get("webhook_secret")
        
        # Create session with authentication
        self.session: Optional[aiohttp.ClientSession] = None
        self._auth_header = self._create_auth_header()
        
        # Cache for user lookups
        self._user_cache: Dict[str, User] = {}
        
        # JIRA-specific mappings
        self._status_map = {
            "to do": TicketStatus.TODO,
            "todo": TicketStatus.TODO,
            "open": TicketStatus.OPEN,
            "in progress": TicketStatus.IN_PROGRESS,
            "in review": TicketStatus.IN_REVIEW,
            "code review": TicketStatus.IN_REVIEW,
            "testing": TicketStatus.TESTING,
            "done": TicketStatus.DONE,
            "closed": TicketStatus.CLOSED,
            "resolved": TicketStatus.DONE,
            "blocked": TicketStatus.BLOCKED,
            "cancelled": TicketStatus.CANCELLED,
            "won't do": TicketStatus.CANCELLED
        }
        
        self._priority_map = {
            "highest": TicketPriority.CRITICAL,
            "critical": TicketPriority.CRITICAL,
            "high": TicketPriority.HIGH,
            "medium": TicketPriority.MEDIUM,
            "low": TicketPriority.LOW,
            "lowest": TicketPriority.TRIVIAL,
            "trivial": TicketPriority.TRIVIAL
        }
        
        self._type_map = {
            "bug": TicketType.BUG,
            "feature": TicketType.FEATURE,
            "task": TicketType.TASK,
            "story": TicketType.STORY,
            "epic": TicketType.EPIC,
            "sub-task": TicketType.SUBTASK,
            "improvement": TicketType.IMPROVEMENT
        }
    
    def _create_auth_header(self) -> str:
        """Create Basic auth header."""
        credentials = f"{self.username}:{self.api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    async def initialize(self):
        """Initialize the integration."""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": self._auth_header,
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }
            )
        
        # Verify authentication
        await self.authenticate()
    
    async def cleanup(self):
        """Clean up resources."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def authenticate(self) -> bool:
        """Authenticate with JIRA."""
        try:
            # Test authentication by getting current user
            url = urljoin(self.server_url, "/rest/api/2/myself")
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Authenticated as {data.get('displayName', 'Unknown')}")
                    return True
                elif response.status == 401:
                    raise AuthenticationError("Invalid JIRA credentials")
                else:
                    raise IntegrationError(
                        f"JIRA authentication failed with status {response.status}",
                        integration_name="jira"
                    )
        except aiohttp.ClientError as e:
            raise IntegrationError(
                f"Failed to connect to JIRA: {e}",
                integration_name="jira"
            )
    
    async def get_ticket(self, ticket_id: str) -> Ticket:
        """Get ticket details by ID."""
        return await self.get_ticket_by_key(ticket_id)
    
    async def get_ticket_by_key(self, ticket_key: str) -> Ticket:
        """Get ticket details by key."""
        url = urljoin(self.server_url, f"/rest/api/2/issue/{ticket_key}")
        params = {
            "expand": "renderedFields,names,schema,operations,editmeta,changelog"
        }
        
        async with self.session.get(url, params=params) as response:
            if response.status == 404:
                raise IntegrationError(
                    f"Ticket {ticket_key} not found",
                    integration_name="jira"
                )
            elif response.status != 200:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to get ticket: {text}",
                    integration_name="jira"
                )
            
            data = await response.json()
            return await self._parse_ticket(data)
    
    async def _parse_ticket(self, data: Dict[str, Any]) -> Ticket:
        """Parse JIRA issue data into Ticket object."""
        fields = data["fields"]
        
        # Parse users
        assignee = await self._parse_user(fields.get("assignee")) if fields.get("assignee") else None
        reporter = await self._parse_user(fields.get("reporter")) if fields.get("reporter") else None
        
        # Parse dates
        created_at = datetime.fromisoformat(fields["created"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(fields["updated"].replace("Z", "+00:00"))
        due_date = None
        if fields.get("duedate"):
            due_date = datetime.fromisoformat(fields["duedate"] + "T00:00:00+00:00")
        
        # Extract acceptance criteria from description or custom field
        acceptance_criteria = self._extract_acceptance_criteria(fields)
        
        # Get repository URL from custom field or description
        repository_url = self._extract_repository_url(fields)
        
        return Ticket(
            id=data["id"],
            key=data["key"],
            title=fields["summary"],
            description=fields.get("description", ""),
            status=self.map_status(fields["status"]["name"]),
            priority=self.map_priority(fields["priority"]["name"]),
            ticket_type=self._map_issue_type(fields["issuetype"]["name"]),
            assignee=assignee,
            reporter=reporter,
            created_at=created_at,
            updated_at=updated_at,
            due_date=due_date,
            labels=[label["name"] for label in fields.get("labels", [])],
            components=[comp["name"] for comp in fields.get("components", [])],
            fix_versions=[ver["name"] for ver in fields.get("fixVersions", [])],
            acceptance_criteria=acceptance_criteria,
            repository_url=repository_url,
            story_points=fields.get("customfield_10004"),  # Common story points field
            parent_id=fields.get("parent", {}).get("id"),
            subtask_ids=[subtask["id"] for subtask in fields.get("subtasks", [])],
            metadata={
                "jira_url": f"{self.server_url}/browse/{data['key']}",
                "project_key": fields["project"]["key"],
                "issue_type": fields["issuetype"]["name"]
            }
        )
    
    async def _parse_user(self, user_data: Dict[str, Any]) -> User:
        """Parse JIRA user data."""
        user_id = user_data["accountId"] if "accountId" in user_data else user_data["key"]
        
        # Check cache
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        
        user = User(
            id=user_id,
            username=user_data.get("name", user_data.get("key", user_id)),
            display_name=user_data["displayName"],
            email=user_data.get("emailAddress"),
            avatar_url=user_data.get("avatarUrls", {}).get("48x48"),
            platform_specific={"jira": user_data}
        )
        
        self._user_cache[user_id] = user
        return user
    
    def _extract_acceptance_criteria(self, fields: Dict[str, Any]) -> List[str]:
        """Extract acceptance criteria from description or custom fields."""
        criteria = []
        
        # Check common custom field IDs for acceptance criteria
        for field_id in ["customfield_10100", "customfield_10101", "customfield_10102"]:
            if field_id in fields and fields[field_id]:
                if isinstance(fields[field_id], str):
                    # Parse criteria from text
                    lines = fields[field_id].split("\n")
                    for line in lines:
                        line = line.strip()
                        if line and line.startswith(("*", "-", "•")):
                            criteria.append(line[1:].strip())
                        elif line:
                            criteria.append(line)
                elif isinstance(fields[field_id], list):
                    criteria.extend(fields[field_id])
        
        # Also check description for acceptance criteria section
        if not criteria and fields.get("description"):
            description = fields["description"]
            if "acceptance criteria" in description.lower():
                # Extract section after "Acceptance Criteria"
                parts = description.split("Acceptance Criteria", 1)
                if len(parts) > 1:
                    criteria_text = parts[1].split("\n\n")[0]
                    for line in criteria_text.split("\n"):
                        line = line.strip()
                        if line and line.startswith(("*", "-", "•")):
                            criteria.append(line[1:].strip())
        
        return criteria
    
    def _extract_repository_url(self, fields: Dict[str, Any]) -> Optional[str]:
        """Extract repository URL from custom fields or description."""
        # Check common custom field IDs for repository URL
        for field_id in ["customfield_10200", "customfield_10201", "customfield_10202"]:
            if field_id in fields and fields[field_id]:
                return fields[field_id]
        
        # Check description for repository URL
        if fields.get("description"):
            import re
            urls = re.findall(
                r'https?://(?:github\.com|gitlab\.com|bitbucket\.org)/[\w\-\.]+/[\w\-\.]+',
                fields["description"]
            )
            if urls:
                return urls[0]
        
        return None
    
    def _map_issue_type(self, jira_type: str) -> TicketType:
        """Map JIRA issue type to standard type."""
        return self._type_map.get(jira_type.lower(), TicketType.TASK)
    
    def map_status(self, platform_status: str) -> TicketStatus:
        """Map JIRA status to standard status."""
        return self._status_map.get(platform_status.lower(), TicketStatus.TODO)
    
    def map_priority(self, platform_priority: str) -> TicketPriority:
        """Map JIRA priority to standard priority."""
        return self._priority_map.get(platform_priority.lower(), TicketPriority.MEDIUM)
    
    async def update_ticket_status(
        self,
        ticket_id: str,
        status: TicketStatus,
        comment: Optional[str] = None
    ) -> bool:
        """Update ticket status using transitions."""
        # Get available transitions
        transitions = await self._get_transitions(ticket_id)
        
        # Find matching transition
        target_status_names = self._get_jira_status_names(status)
        transition = None
        
        for trans in transitions:
            if trans["to"]["name"].lower() in target_status_names:
                transition = trans
                break
        
        if not transition:
            available = [t["to"]["name"] for t in transitions]
            raise IntegrationError(
                f"No transition available to status {status.value}. Available: {available}",
                integration_name="jira"
            )
        
        # Perform transition
        url = urljoin(self.server_url, f"/rest/api/2/issue/{ticket_id}/transitions")
        data = {
            "transition": {"id": transition["id"]}
        }
        
        if comment:
            data["update"] = {
                "comment": [{"add": {"body": comment}}]
            }
        
        async with self.session.post(url, json=data) as response:
            if response.status == 204:
                return True
            else:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to update ticket status: {text}",
                    integration_name="jira"
                )
    
    async def _get_transitions(self, ticket_id: str) -> List[Dict[str, Any]]:
        """Get available transitions for a ticket."""
        url = urljoin(self.server_url, f"/rest/api/2/issue/{ticket_id}/transitions")
        
        async with self.session.get(url) as response:
            if response.status != 200:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to get transitions: {text}",
                    integration_name="jira"
                )
            
            data = await response.json()
            return data["transitions"]
    
    def _get_jira_status_names(self, status: TicketStatus) -> List[str]:
        """Get possible JIRA status names for a standard status."""
        # Reverse mapping
        names = []
        for jira_status, std_status in self._status_map.items():
            if std_status == status:
                names.append(jira_status)
        
        # Add the standard status name as fallback
        names.append(status.value.replace("_", " "))
        return names
    
    async def add_comment(
        self,
        ticket_id: str,
        comment: str,
        is_internal: bool = False
    ) -> TicketComment:
        """Add a comment to a ticket."""
        url = urljoin(self.server_url, f"/rest/api/2/issue/{ticket_id}/comment")
        
        data = {
            "body": comment
        }
        
        if is_internal:
            # JIRA Service Desk internal comments
            data["properties"] = [
                {"key": "sd.public.comment", "value": {"internal": True}}
            ]
        
        async with self.session.post(url, json=data) as response:
            if response.status != 201:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to add comment: {text}",
                    integration_name="jira"
                )
            
            comment_data = await response.json()
            author = await self._parse_user(comment_data["author"])
            
            return TicketComment(
                id=comment_data["id"],
                ticket_id=ticket_id,
                author=author,
                content=comment_data["body"],
                created_at=datetime.fromisoformat(
                    comment_data["created"].replace("Z", "+00:00")
                ),
                updated_at=datetime.fromisoformat(
                    comment_data["updated"].replace("Z", "+00:00")
                ) if comment_data.get("updated") else None,
                is_internal=is_internal,
                metadata={"jira": comment_data}
            )
    
    async def update_ticket(self, ticket_id: str, updates: Dict[str, Any]) -> Ticket:
        """Update ticket fields."""
        url = urljoin(self.server_url, f"/rest/api/2/issue/{ticket_id}")
        
        # Convert updates to JIRA format
        fields = {}
        
        if "title" in updates:
            fields["summary"] = updates["title"]
        if "description" in updates:
            fields["description"] = updates["description"]
        if "labels" in updates:
            fields["labels"] = updates["labels"]
        if "priority" in updates:
            # Need to look up priority ID
            fields["priority"] = {"name": updates["priority"]}
        if "assignee" in updates:
            fields["assignee"] = {"name": updates["assignee"]}
        if "due_date" in updates:
            fields["duedate"] = updates["due_date"].strftime("%Y-%m-%d") if updates["due_date"] else None
        
        data = {"fields": fields}
        
        async with self.session.put(url, json=data) as response:
            if response.status != 204:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to update ticket: {text}",
                    integration_name="jira"
                )
        
        # Return updated ticket
        return await self.get_ticket(ticket_id)
    
    async def search_tickets(self, query: str, limit: int = 50) -> List[Ticket]:
        """Search tickets using JQL."""
        url = urljoin(self.server_url, "/rest/api/2/search")
        
        data = {
            "jql": query,
            "maxResults": limit,
            "fields": ["*all"],
            "expand": ["renderedFields", "names", "schema"]
        }
        
        async with self.session.post(url, json=data) as response:
            if response.status != 200:
                text = await response.text()
                raise IntegrationError(
                    f"Search failed: {text}",
                    integration_name="jira"
                )
            
            result = await response.json()
            tickets = []
            
            for issue in result["issues"]:
                try:
                    ticket = await self._parse_ticket(issue)
                    tickets.append(ticket)
                except Exception as e:
                    logger.error(f"Failed to parse issue {issue.get('key', 'unknown')}: {e}")
            
            return tickets
    
    async def assign_ticket(self, ticket_id: str, assignee: str) -> None:
        """Assign ticket to a user."""
        await self.update_ticket(ticket_id, {"assignee": assignee})
    
    async def link_pull_request(self, ticket_id: str, pr_url: str) -> None:
        """Link a pull request to the ticket."""
        # Add as web link
        url = urljoin(self.server_url, f"/rest/api/2/issue/{ticket_id}/remotelink")
        
        # Extract PR info from URL
        import re
        pr_match = re.match(
            r'https?://(?P<host>[\w\.\-]+)/(?P<owner>[\w\-]+)/(?P<repo>[\w\-]+)/pull/(?P<number>\d+)',
            pr_url
        )
        
        if pr_match:
            data = {
                "globalId": f"pr={pr_url}",
                "application": {
                    "type": "com.github",
                    "name": "GitHub"
                },
                "relationship": "Pull Request",
                "object": {
                    "url": pr_url,
                    "title": f"Pull Request #{pr_match.group('number')}",
                    "icon": {
                        "url16x16": "https://github.githubassets.com/favicon.ico"
                    }
                }
            }
        else:
            data = {
                "globalId": f"pr={pr_url}",
                "relationship": "Pull Request",
                "object": {
                    "url": pr_url,
                    "title": "Pull Request"
                }
            }
        
        async with self.session.post(url, json=data) as response:
            if response.status not in [200, 201]:
                text = await response.text()
                logger.warning(f"Failed to link PR: {text}")
        
        # Also add as comment
        await self.add_comment(
            ticket_id,
            f"🔗 Pull Request: {pr_url}"
        )
    
    async def parse_webhook(
        self,
        headers: Dict[str, str],
        body: Dict[str, Any]
    ) -> WebhookEvent:
        """Parse JIRA webhook payload."""
        webhook_event = body.get("webhookEvent", "")
        issue = body.get("issue", {})
        
        # Parse user who triggered the event
        user_data = body.get("user", {})
        user = await self._parse_user(user_data) if user_data else None
        
        # Determine event type
        event_type = "unknown"
        if "created" in webhook_event:
            event_type = "ticket_created"
        elif "updated" in webhook_event:
            event_type = "ticket_updated"
        elif "deleted" in webhook_event:
            event_type = "ticket_deleted"
        elif "comment" in webhook_event:
            event_type = "comment_added"
        
        # Extract changes
        changes = {}
        if "changelog" in body:
            for item in body["changelog"]["items"]:
                changes[item["field"]] = {
                    "from": item.get("fromString"),
                    "to": item.get("toString")
                }
        
        return WebhookEvent(
            event_type=event_type,
            ticket_id=issue.get("id", ""),
            ticket_key=issue.get("key", ""),
            timestamp=datetime.fromisoformat(
                body.get("timestamp", datetime.utcnow().isoformat())
            ),
            changes=changes,
            user=user,
            platform="jira",
            raw_payload=body
        )
    
    async def validate_webhook(
        self,
        headers: Dict[str, str],
        body: bytes,
        secret: Optional[str] = None
    ) -> bool:
        """Validate JIRA webhook signature."""
        if not secret and not self.webhook_secret:
            # No secret configured, accept all
            return True
        
        secret = secret or self.webhook_secret
        
        # JIRA uses different header names based on version
        signature = headers.get("X-Hub-Signature") or headers.get("X-Atlassian-Webhook-Signature")
        
        if not signature:
            logger.warning("No webhook signature found in headers")
            return False
        
        # Calculate expected signature
        expected = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(signature, f"sha256={expected}")
    
    async def setup_webhook(
        self,
        webhook_url: str,
        events: List[str]
    ) -> str:
        """Set up JIRA webhook."""
        url = urljoin(self.server_url, "/rest/webhooks/1.0/webhook")
        
        # Map our events to JIRA events
        jira_events = []
        event_mapping = {
            "ticket_created": "jira:issue_created",
            "ticket_updated": "jira:issue_updated",
            "ticket_deleted": "jira:issue_deleted",
            "comment_added": "comment_created",
            "*": ["jira:issue_created", "jira:issue_updated", "comment_created"]
        }
        
        for event in events:
            mapped = event_mapping.get(event, [])
            if isinstance(mapped, str):
                jira_events.append(mapped)
            else:
                jira_events.extend(mapped)
        
        data = {
            "name": f"AI Agent Webhook - {datetime.utcnow().isoformat()}",
            "url": webhook_url,
            "events": list(set(jira_events)),  # Remove duplicates
            "filters": {
                "issue-related-events-section": f"project = {self.project_key}"
            } if self.project_key else {},
            "excludeBody": False
        }
        
        async with self.session.post(url, json=data) as response:
            if response.status != 201:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to create webhook: {text}",
                    integration_name="jira"
                )
            
            webhook_data = await response.json()
            return webhook_data["self"].split("/")[-1]  # Extract ID from URL
    
    async def delete_webhook(self, webhook_id: str) -> None:
        """Delete a JIRA webhook."""
        url = urljoin(self.server_url, f"/rest/webhooks/1.0/webhook/{webhook_id}")
        
        async with self.session.delete(url) as response:
            if response.status != 204:
                text = await response.text()
                logger.warning(f"Failed to delete webhook: {text}")
    
    async def get_user(self, user_id: str) -> User:
        """Get user details."""
        # Check cache first
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        
        # Try different endpoints based on JIRA version
        for endpoint in [f"/rest/api/2/user?accountId={user_id}", f"/rest/api/2/user?key={user_id}"]:
            url = urljoin(self.server_url, endpoint)
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return await self._parse_user(data)
        
        raise IntegrationError(
            f"User {user_id} not found",
            integration_name="jira"
        )
    
    async def get_current_user(self) -> User:
        """Get current authenticated user."""
        url = urljoin(self.server_url, "/rest/api/2/myself")
        
        async with self.session.get(url) as response:
            if response.status != 200:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to get current user: {text}",
                    integration_name="jira"
                )
            
            data = await response.json()
            return await self._parse_user(data)