"""Base classes and interfaces for all integrations."""

from .plugin import Plugin, PluginMetadata, PluginStatus
from .project_management import ProjectManagementPlugin, Ticket, TicketStatus, TicketPriority
from .version_control import VersionControlPlugin, Repository, PullRequest, CommitInfo
from .communication import CommunicationPlugin, Message, NotificationLevel
from .cicd import CICDPlugin, BuildStatus, Pipeline

__all__ = [
    # Plugin base
    "Plugin",
    "PluginMetadata",
    "PluginStatus",
    
    # Project management
    "ProjectManagementPlugin",
    "Ticket",
    "TicketStatus",
    "TicketPriority",
    
    # Version control
    "VersionControlPlugin",
    "Repository",
    "PullRequest",
    "CommitInfo",
    
    # Communication
    "CommunicationPlugin",
    "Message",
    "NotificationLevel",
    
    # CI/CD
    "CICDPlugin",
    "BuildStatus",
    "Pipeline",
]