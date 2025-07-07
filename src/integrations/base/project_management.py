"""Base classes for project management integrations."""

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Callable
import asyncio
from .plugin import Plugin


class TicketStatus(str, Enum):
    """Standard ticket statuses."""
    TODO = "todo"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    TESTING = "testing"
    DONE = "done"
    CLOSED = "closed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TicketPriority(str, Enum):
    """Standard ticket priorities."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    TRIVIAL = "trivial"


class TicketType(str, Enum):
    """Standard ticket types."""
    BUG = "bug"
    FEATURE = "feature"
    TASK = "task"
    STORY = "story"
    EPIC = "epic"
    SUBTASK = "subtask"
    IMPROVEMENT = "improvement"


@dataclass
class User:
    """User representation across platforms."""
    id: str
    username: str
    display_name: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    platform_specific: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Ticket:
    """Represents a ticket/issue/work item."""
    id: str
    key: str  # e.g., PROJ-123
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    ticket_type: TicketType
    assignee: Optional[User] = None
    reporter: Optional[User] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_date: Optional[datetime] = None
    labels: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)
    fix_versions: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    repository_url: Optional[str] = None
    branch_name: Optional[str] = None
    pull_request_url: Optional[str] = None
    story_points: Optional[int] = None
    parent_id: Optional[str] = None
    subtask_ids: List[str] = field(default_factory=list)
    linked_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ticket to dictionary."""
        return {
            "id": self.id,
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "ticket_type": self.ticket_type.value,
            "assignee": self.assignee.username if self.assignee else None,
            "reporter": self.reporter.username if self.reporter else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "labels": self.labels,
            "acceptance_criteria": self.acceptance_criteria,
            "repository_url": self.repository_url,
            "branch_name": self.branch_name,
            "pull_request_url": self.pull_request_url,
            "metadata": self.metadata
        }
    
    def get_ai_agent_instructions(self) -> str:
        """Extract AI agent instructions from description and criteria."""
        instructions = [self.description]
        
        if self.acceptance_criteria:
            instructions.append("\n\nAcceptance Criteria:")
            instructions.extend(f"- {criterion}" for criterion in self.acceptance_criteria)
        
        return "\n".join(instructions)


@dataclass
class TicketComment:
    """Represents a comment on a ticket."""
    id: str
    ticket_id: str
    author: User
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_internal: bool = False
    attachments: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WebhookEvent:
    """Represents a webhook event from project management tool."""
    event_type: str
    ticket_id: str
    ticket_key: str
    timestamp: datetime
    changes: Dict[str, Any]
    user: User
    platform: str
    raw_payload: Dict[str, Any]


class ProjectManagementPlugin(Plugin):
    """Base class for project management integrations."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with configuration."""
        super().__init__(config)
        self.webhook_handlers: Dict[str, List[Callable]] = {}
    
    @abstractmethod
    async def get_ticket(self, ticket_id: str) -> Ticket:
        """Get ticket details by ID."""
        pass
    
    @abstractmethod
    async def get_ticket_by_key(self, ticket_key: str) -> Ticket:
        """Get ticket details by key (e.g., PROJ-123)."""
        pass
    
    @abstractmethod
    async def update_ticket_status(self, ticket_id: str, status: TicketStatus) -> None:
        """Update ticket status."""
        pass
    
    @abstractmethod
    async def add_comment(self, ticket_id: str, comment: str, is_internal: bool = False) -> TicketComment:
        """Add a comment to a ticket."""
        pass
    
    @abstractmethod
    async def update_ticket(self, ticket_id: str, updates: Dict[str, Any]) -> Ticket:
        """Update ticket with arbitrary fields."""
        pass
    
    @abstractmethod
    async def search_tickets(self, query: str, limit: int = 50) -> List[Ticket]:
        """Search for tickets using platform-specific query."""
        pass
    
    @abstractmethod
    async def assign_ticket(self, ticket_id: str, assignee: str) -> None:
        """Assign ticket to a user."""
        pass
    
    @abstractmethod
    async def link_pull_request(self, ticket_id: str, pr_url: str) -> None:
        """Link a pull request to the ticket."""
        pass
    
    @abstractmethod
    async def parse_webhook(self, headers: Dict[str, str], body: Dict[str, Any]) -> WebhookEvent:
        """Parse webhook payload into standard format."""
        pass
    
    @abstractmethod
    async def setup_webhook(self, webhook_url: str, events: List[str]) -> str:
        """Setup webhook for receiving events."""
        pass
    
    @abstractmethod
    async def delete_webhook(self, webhook_id: str) -> None:
        """Delete a webhook."""
        pass
    
    async def is_ticket_assigned_to_agent(self, ticket: Ticket, agent_identifier: str) -> bool:
        """Check if ticket is assigned to the AI agent."""
        return ticket.assignee and ticket.assignee.username == agent_identifier
    
    def register_webhook_handler(
        self,
        event_type: str,
        handler: Callable[[WebhookEvent], asyncio.Future]
    ):
        """Register a handler for webhook events."""
        if event_type not in self.webhook_handlers:
            self.webhook_handlers[event_type] = []
        self.webhook_handlers[event_type].append(handler)
    
    async def handle_webhook_event(self, event: WebhookEvent):
        """Handle incoming webhook event."""
        handlers = self.webhook_handlers.get(event.event_type, [])
        handlers.extend(self.webhook_handlers.get("*", []))  # Universal handlers
        
        if handlers:
            await asyncio.gather(
                *[handler(event) for handler in handlers],
                return_exceptions=True
            )
    
    def map_status(self, platform_status: str) -> TicketStatus:
        """Map platform-specific status to standard status."""
        # Override in subclasses for custom mapping
        status_map = {
            "todo": TicketStatus.TODO,
            "in_progress": TicketStatus.IN_PROGRESS,
            "in_review": TicketStatus.IN_REVIEW,
            "testing": TicketStatus.TESTING,
            "done": TicketStatus.DONE,
            "blocked": TicketStatus.BLOCKED,
            "cancelled": TicketStatus.CANCELLED
        }
        return status_map.get(platform_status.lower(), TicketStatus.TODO)
    
    def map_priority(self, platform_priority: str) -> TicketPriority:
        """Map platform-specific priority to standard priority."""
        # Override in subclasses for custom mapping
        priority_map = {
            "critical": TicketPriority.CRITICAL,
            "high": TicketPriority.HIGH,
            "medium": TicketPriority.MEDIUM,
            "low": TicketPriority.LOW
        }
        return priority_map.get(platform_priority.lower(), TicketPriority.MEDIUM)
    
    @abstractmethod
    async def validate_webhook(
        self,
        headers: Dict[str, str],
        body: bytes,
        secret: Optional[str] = None
    ) -> bool:
        """Validate webhook request."""
        pass
    
    @abstractmethod
    async def get_user(self, user_id: str) -> User:
        """Get user details."""
        pass
    
    @abstractmethod
    async def get_current_user(self) -> User:
        """Get current authenticated user."""
        pass