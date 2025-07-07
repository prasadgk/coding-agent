"""Base classes for communication integrations."""

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional
from .plugin import Plugin


class NotificationLevel(str, Enum):
    """Notification importance levels."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MessageFormat(str, Enum):
    """Message formatting types."""
    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"
    HTML = "html"
    RICH = "rich"  # Platform-specific rich formatting


@dataclass
class User:
    """Represents a user in the communication platform."""
    id: str
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    is_bot: bool = False
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Channel:
    """Represents a communication channel."""
    id: str
    name: str
    type: str  # public, private, direct
    topic: Optional[str] = None
    purpose: Optional[str] = None
    members: List[str] = field(default_factory=list)
    is_archived: bool = False
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """Represents a message to be sent."""
    channel: str
    text: str
    level: NotificationLevel = NotificationLevel.INFO
    format: MessageFormat = MessageFormat.PLAIN_TEXT
    thread_id: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "channel": self.channel,
            "text": self.text,
            "level": self.level.value,
            "format": self.format.value,
            "thread_id": self.thread_id,
            "attachments": self.attachments,
            "mentions": self.mentions,
            "metadata": self.metadata
        }


@dataclass
class MessageResponse:
    """Response after sending a message."""
    message_id: str
    channel_id: str
    timestamp: datetime
    thread_id: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Notification:
    """Structured notification for workflow events."""
    title: str
    description: str
    level: NotificationLevel
    ticket_id: Optional[str] = None
    pr_url: Optional[str] = None
    workflow_id: Optional[str] = None
    error_details: Optional[str] = None
    action_required: bool = False
    fields: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CommunicationPlugin(Plugin):
    """Base class for communication integrations."""
    
    @abstractmethod
    async def send_message(self, message: Message) -> MessageResponse:
        """Send a message to a channel."""
        pass
    
    @abstractmethod
    async def send_notification(self, channel: str, notification: Notification) -> MessageResponse:
        """Send a structured notification."""
        pass
    
    @abstractmethod
    async def reply_to_thread(self, thread_id: str, text: str, format: MessageFormat = MessageFormat.PLAIN_TEXT) -> MessageResponse:
        """Reply to an existing thread."""
        pass
    
    @abstractmethod
    async def update_message(self, message_id: str, channel: str, text: str) -> None:
        """Update an existing message."""
        pass
    
    @abstractmethod
    async def delete_message(self, message_id: str, channel: str) -> None:
        """Delete a message."""
        pass
    
    @abstractmethod
    async def get_channel(self, channel_id: str) -> Channel:
        """Get channel information."""
        pass
    
    @abstractmethod
    async def list_channels(self, include_archived: bool = False) -> List[Channel]:
        """List all available channels."""
        pass
    
    @abstractmethod
    async def get_user(self, user_id: str) -> User:
        """Get user information."""
        pass
    
    @abstractmethod
    async def find_user_by_email(self, email: str) -> Optional[User]:
        """Find user by email address."""
        pass
    
    @abstractmethod
    async def upload_file(self, channel: str, file_path: str, filename: str, title: Optional[str] = None) -> MessageResponse:
        """Upload a file to a channel."""
        pass
    
    def format_notification(self, notification: Notification) -> Dict[str, Any]:
        """Format notification for the specific platform."""
        # Override in subclasses for platform-specific formatting
        color_map = {
            NotificationLevel.INFO: "#36a64f",
            NotificationLevel.SUCCESS: "#2eb886",
            NotificationLevel.WARNING: "#ffa500",
            NotificationLevel.ERROR: "#ff0000",
            NotificationLevel.CRITICAL: "#8b0000"
        }
        
        return {
            "title": notification.title,
            "text": notification.description,
            "color": color_map.get(notification.level, "#808080"),
            "fields": [
                {"title": k, "value": v, "short": True}
                for k, v in notification.fields.items()
            ]
        }
    
    def create_workflow_notification(
        self,
        event_type: str,
        ticket_id: str,
        status: str,
        details: Optional[str] = None,
        pr_url: Optional[str] = None,
        error: Optional[str] = None
    ) -> Notification:
        """Create a standard workflow notification."""
        level = NotificationLevel.INFO
        title = f"Workflow Update: {event_type}"
        
        if error:
            level = NotificationLevel.ERROR
            title = f"Workflow Failed: {event_type}"
        elif status == "completed":
            level = NotificationLevel.SUCCESS
            title = f"Workflow Completed: {event_type}"
        
        fields = {
            "Ticket": ticket_id,
            "Status": status
        }
        
        if pr_url:
            fields["Pull Request"] = pr_url
        
        return Notification(
            title=title,
            description=details or f"Workflow {event_type} for ticket {ticket_id}",
            level=level,
            ticket_id=ticket_id,
            pr_url=pr_url,
            error_details=error,
            fields=fields
        )