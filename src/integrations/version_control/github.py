"""GitHub integration for version control."""

import asyncio
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import aiohttp
from urllib.parse import urlparse, quote
import base64

from ..base.version_control import (
    VersionControlIntegration,
    Repository,
    Branch,
    PullRequest,
    Commit,
    FileContent,
    PullRequestStatus,
    MergeStrategy,
    WebhookEvent as VCSWebhookEvent,
    WebhookEventType as VCSWebhookEventType
)
from ...utils.exceptions import IntegrationError, AuthenticationError, ValidationError
from ...utils.logging import get_logger

logger = get_logger(__name__)


class GitHubIntegration(VersionControlIntegration):
    """GitHub integration implementation."""
    
    PLUGIN_ID = "github"
    DISPLAY_NAME = "GitHub"
    VERSION = "1.0.0"
    
    def __init__(self, token: str, organization: Optional[str] = None,
                 api_base_url: Optional[str] = None):
        """Initialize GitHub integration.
        
        Args:
            token: GitHub personal access token or app token
            organization: Optional organization name for enterprise setups
            api_base_url: Optional API base URL (for GitHub Enterprise)
        """
        super().__init__()
        self.token = token
        self.organization = organization
        self.api_base_url = api_base_url or "https://api.github.com"
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def initialize(self) -> None:
        """Initialize the integration."""
        await super().initialize()
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AIAgentPlatform/1.0"
            }
        )
        logger.info("GitHub integration initialized")
        
    async def cleanup(self) -> None:
        """Cleanup integration resources."""
        if self._session:
            await self._session.close()
            self._session = None
        await super().cleanup()
        
    async def health_check(self) -> Dict[str, Any]:
        """Check integration health."""
        try:
            url = f"{self.api_base_url}/user"
            async with self._session.get(url) as response:
                if response.status == 200:
                    user_data = await response.json()
                    return {
                        "healthy": True,
                        "message": f"Connected as: {user_data.get('login', 'Unknown')}",
                        "details": {
                            "user": user_data.get("login"),
                            "name": user_data.get("name"),
                            "rate_limit": response.headers.get("X-RateLimit-Remaining")
                        }
                    }
                elif response.status == 401:
                    return {
                        "healthy": False,
                        "message": "Authentication failed",
                        "error": "Invalid token"
                    }
                else:
                    return {
                        "healthy": False,
                        "message": f"Health check failed: HTTP {response.status}",
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
        return "token" in config
        
    async def get_repository(self, repo_name: str) -> Repository:
        """Get repository information."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            url = f"{self.api_base_url}/repos/{owner}/{name}"
            
            async with self._session.get(url) as response:
                if response.status == 404:
                    raise IntegrationError(f"Repository {repo_name} not found")
                elif response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to get repository: {error_text}")
                    
                data = await response.json()
                return self._convert_to_repository(data)
                
        except Exception as e:
            logger.error(f"Error getting repository {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to get repository: {str(e)}")
            
    async def create_repository(self, name: str, description: Optional[str] = None,
                              private: bool = True) -> Repository:
        """Create a new repository."""
        try:
            data = {
                "name": name,
                "description": description or "",
                "private": private,
                "auto_init": True
            }
            
            if self.organization:
                url = f"{self.api_base_url}/orgs/{self.organization}/repos"
            else:
                url = f"{self.api_base_url}/user/repos"
                
            async with self._session.post(url, json=data) as response:
                if response.status != 201:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to create repository: {error_text}")
                    
                repo_data = await response.json()
                return self._convert_to_repository(repo_data)
                
        except Exception as e:
            logger.error(f"Error creating repository {name}: {str(e)}")
            raise IntegrationError(f"Failed to create repository: {str(e)}")
            
    async def get_branches(self, repo_name: str) -> List[Branch]:
        """List all branches in a repository."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            url = f"{self.api_base_url}/repos/{owner}/{name}/branches"
            
            branches = []
            page = 1
            while True:
                async with self._session.get(f"{url}?page={page}&per_page=100") as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise IntegrationError(f"Failed to get branches: {error_text}")
                        
                    data = await response.json()
                    if not data:
                        break
                        
                    for branch_data in data:
                        branches.append(self._convert_to_branch(branch_data))
                        
                    # Check if there are more pages
                    link_header = response.headers.get("Link")
                    if not link_header or 'rel="next"' not in link_header:
                        break
                        
                    page += 1
                    
            return branches
            
        except Exception as e:
            logger.error(f"Error getting branches for {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to get branches: {str(e)}")
            
    async def create_branch(self, repo_name: str, branch_name: str,
                          from_branch: str = "main") -> Branch:
        """Create a new branch."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            
            # Get the SHA of the base branch
            ref_url = f"{self.api_base_url}/repos/{owner}/{name}/git/refs/heads/{from_branch}"
            async with self._session.get(ref_url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to get base branch: {error_text}")
                    
                ref_data = await response.json()
                base_sha = ref_data["object"]["sha"]
                
            # Create the new branch
            create_url = f"{self.api_base_url}/repos/{owner}/{name}/git/refs"
            data = {
                "ref": f"refs/heads/{branch_name}",
                "sha": base_sha
            }
            
            async with self._session.post(create_url, json=data) as response:
                if response.status != 201:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to create branch: {error_text}")
                    
                # Get branch details
                branch_url = f"{self.api_base_url}/repos/{owner}/{name}/branches/{branch_name}"
                async with self._session.get(branch_url) as branch_response:
                    if branch_response.status == 200:
                        branch_data = await branch_response.json()
                        return self._convert_to_branch(branch_data)
                        
                # Fallback if branch details unavailable
                return Branch(
                    name=branch_name,
                    commit_sha=base_sha,
                    protected=False
                )
                
        except Exception as e:
            logger.error(f"Error creating branch {branch_name} in {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to create branch: {str(e)}")
            
    async def delete_branch(self, repo_name: str, branch_name: str) -> bool:
        """Delete a branch."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            url = f"{self.api_base_url}/repos/{owner}/{name}/git/refs/heads/{branch_name}"
            
            async with self._session.delete(url) as response:
                if response.status == 204:
                    return True
                elif response.status == 404:
                    logger.warning(f"Branch {branch_name} not found in {repo_name}")
                    return False
                else:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to delete branch: {error_text}")
                    
        except Exception as e:
            logger.error(f"Error deleting branch {branch_name} from {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to delete branch: {str(e)}")
            
    async def get_pull_requests(self, repo_name: str, state: str = "open") -> List[PullRequest]:
        """List pull requests."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            url = f"{self.api_base_url}/repos/{owner}/{name}/pulls"
            
            prs = []
            page = 1
            while True:
                params = {
                    "state": state,
                    "page": page,
                    "per_page": 100,
                    "sort": "updated",
                    "direction": "desc"
                }
                
                async with self._session.get(url, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise IntegrationError(f"Failed to get pull requests: {error_text}")
                        
                    data = await response.json()
                    if not data:
                        break
                        
                    for pr_data in data:
                        prs.append(self._convert_to_pull_request(pr_data))
                        
                    # Check if there are more pages
                    link_header = response.headers.get("Link")
                    if not link_header or 'rel="next"' not in link_header:
                        break
                        
                    page += 1
                    
            return prs
            
        except Exception as e:
            logger.error(f"Error getting pull requests for {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to get pull requests: {str(e)}")
            
    async def create_pull_request(self, repo_name: str, title: str, description: str,
                                source_branch: str, target_branch: str = "main",
                                reviewers: Optional[List[str]] = None) -> PullRequest:
        """Create a pull request."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            url = f"{self.api_base_url}/repos/{owner}/{name}/pulls"
            
            data = {
                "title": title,
                "body": description,
                "head": source_branch,
                "base": target_branch,
                "draft": False
            }
            
            async with self._session.post(url, json=data) as response:
                if response.status != 201:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to create pull request: {error_text}")
                    
                pr_data = await response.json()
                pr = self._convert_to_pull_request(pr_data)
                
                # Add reviewers if specified
                if reviewers:
                    await self._add_reviewers(owner, name, pr.id, reviewers)
                    
                return pr
                
        except Exception as e:
            logger.error(f"Error creating pull request in {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to create pull request: {str(e)}")
            
    async def update_pull_request(self, repo_name: str, pr_id: str,
                                title: Optional[str] = None,
                                description: Optional[str] = None,
                                state: Optional[str] = None) -> PullRequest:
        """Update a pull request."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            url = f"{self.api_base_url}/repos/{owner}/{name}/pulls/{pr_id}"
            
            data = {}
            if title is not None:
                data["title"] = title
            if description is not None:
                data["body"] = description
            if state is not None:
                data["state"] = state
                
            async with self._session.patch(url, json=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to update pull request: {error_text}")
                    
                pr_data = await response.json()
                return self._convert_to_pull_request(pr_data)
                
        except Exception as e:
            logger.error(f"Error updating pull request {pr_id} in {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to update pull request: {str(e)}")
            
    async def merge_pull_request(self, repo_name: str, pr_id: str,
                               merge_strategy: MergeStrategy = MergeStrategy.SQUASH,
                               commit_message: Optional[str] = None) -> bool:
        """Merge a pull request."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            url = f"{self.api_base_url}/repos/{owner}/{name}/pulls/{pr_id}/merge"
            
            # Map merge strategy
            merge_method_map = {
                MergeStrategy.MERGE: "merge",
                MergeStrategy.SQUASH: "squash",
                MergeStrategy.REBASE: "rebase"
            }
            
            data = {
                "merge_method": merge_method_map.get(merge_strategy, "squash")
            }
            
            if commit_message:
                data["commit_message"] = commit_message
                
            async with self._session.put(url, json=data) as response:
                if response.status == 200:
                    return True
                elif response.status == 405:
                    error_data = await response.json()
                    logger.warning(f"Cannot merge PR: {error_data.get('message', 'Unknown reason')}")
                    return False
                else:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to merge pull request: {error_text}")
                    
        except Exception as e:
            logger.error(f"Error merging pull request {pr_id} in {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to merge pull request: {str(e)}")
            
    async def get_commits(self, repo_name: str, branch: Optional[str] = None,
                         since: Optional[datetime] = None,
                         until: Optional[datetime] = None) -> List[Commit]:
        """Get commits from a repository."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            url = f"{self.api_base_url}/repos/{owner}/{name}/commits"
            
            params = {}
            if branch:
                params["sha"] = branch
            if since:
                params["since"] = since.isoformat()
            if until:
                params["until"] = until.isoformat()
                
            commits = []
            page = 1
            while True:
                params["page"] = page
                params["per_page"] = 100
                
                async with self._session.get(url, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise IntegrationError(f"Failed to get commits: {error_text}")
                        
                    data = await response.json()
                    if not data:
                        break
                        
                    for commit_data in data:
                        commits.append(self._convert_to_commit(commit_data))
                        
                    # Check if there are more pages
                    link_header = response.headers.get("Link")
                    if not link_header or 'rel="next"' not in link_header:
                        break
                        
                    page += 1
                    
            return commits
            
        except Exception as e:
            logger.error(f"Error getting commits from {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to get commits: {str(e)}")
            
    async def commit_files(self, repo_name: str, branch: str, message: str,
                         files: Dict[str, str], author: Optional[Dict[str, str]] = None) -> Commit:
        """Commit multiple files to a repository."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            
            # Get the current commit SHA of the branch
            ref_url = f"{self.api_base_url}/repos/{owner}/{name}/git/refs/heads/{branch}"
            async with self._session.get(ref_url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to get branch reference: {error_text}")
                    
                ref_data = await response.json()
                current_commit_sha = ref_data["object"]["sha"]
                
            # Get the current tree
            commit_url = f"{self.api_base_url}/repos/{owner}/{name}/git/commits/{current_commit_sha}"
            async with self._session.get(commit_url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to get current commit: {error_text}")
                    
                commit_data = await response.json()
                base_tree_sha = commit_data["tree"]["sha"]
                
            # Create blobs for each file
            tree_items = []
            for file_path, content in files.items():
                blob_data = {
                    "content": base64.b64encode(content.encode()).decode(),
                    "encoding": "base64"
                }
                
                blob_url = f"{self.api_base_url}/repos/{owner}/{name}/git/blobs"
                async with self._session.post(blob_url, json=blob_data) as response:
                    if response.status != 201:
                        error_text = await response.text()
                        raise IntegrationError(f"Failed to create blob: {error_text}")
                        
                    blob_response = await response.json()
                    tree_items.append({
                        "path": file_path,
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_response["sha"]
                    })
                    
            # Create tree
            tree_data = {
                "base_tree": base_tree_sha,
                "tree": tree_items
            }
            
            tree_url = f"{self.api_base_url}/repos/{owner}/{name}/git/trees"
            async with self._session.post(tree_url, json=tree_data) as response:
                if response.status != 201:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to create tree: {error_text}")
                    
                tree_response = await response.json()
                new_tree_sha = tree_response["sha"]
                
            # Create commit
            commit_data = {
                "message": message,
                "tree": new_tree_sha,
                "parents": [current_commit_sha]
            }
            
            if author:
                commit_data["author"] = author
                
            commit_url = f"{self.api_base_url}/repos/{owner}/{name}/git/commits"
            async with self._session.post(commit_url, json=commit_data) as response:
                if response.status != 201:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to create commit: {error_text}")
                    
                commit_response = await response.json()
                new_commit_sha = commit_response["sha"]
                
            # Update branch reference
            update_data = {
                "sha": new_commit_sha,
                "force": False
            }
            
            async with self._session.patch(ref_url, json=update_data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to update branch: {error_text}")
                    
            return Commit(
                sha=new_commit_sha,
                message=message,
                author=author.get("name", "Unknown") if author else "Unknown",
                email=author.get("email", "") if author else "",
                date=datetime.utcnow(),
                files=list(files.keys())
            )
            
        except Exception as e:
            logger.error(f"Error committing files to {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to commit files: {str(e)}")
            
    async def get_file_content(self, repo_name: str, file_path: str,
                             branch: Optional[str] = None) -> FileContent:
        """Get file content from repository."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            url = f"{self.api_base_url}/repos/{owner}/{name}/contents/{file_path}"
            
            params = {}
            if branch:
                params["ref"] = branch
                
            async with self._session.get(url, params=params) as response:
                if response.status == 404:
                    raise IntegrationError(f"File {file_path} not found")
                elif response.status != 200:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to get file content: {error_text}")
                    
                data = await response.json()
                
                if data.get("type") != "file":
                    raise IntegrationError(f"{file_path} is not a file")
                    
                content = base64.b64decode(data["content"]).decode()
                
                return FileContent(
                    path=file_path,
                    content=content,
                    sha=data["sha"],
                    size=data["size"]
                )
                
        except Exception as e:
            logger.error(f"Error getting file {file_path} from {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to get file content: {str(e)}")
            
    async def setup_webhook(self, repo_name: str, callback_url: str,
                          events: Optional[List[str]] = None,
                          secret: Optional[str] = None) -> str:
        """Setup webhook for repository events."""
        try:
            owner, name = self._parse_repo_name(repo_name)
            url = f"{self.api_base_url}/repos/{owner}/{name}/hooks"
            
            if events is None:
                events = ["push", "pull_request", "issues"]
                
            data = {
                "name": "web",
                "active": True,
                "events": events,
                "config": {
                    "url": callback_url,
                    "content_type": "json",
                    "insecure_ssl": "0"
                }
            }
            
            if secret:
                data["config"]["secret"] = secret
                
            async with self._session.post(url, json=data) as response:
                if response.status != 201:
                    error_text = await response.text()
                    raise IntegrationError(f"Failed to create webhook: {error_text}")
                    
                webhook_data = await response.json()
                return str(webhook_data["id"])
                
        except Exception as e:
            logger.error(f"Error setting up webhook for {repo_name}: {str(e)}")
            raise IntegrationError(f"Failed to setup webhook: {str(e)}")
            
    async def validate_webhook(self, headers: Dict[str, str], body: bytes,
                             secret: Optional[str] = None) -> bool:
        """Validate webhook signature."""
        if not secret:
            return True
            
        signature = headers.get("X-Hub-Signature-256", "")
        if not signature:
            return False
            
        # GitHub uses HMAC-SHA256
        import hmac
        import hashlib
        
        expected_signature = "sha256=" + hmac.new(
            secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
        
    async def parse_webhook_event(self, headers: Dict[str, str],
                                body: Dict[str, Any]) -> VCSWebhookEvent:
        """Parse webhook event data."""
        try:
            event_type = headers.get("X-GitHub-Event", "")
            
            if event_type == "pull_request":
                action = body.get("action", "")
                if action == "opened":
                    webhook_type = VCSWebhookEventType.PULL_REQUEST_OPENED
                elif action == "closed":
                    if body.get("pull_request", {}).get("merged"):
                        webhook_type = VCSWebhookEventType.PULL_REQUEST_MERGED
                    else:
                        webhook_type = VCSWebhookEventType.PULL_REQUEST_CLOSED
                elif action in ["synchronize", "edited"]:
                    webhook_type = VCSWebhookEventType.PULL_REQUEST_UPDATED
                else:
                    webhook_type = VCSWebhookEventType.OTHER
                    
                pr_data = body.get("pull_request", {})
                pr_id = str(pr_data.get("number", ""))
                repo_name = body.get("repository", {}).get("full_name", "")
                
            elif event_type == "push":
                webhook_type = VCSWebhookEventType.PUSH
                pr_id = None
                repo_name = body.get("repository", {}).get("full_name", "")
                
            else:
                webhook_type = VCSWebhookEventType.OTHER
                pr_id = None
                repo_name = body.get("repository", {}).get("full_name", "")
                
            return VCSWebhookEvent(
                id=headers.get("X-GitHub-Delivery", ""),
                type=webhook_type,
                repository=repo_name,
                pull_request_id=pr_id,
                data=body,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Error parsing webhook event: {str(e)}")
            raise IntegrationError(f"Failed to parse webhook event: {str(e)}")
            
    def _parse_repo_name(self, repo_name: str) -> Tuple[str, str]:
        """Parse repository name into owner and name."""
        if "/" in repo_name:
            parts = repo_name.split("/", 1)
            return parts[0], parts[1]
        elif self.organization:
            return self.organization, repo_name
        else:
            raise ValidationError("Repository name must be in format 'owner/name'")
            
    def _convert_to_repository(self, data: Dict[str, Any]) -> Repository:
        """Convert GitHub repository data to Repository object."""
        return Repository(
            id=str(data["id"]),
            name=data["name"],
            full_name=data["full_name"],
            description=data.get("description", ""),
            url=data["html_url"],
            clone_url=data["clone_url"],
            default_branch=data.get("default_branch", "main"),
            private=data["private"],
            created_at=datetime.fromisoformat(data["created_at"].rstrip("Z")),
            updated_at=datetime.fromisoformat(data["updated_at"].rstrip("Z"))
        )
        
    def _convert_to_branch(self, data: Dict[str, Any]) -> Branch:
        """Convert GitHub branch data to Branch object."""
        return Branch(
            name=data["name"],
            commit_sha=data["commit"]["sha"],
            protected=data.get("protected", False)
        )
        
    def _convert_to_pull_request(self, data: Dict[str, Any]) -> PullRequest:
        """Convert GitHub pull request data to PullRequest object."""
        state_map = {
            "open": PullRequestStatus.OPEN,
            "closed": PullRequestStatus.CLOSED if not data.get("merged") else PullRequestStatus.MERGED
        }
        
        return PullRequest(
            id=str(data["number"]),
            title=data["title"],
            description=data.get("body", ""),
            source_branch=data["head"]["ref"],
            target_branch=data["base"]["ref"],
            status=state_map.get(data["state"], PullRequestStatus.OPEN),
            author=data["user"]["login"],
            created_at=datetime.fromisoformat(data["created_at"].rstrip("Z")),
            updated_at=datetime.fromisoformat(data["updated_at"].rstrip("Z")),
            url=data["html_url"],
            mergeable=data.get("mergeable", False),
            metadata={
                "number": data["number"],
                "state": data["state"],
                "merged": data.get("merged", False),
                "draft": data.get("draft", False),
                "commits": data.get("commits", 0),
                "additions": data.get("additions", 0),
                "deletions": data.get("deletions", 0),
                "changed_files": data.get("changed_files", 0)
            }
        )
        
    def _convert_to_commit(self, data: Dict[str, Any]) -> Commit:
        """Convert GitHub commit data to Commit object."""
        commit_info = data.get("commit", data)
        author_info = commit_info.get("author", {})
        
        return Commit(
            sha=data["sha"],
            message=commit_info["message"],
            author=author_info.get("name", "Unknown"),
            email=author_info.get("email", ""),
            date=datetime.fromisoformat(author_info.get("date", "").rstrip("Z")),
            files=[f["filename"] for f in data.get("files", [])]
        )
        
    async def _add_reviewers(self, owner: str, repo: str, pr_number: str,
                           reviewers: List[str]) -> None:
        """Add reviewers to a pull request."""
        try:
            url = f"{self.api_base_url}/repos/{owner}/{repo}/pulls/{pr_number}/requested_reviewers"
            data = {
                "reviewers": reviewers
            }
            
            async with self._session.post(url, json=data) as response:
                if response.status != 201:
                    error_text = await response.text()
                    logger.warning(f"Failed to add reviewers: {error_text}")
                    
        except Exception as e:
            logger.warning(f"Error adding reviewers: {str(e)}")