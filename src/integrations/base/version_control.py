"""Base classes for version control integrations."""

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import asyncio
from .plugin import Plugin


class PullRequestStatus(str, Enum):
    """Standard pull request statuses."""
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"
    DRAFT = "draft"


class FileChangeType(str, Enum):
    """Types of file changes."""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


@dataclass
class Repository:
    """Represents a version control repository."""
    id: str
    name: str
    full_name: str  # e.g., owner/repo
    url: str
    clone_url_https: str
    clone_url_ssh: str
    default_branch: str
    description: Optional[str] = None
    is_private: bool = True
    owner: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    size_kb: Optional[int] = None
    language: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Branch:
    """Represents a repository branch."""
    name: str
    ref: str
    commit_sha: str
    is_protected: bool = False
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CommitInfo:
    """Represents a git commit."""
    sha: str
    message: str
    author: str
    author_email: str
    timestamp: datetime
    branch: Optional[str] = None
    files_changed: List[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileChange:
    """Represents a file change in a commit or PR."""
    filename: str
    change_type: FileChangeType
    additions: int = 0
    deletions: int = 0
    patch: Optional[str] = None
    old_filename: Optional[str] = None  # For renames


@dataclass
class PullRequestComment:
    """Represents a comment on a pull request."""
    id: str
    author: str
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    in_reply_to: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None


@dataclass
class PullRequest:
    """Represents a pull request/merge request."""
    id: str
    number: int
    title: str
    description: str
    status: PullRequestStatus
    source_branch: str
    target_branch: str
    author: str
    created_at: datetime
    url: str
    updated_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    reviewers: List[str] = field(default_factory=list)
    approvals: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    commits: List[CommitInfo] = field(default_factory=list)
    files_changed: List[FileChange] = field(default_factory=list)
    comments: List[PullRequestComment] = field(default_factory=list)
    conflicts: bool = False
    mergeable: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert pull request to dictionary."""
        return {
            "id": self.id,
            "number": self.number,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "source_branch": self.source_branch,
            "target_branch": self.target_branch,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "merged_at": self.merged_at.isoformat() if self.merged_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "url": self.url,
            "reviewers": self.reviewers,
            "approvals": self.approvals,
            "labels": self.labels,
            "commits": [{"sha": c.sha, "message": c.message} for c in self.commits],
            "files_changed": len(self.files_changed),
            "metadata": self.metadata
        }


@dataclass
class WebhookEvent:
    """Represents a webhook event from version control system."""
    event_type: str  # push, pull_request, etc.
    repository: str
    timestamp: datetime
    data: Dict[str, Any]
    user: str
    raw_payload: Dict[str, Any]


class VersionControlPlugin(Plugin):
    """Base class for version control integrations."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with configuration."""
        super().__init__(config)
        self.webhook_handlers: Dict[str, List[Callable]] = {}
    
    @abstractmethod
    async def get_repository(self, repo_name: str) -> Repository:
        """Get repository information."""
        pass
    
    @abstractmethod
    async def clone_repository(self, repo_name: str, destination: Path) -> Path:
        """Clone repository to local path."""
        pass
    
    @abstractmethod
    async def create_branch(self, repo_name: str, branch_name: str, base_branch: str = "main") -> Branch:
        """Create a new branch."""
        pass
    
    @abstractmethod
    async def delete_branch(self, repo_name: str, branch_name: str) -> None:
        """Delete a branch."""
        pass
    
    @abstractmethod
    async def commit_changes(
        self, 
        repo_path: Path, 
        message: str, 
        files: List[str],
        author_name: str,
        author_email: str
    ) -> CommitInfo:
        """Commit changes to repository."""
        pass
    
    @abstractmethod
    async def push_changes(self, repo_path: Path, branch: str, force: bool = False) -> None:
        """Push changes to remote repository."""
        pass
    
    @abstractmethod
    async def create_pull_request(
        self,
        repo_name: str,
        title: str,
        description: str,
        source_branch: str,
        target_branch: str = "main",
        reviewers: Optional[List[str]] = None,
        labels: Optional[List[str]] = None
    ) -> PullRequest:
        """Create a pull request."""
        pass
    
    @abstractmethod
    async def get_pull_request(self, repo_name: str, pr_number: int) -> PullRequest:
        """Get pull request details."""
        pass
    
    @abstractmethod
    async def update_pull_request(
        self,
        repo_name: str,
        pr_number: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        labels: Optional[List[str]] = None
    ) -> PullRequest:
        """Update pull request details."""
        pass
    
    @abstractmethod
    async def merge_pull_request(
        self,
        repo_name: str,
        pr_number: int,
        merge_method: str = "merge",
        delete_branch: bool = True
    ) -> None:
        """Merge a pull request."""
        pass
    
    @abstractmethod
    async def add_pr_comment(self, repo_name: str, pr_number: int, comment: str) -> None:
        """Add a comment to a pull request."""
        pass
    
    @abstractmethod
    async def request_pr_review(self, repo_name: str, pr_number: int, reviewers: List[str]) -> None:
        """Request review for a pull request."""
        pass
    
    @abstractmethod
    async def list_branches(self, repo_name: str) -> List[Branch]:
        """List all branches in repository."""
        pass
    
    @abstractmethod
    async def get_file_content(self, repo_name: str, file_path: str, branch: str = "main") -> str:
        """Get file content from repository."""
        pass
    
    @abstractmethod
    async def setup_webhook(self, repo_name: str, webhook_url: str, events: List[str]) -> str:
        """Setup webhook for repository events."""
        pass
    
    @abstractmethod
    async def delete_webhook(self, repo_name: str, webhook_id: str) -> None:
        """Delete a webhook."""
        pass
    
    def get_clone_url(self, repo: Repository, use_ssh: bool = False) -> str:
        """Get appropriate clone URL based on authentication method."""
        return repo.clone_url_ssh if use_ssh else repo.clone_url_https
    
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
    async def parse_webhook_event(
        self,
        headers: Dict[str, str],
        body: Dict[str, Any]
    ) -> WebhookEvent:
        """Parse webhook payload into standard event."""
        pass
    
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