"""Bitbucket integration for version control."""

import asyncio
import aiohttp
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin, quote

from ..base.version_control import (
    VersionControlPlugin,
    Repository,
    Branch,
    CommitInfo,
    FileChange,
    FileChangeType,
    PullRequest,
    PullRequestComment,
    PullRequestStatus,
    WebhookEvent
)
from ...utils.exceptions import IntegrationError, AuthenticationError


logger = logging.getLogger(__name__)


class BitbucketIntegration(VersionControlPlugin):
    """Bitbucket integration implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Bitbucket integration.
        
        Args:
            config: Configuration with keys:
                - workspace: Bitbucket workspace (team/user)
                - username: Bitbucket username
                - app_password: App password for authentication
                - default_reviewers: List of default PR reviewers
                - webhook_secret: Optional webhook secret
        """
        super().__init__(config)
        self.workspace = config["workspace"]
        self.username = config["username"]
        self.app_password = config["app_password"]
        self.default_reviewers = config.get("default_reviewers", [])
        self.webhook_secret = config.get("webhook_secret")
        
        # Bitbucket API base URL
        self.api_url = "https://api.bitbucket.org/2.0"
        
        # Create session with authentication
        self.session: Optional[aiohttp.ClientSession] = None
        self._auth_header = self._create_auth_header()
        
        # Cache for repository info
        self._repo_cache: Dict[str, Repository] = {}
    
    def _create_auth_header(self) -> str:
        """Create Basic auth header."""
        credentials = f"{self.username}:{self.app_password}"
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
        """Authenticate with Bitbucket."""
        try:
            # Test authentication by getting current user
            url = f"{self.api_url}/user"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Authenticated as {data.get('display_name', 'Unknown')}")
                    return True
                elif response.status == 401:
                    raise AuthenticationError("Invalid Bitbucket credentials")
                else:
                    raise IntegrationError(
                        f"Bitbucket authentication failed with status {response.status}",
                        integration_name="bitbucket"
                    )
        except aiohttp.ClientError as e:
            raise IntegrationError(
                f"Failed to connect to Bitbucket: {e}",
                integration_name="bitbucket"
            )
    
    async def get_repository(self, repo_name: str) -> Repository:
        """Get repository information."""
        # Check cache
        cache_key = f"{self.workspace}/{repo_name}"
        if cache_key in self._repo_cache:
            return self._repo_cache[cache_key]
        
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}"
        
        async with self.session.get(url) as response:
            if response.status == 404:
                raise IntegrationError(
                    f"Repository {repo_name} not found",
                    integration_name="bitbucket"
                )
            elif response.status != 200:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to get repository: {text}",
                    integration_name="bitbucket"
                )
            
            data = await response.json()
            
            repo = Repository(
                id=data["uuid"],
                name=data["name"],
                full_name=data["full_name"],
                url=data["links"]["html"]["href"],
                clone_url_https=next(
                    link["href"] for link in data["links"]["clone"]
                    if link["name"] == "https"
                ),
                clone_url_ssh=next(
                    link["href"] for link in data["links"]["clone"]
                    if link["name"] == "ssh"
                ),
                default_branch=data.get("mainbranch", {}).get("name", "main"),
                description=data.get("description"),
                is_private=data.get("is_private", True),
                owner=data["owner"]["display_name"],
                created_at=datetime.fromisoformat(
                    data["created_on"].replace("Z", "+00:00")
                ) if data.get("created_on") else None,
                updated_at=datetime.fromisoformat(
                    data["updated_on"].replace("Z", "+00:00")
                ) if data.get("updated_on") else None,
                size_kb=data.get("size", 0) // 1024,
                language=data.get("language"),
                metadata={"bitbucket": data}
            )
            
            self._repo_cache[cache_key] = repo
            return repo
    
    async def clone_repository(self, repo_name: str, destination: Path) -> Path:
        """Clone repository to local path."""
        repo = await self.get_repository(repo_name)
        
        # Use git command to clone
        import subprocess
        
        # Add credentials to URL for HTTPS clone
        clone_url = repo.clone_url_https
        if "https://" in clone_url:
            clone_url = clone_url.replace(
                "https://",
                f"https://{self.username}:{self.app_password}@"
            )
        
        try:
            subprocess.run(
                ["git", "clone", clone_url, str(destination)],
                check=True,
                capture_output=True,
                text=True
            )
            return destination
        except subprocess.CalledProcessError as e:
            raise IntegrationError(
                f"Failed to clone repository: {e.stderr}",
                integration_name="bitbucket"
            )
    
    async def create_branch(
        self,
        repo_name: str,
        branch_name: str,
        base_branch: str = "main"
    ) -> Branch:
        """Create a new branch."""
        # Get base branch info first
        base_ref = await self._get_branch_ref(repo_name, base_branch)
        
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/refs/branches"
        data = {
            "name": branch_name,
            "target": {
                "hash": base_ref
            }
        }
        
        async with self.session.post(url, json=data) as response:
            if response.status != 201:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to create branch: {text}",
                    integration_name="bitbucket"
                )
            
            branch_data = await response.json()
            
            return Branch(
                name=branch_data["name"],
                ref=f"refs/heads/{branch_data['name']}",
                commit_sha=branch_data["target"]["hash"],
                created_at=datetime.utcnow(),
                metadata={"bitbucket": branch_data}
            )
    
    async def _get_branch_ref(self, repo_name: str, branch_name: str) -> str:
        """Get the commit SHA for a branch."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/refs/branches/{branch_name}"
        
        async with self.session.get(url) as response:
            if response.status != 200:
                raise IntegrationError(
                    f"Branch {branch_name} not found",
                    integration_name="bitbucket"
                )
            
            data = await response.json()
            return data["target"]["hash"]
    
    async def delete_branch(self, repo_name: str, branch_name: str) -> None:
        """Delete a branch."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/refs/branches/{branch_name}"
        
        async with self.session.delete(url) as response:
            if response.status not in [204, 404]:
                text = await response.text()
                logger.warning(f"Failed to delete branch: {text}")
    
    async def commit_changes(
        self,
        repo_path: Path,
        message: str,
        files: List[str],
        author_name: str,
        author_email: str
    ) -> CommitInfo:
        """Commit changes to repository."""
        import subprocess
        
        try:
            # Configure git user
            subprocess.run(
                ["git", "config", "user.name", author_name],
                cwd=str(repo_path),
                check=True
            )
            subprocess.run(
                ["git", "config", "user.email", author_email],
                cwd=str(repo_path),
                check=True
            )
            
            # Add files
            for file in files:
                subprocess.run(
                    ["git", "add", file],
                    cwd=str(repo_path),
                    check=True
                )
            
            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                text=True
            )
            
            # Get commit info
            commit_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                text=True
            ).stdout.strip()
            
            # Get current branch
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                text=True
            ).stdout.strip()
            
            return CommitInfo(
                sha=commit_sha,
                message=message,
                author=author_name,
                author_email=author_email,
                timestamp=datetime.utcnow(),
                branch=branch,
                files_changed=files
            )
            
        except subprocess.CalledProcessError as e:
            raise IntegrationError(
                f"Failed to commit changes: {e.stderr}",
                integration_name="bitbucket"
            )
    
    async def push_changes(
        self,
        repo_path: Path,
        branch: str,
        force: bool = False
    ) -> None:
        """Push changes to remote repository."""
        import subprocess
        
        cmd = ["git", "push", "origin", branch]
        if force:
            cmd.append("--force")
        
        try:
            subprocess.run(
                cmd,
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            raise IntegrationError(
                f"Failed to push changes: {e.stderr}",
                integration_name="bitbucket"
            )
    
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
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/pullrequests"
        
        # Build reviewers list
        reviewer_list = []
        for reviewer in (reviewers or self.default_reviewers):
            reviewer_list.append({"uuid": reviewer})
        
        data = {
            "title": title,
            "description": description,
            "source": {
                "branch": {
                    "name": source_branch
                }
            },
            "destination": {
                "branch": {
                    "name": target_branch
                }
            },
            "reviewers": reviewer_list,
            "close_source_branch": True
        }
        
        async with self.session.post(url, json=data) as response:
            if response.status != 201:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to create pull request: {text}",
                    integration_name="bitbucket"
                )
            
            pr_data = await response.json()
            return await self._parse_pull_request(pr_data)
    
    async def _parse_pull_request(self, data: Dict[str, Any]) -> PullRequest:
        """Parse Bitbucket PR data into PullRequest object."""
        # Map Bitbucket states to standard states
        state_map = {
            "OPEN": PullRequestStatus.OPEN,
            "MERGED": PullRequestStatus.MERGED,
            "DECLINED": PullRequestStatus.CLOSED,
            "SUPERSEDED": PullRequestStatus.CLOSED
        }
        
        # Parse timestamps
        created_at = datetime.fromisoformat(
            data["created_on"].replace("Z", "+00:00")
        )
        updated_at = datetime.fromisoformat(
            data["updated_on"].replace("Z", "+00:00")
        ) if data.get("updated_on") else None
        merged_at = None
        closed_at = None
        
        if data["state"] == "MERGED" and data.get("merge_commit"):
            merged_at = updated_at
        elif data["state"] in ["DECLINED", "SUPERSEDED"]:
            closed_at = updated_at
        
        # Get reviewers and approvals
        reviewers = [r["display_name"] for r in data.get("reviewers", [])]
        participants = data.get("participants", [])
        approvals = [
            p["user"]["display_name"] for p in participants
            if p.get("approved", False)
        ]
        
        return PullRequest(
            id=str(data["id"]),
            number=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            status=state_map.get(data["state"], PullRequestStatus.OPEN),
            source_branch=data["source"]["branch"]["name"],
            target_branch=data["destination"]["branch"]["name"],
            author=data["author"]["display_name"],
            created_at=created_at,
            updated_at=updated_at,
            merged_at=merged_at,
            closed_at=closed_at,
            url=data["links"]["html"]["href"],
            reviewers=reviewers,
            approvals=approvals,
            labels=[],  # Bitbucket doesn't have PR labels
            metadata={"bitbucket": data}
        )
    
    async def get_pull_request(self, repo_name: str, pr_number: int) -> PullRequest:
        """Get pull request details."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/pullrequests/{pr_number}"
        
        async with self.session.get(url) as response:
            if response.status == 404:
                raise IntegrationError(
                    f"Pull request #{pr_number} not found",
                    integration_name="bitbucket"
                )
            elif response.status != 200:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to get pull request: {text}",
                    integration_name="bitbucket"
                )
            
            data = await response.json()
            pr = await self._parse_pull_request(data)
            
            # Get additional details
            pr.commits = await self._get_pr_commits(repo_name, pr_number)
            pr.files_changed = await self._get_pr_files(repo_name, pr_number)
            pr.comments = await self._get_pr_comments(repo_name, pr_number)
            
            return pr
    
    async def _get_pr_commits(
        self,
        repo_name: str,
        pr_number: int
    ) -> List[CommitInfo]:
        """Get commits in a pull request."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/pullrequests/{pr_number}/commits"
        commits = []
        
        async with self.session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                for commit in data.get("values", []):
                    commits.append(CommitInfo(
                        sha=commit["hash"],
                        message=commit["message"],
                        author=commit["author"]["user"]["display_name"]
                        if commit.get("author", {}).get("user")
                        else commit.get("author", {}).get("raw", "Unknown"),
                        author_email="",
                        timestamp=datetime.fromisoformat(
                            commit["date"].replace("Z", "+00:00")
                        )
                    ))
        
        return commits
    
    async def _get_pr_files(
        self,
        repo_name: str,
        pr_number: int
    ) -> List[FileChange]:
        """Get files changed in a pull request."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/pullrequests/{pr_number}/diffstat"
        files = []
        
        async with self.session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                for diff in data.get("values", []):
                    change_type = FileChangeType.MODIFIED
                    if diff["status"] == "added":
                        change_type = FileChangeType.ADDED
                    elif diff["status"] == "removed":
                        change_type = FileChangeType.DELETED
                    elif diff["status"] == "renamed":
                        change_type = FileChangeType.RENAMED
                    
                    files.append(FileChange(
                        filename=diff["new"]["path"] if diff.get("new") else diff["old"]["path"],
                        change_type=change_type,
                        additions=diff.get("lines_added", 0),
                        deletions=diff.get("lines_removed", 0),
                        old_filename=diff["old"]["path"] if diff.get("old") and change_type == FileChangeType.RENAMED else None
                    ))
        
        return files
    
    async def _get_pr_comments(
        self,
        repo_name: str,
        pr_number: int
    ) -> List[PullRequestComment]:
        """Get comments on a pull request."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/pullrequests/{pr_number}/comments"
        comments = []
        
        async with self.session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                for comment in data.get("values", []):
                    comments.append(PullRequestComment(
                        id=str(comment["id"]),
                        author=comment["user"]["display_name"],
                        content=comment["content"]["raw"],
                        created_at=datetime.fromisoformat(
                            comment["created_on"].replace("Z", "+00:00")
                        ),
                        updated_at=datetime.fromisoformat(
                            comment["updated_on"].replace("Z", "+00:00")
                        ) if comment.get("updated_on") else None,
                        in_reply_to=str(comment["parent"]["id"]) if comment.get("parent") else None,
                        file_path=comment.get("inline", {}).get("path"),
                        line_number=comment.get("inline", {}).get("to")
                    ))
        
        return comments
    
    async def update_pull_request(
        self,
        repo_name: str,
        pr_number: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        labels: Optional[List[str]] = None
    ) -> PullRequest:
        """Update pull request details."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/pullrequests/{pr_number}"
        
        data = {}
        if title:
            data["title"] = title
        if description is not None:
            data["description"] = description
        
        async with self.session.put(url, json=data) as response:
            if response.status != 200:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to update pull request: {text}",
                    integration_name="bitbucket"
                )
            
            pr_data = await response.json()
            return await self._parse_pull_request(pr_data)
    
    async def merge_pull_request(
        self,
        repo_name: str,
        pr_number: int,
        merge_method: str = "merge",
        delete_branch: bool = True
    ) -> None:
        """Merge a pull request."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/pullrequests/{pr_number}/merge"
        
        # Bitbucket merge strategies
        strategy_map = {
            "merge": "merge_commit",
            "squash": "squash",
            "rebase": "fast_forward"
        }
        
        data = {
            "type": "pullrequest_merge",
            "merge_strategy": strategy_map.get(merge_method, "merge_commit"),
            "close_source_branch": delete_branch
        }
        
        async with self.session.post(url, json=data) as response:
            if response.status not in [200, 201]:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to merge pull request: {text}",
                    integration_name="bitbucket"
                )
    
    async def add_pr_comment(
        self,
        repo_name: str,
        pr_number: int,
        comment: str
    ) -> None:
        """Add a comment to a pull request."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/pullrequests/{pr_number}/comments"
        
        data = {
            "content": {
                "raw": comment
            }
        }
        
        async with self.session.post(url, json=data) as response:
            if response.status != 201:
                text = await response.text()
                logger.warning(f"Failed to add comment: {text}")
    
    async def request_pr_review(
        self,
        repo_name: str,
        pr_number: int,
        reviewers: List[str]
    ) -> None:
        """Request review for a pull request."""
        # Get current PR data
        pr = await self.get_pull_request(repo_name, pr_number)
        
        # Add new reviewers
        current_reviewers = {r for r in pr.reviewers}
        new_reviewers = current_reviewers.union(set(reviewers))
        
        # Update PR with new reviewers
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/pullrequests/{pr_number}"
        
        reviewer_list = [{"uuid": r} for r in new_reviewers]
        
        data = {
            "reviewers": reviewer_list
        }
        
        async with self.session.put(url, json=data) as response:
            if response.status != 200:
                text = await response.text()
                logger.warning(f"Failed to add reviewers: {text}")
    
    async def list_branches(self, repo_name: str) -> List[Branch]:
        """List all branches in repository."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/refs/branches"
        branches = []
        
        # Paginate through all branches
        while url:
            async with self.session.get(url) as response:
                if response.status != 200:
                    text = await response.text()
                    raise IntegrationError(
                        f"Failed to list branches: {text}",
                        integration_name="bitbucket"
                    )
                
                data = await response.json()
                
                for branch_data in data.get("values", []):
                    branches.append(Branch(
                        name=branch_data["name"],
                        ref=f"refs/heads/{branch_data['name']}",
                        commit_sha=branch_data["target"]["hash"],
                        metadata={"bitbucket": branch_data}
                    ))
                
                # Get next page URL
                url = data.get("next")
        
        return branches
    
    async def get_file_content(
        self,
        repo_name: str,
        file_path: str,
        branch: str = "main"
    ) -> str:
        """Get file content from repository."""
        # URL encode the file path
        encoded_path = quote(file_path)
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/src/{branch}/{encoded_path}"
        
        async with self.session.get(url) as response:
            if response.status == 404:
                raise IntegrationError(
                    f"File {file_path} not found in branch {branch}",
                    integration_name="bitbucket"
                )
            elif response.status != 200:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to get file content: {text}",
                    integration_name="bitbucket"
                )
            
            return await response.text()
    
    async def validate_webhook(
        self,
        headers: Dict[str, str],
        body: bytes,
        secret: Optional[str] = None
    ) -> bool:
        """Validate Bitbucket webhook signature."""
        if not secret and not self.webhook_secret:
            # No secret configured, accept all
            return True
        
        secret = secret or self.webhook_secret
        
        # Bitbucket uses X-Hub-Signature header with HMAC-SHA256
        signature = headers.get("X-Hub-Signature")
        
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
    
    async def parse_webhook_event(
        self,
        headers: Dict[str, str],
        body: Dict[str, Any]
    ) -> WebhookEvent:
        """Parse Bitbucket webhook payload."""
        # Determine event type from headers
        event_key = headers.get("X-Event-Key", "")
        
        # Map Bitbucket events to standard events
        event_map = {
            "repo:push": "push",
            "pullrequest:created": "pull_request_opened",
            "pullrequest:updated": "pull_request_updated",
            "pullrequest:approved": "pull_request_approved",
            "pullrequest:unapproved": "pull_request_unapproved",
            "pullrequest:fulfilled": "pull_request_merged",
            "pullrequest:rejected": "pull_request_closed",
            "pullrequest:comment_created": "pull_request_comment"
        }
        
        event_type = event_map.get(event_key, event_key)
        
        # Extract repository name
        repo_name = ""
        if "repository" in body:
            repo_name = body["repository"]["full_name"]
        elif "pullrequest" in body:
            repo_name = body["pullrequest"]["destination"]["repository"]["full_name"]
        
        # Extract user
        user = ""
        if "actor" in body:
            user = body["actor"]["display_name"]
        
        return WebhookEvent(
            event_type=event_type,
            repository=repo_name,
            timestamp=datetime.utcnow(),
            data=body,
            user=user,
            raw_payload=body
        )
    
    async def setup_webhook(
        self,
        repo_name: str,
        webhook_url: str,
        events: List[str]
    ) -> str:
        """Setup webhook for repository events."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/hooks"
        
        # Map our events to Bitbucket events
        bitbucket_events = []
        event_mapping = {
            "push": "repo:push",
            "pull_request": [
                "pullrequest:created",
                "pullrequest:updated",
                "pullrequest:approved",
                "pullrequest:unapproved",
                "pullrequest:fulfilled",
                "pullrequest:rejected"
            ],
            "pull_request_comment": "pullrequest:comment_created",
            "*": [
                "repo:push",
                "pullrequest:created",
                "pullrequest:updated",
                "pullrequest:fulfilled"
            ]
        }
        
        for event in events:
            mapped = event_mapping.get(event, [])
            if isinstance(mapped, str):
                bitbucket_events.append(mapped)
            else:
                bitbucket_events.extend(mapped)
        
        data = {
            "description": f"AI Agent Webhook - {datetime.utcnow().isoformat()}",
            "url": webhook_url,
            "active": True,
            "events": list(set(bitbucket_events))  # Remove duplicates
        }
        
        if self.webhook_secret:
            data["secret"] = self.webhook_secret
        
        async with self.session.post(url, json=data) as response:
            if response.status != 201:
                text = await response.text()
                raise IntegrationError(
                    f"Failed to create webhook: {text}",
                    integration_name="bitbucket"
                )
            
            webhook_data = await response.json()
            return webhook_data["uuid"]
    
    async def delete_webhook(self, repo_name: str, webhook_id: str) -> None:
        """Delete a webhook."""
        url = f"{self.api_url}/repositories/{self.workspace}/{repo_name}/hooks/{webhook_id}"
        
        async with self.session.delete(url) as response:
            if response.status != 204:
                text = await response.text()
                logger.warning(f"Failed to delete webhook: {text}")