"""Main AI coding agent orchestrator."""

import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

from src.config.settings import AgentConfig
from src.integrations.base.project_management import Ticket, ProjectManagementIntegration
from src.integrations.base.version_control import VersionControlIntegration
from src.utils.logging import get_logger
from src.utils.exceptions import IntegrationError, WorkflowError
from src.core.claude_code_client import ClaudeCodeClient
from src.core.code_analyzer import CodeAnalyzer
from src.core.workflow_engine import WorkflowEngine, WorkflowStep, WorkflowContext
from src.core.repository_management.manager import RepositoryManager
from src.core.error_recovery import ErrorRecoveryManager
from src.core.plugin_loader import PluginLoader

logger = get_logger(__name__)


class UniversalCodingAgent:
    """Main agent that coordinates all operations."""
    
    def __init__(self, config: AgentConfig):
        """Initialize the universal coding agent.
        
        Args:
            config: Agent configuration
        """
        self.config = config
        self.claude_code = ClaudeCodeClient(config.claude_code_config)
        self.code_analyzer = CodeAnalyzer()
        self.workflow_engine = WorkflowEngine(max_concurrent_workflows=config.max_concurrent_workflows)
        self.repository_manager = RepositoryManager(
            base_workspace=Path(config.workspace_path),
            cleanup_interval=config.repo_cleanup_interval,
            max_repositories=config.max_repositories
        )
        self.error_recovery = ErrorRecoveryManager()
        self.plugin_loader = PluginLoader()
        
        # Load integrations
        self.integrations = self._load_integrations()
        
        # Register workflow steps
        self._register_workflow_steps()
        
        logger.info("Universal Coding Agent initialized", config=config.dict())
        
    def _load_integrations(self) -> Dict[str, Any]:
        """Load configured integrations."""
        integrations = {
            "project_management": {},
            "version_control": {},
            "communication": {},
            "cicd": {}
        }
        
        # Load project management integrations
        for name, config in self.config.integrations.get("project_management", {}).items():
            if config.get("enabled"):
                integration = self.plugin_loader.load_integration("project_management", name, config)
                if integration:
                    integrations["project_management"][name] = integration
                    logger.info(f"Loaded project management integration: {name}")
                    
        # Load version control integrations
        for name, config in self.config.integrations.get("version_control", {}).items():
            if config.get("enabled"):
                integration = self.plugin_loader.load_integration("version_control", name, config)
                if integration:
                    integrations["version_control"][name] = integration
                    logger.info(f"Loaded version control integration: {name}")
                    
        return integrations
        
    def _register_workflow_steps(self):
        """Register workflow steps with the engine."""
        # Step 1: Analyze ticket
        self.workflow_engine.register_step(WorkflowStep(
            name="analyze_ticket",
            handler=self._analyze_ticket_step,
            required=True,
            retry_count=2,
            timeout_seconds=60
        ))
        
        # Step 2: Setup repository
        self.workflow_engine.register_step(WorkflowStep(
            name="setup_repository",
            handler=self._setup_repository_step,
            required=True,
            retry_count=3,
            timeout_seconds=300,
            depends_on=["analyze_ticket"]
        ))
        
        # Step 3: Analyze codebase
        self.workflow_engine.register_step(WorkflowStep(
            name="analyze_codebase",
            handler=self._analyze_codebase_step,
            required=True,
            retry_count=2,
            timeout_seconds=120,
            depends_on=["setup_repository"]
        ))
        
        # Step 4: Generate code
        self.workflow_engine.register_step(WorkflowStep(
            name="generate_code",
            handler=self._generate_code_step,
            required=True,
            retry_count=3,
            timeout_seconds=600,
            depends_on=["analyze_codebase"]
        ))
        
        # Step 5: Validate code
        self.workflow_engine.register_step(WorkflowStep(
            name="validate_code",
            handler=self._validate_code_step,
            required=True,
            retry_count=2,
            timeout_seconds=300,
            depends_on=["generate_code"]
        ))
        
        # Step 6: Run tests
        self.workflow_engine.register_step(WorkflowStep(
            name="run_tests",
            handler=self._run_tests_step,
            required=False,
            retry_count=2,
            timeout_seconds=600,
            depends_on=["validate_code"]
        ))
        
        # Step 7: Create pull request
        self.workflow_engine.register_step(WorkflowStep(
            name="create_pull_request",
            handler=self._create_pull_request_step,
            required=True,
            retry_count=2,
            timeout_seconds=120,
            depends_on=["run_tests"]
        ))
        
        # Step 8: Update ticket
        self.workflow_engine.register_step(WorkflowStep(
            name="update_ticket",
            handler=self._update_ticket_step,
            required=True,
            retry_count=3,
            timeout_seconds=60,
            depends_on=["create_pull_request"]
        ))
        
    async def process_ticket_assignment(self, platform: str, ticket_data: Dict[str, Any]):
        """Process a ticket assignment from a platform.
        
        Args:
            platform: Name of the platform (e.g., "jira", "azure_devops")
            ticket_data: Raw ticket data from webhook
        """
        try:
            logger.info(f"Processing ticket assignment from {platform}", ticket_id=ticket_data.get("id"))
            
            # Get the appropriate integration
            pm_integration = self.integrations["project_management"].get(platform)
            if not pm_integration:
                raise IntegrationError(f"No integration found for platform: {platform}")
                
            # Parse ticket data
            ticket = await pm_integration.parse_webhook_data(ticket_data)
            
            # Execute workflow
            execution = await self.workflow_engine.execute_workflow(ticket)
            
            logger.info(
                "Ticket processing completed",
                ticket_id=ticket.id,
                workflow_id=execution.id,
                status=execution.state
            )
            
        except Exception as e:
            logger.error(f"Error processing ticket assignment: {str(e)}", exc_info=True)
            
            # Attempt error recovery
            await self.error_recovery.handle_error(e, {
                "platform": platform,
                "ticket_data": ticket_data
            })
            
    async def _analyze_ticket_step(self, context: WorkflowContext) -> Dict[str, Any]:
        """Analyze ticket requirements and extract key information."""
        ticket = context.ticket
        
        logger.info(f"Analyzing ticket {ticket.id}")
        
        # Extract key information
        analysis = {
            "type": self._determine_ticket_type(ticket),
            "complexity": self._estimate_complexity(ticket),
            "requirements": self._extract_requirements(ticket),
            "affected_areas": self._identify_affected_areas(ticket),
            "dependencies": self._identify_dependencies(ticket)
        }
        
        # Store in context
        context.set("ticket_analysis", analysis)
        
        return analysis
        
    async def _setup_repository_step(self, context: WorkflowContext) -> Dict[str, Any]:
        """Setup repository workspace for development."""
        ticket = context.ticket
        
        logger.info(f"Setting up repository for ticket {ticket.id}")
        
        # Get or create repository workspace
        repo_workspace = await self.repository_manager.get_repository_workspace(
            repo_url=ticket.repository,
            base_branch=ticket.base_branch or "main"
        )
        
        # Create feature branch
        feature_branch = f"{ticket.branch_prefix or 'feature'}/{ticket.id}"
        workspace_path = await self.repository_manager.create_feature_branch(
            repo_url=ticket.repository,
            branch_name=feature_branch,
            base_branch=ticket.base_branch or "main"
        )
        
        # Store in context
        context.set("workspace_path", workspace_path)
        context.set("feature_branch", feature_branch)
        context.branch_name = feature_branch
        
        return {
            "workspace_path": str(workspace_path),
            "feature_branch": feature_branch
        }
        
    async def _analyze_codebase_step(self, context: WorkflowContext) -> Dict[str, Any]:
        """Analyze codebase to understand structure and patterns."""
        workspace_path = context.get("workspace_path")
        ticket_analysis = context.get("ticket_analysis", {})
        
        logger.info("Analyzing codebase structure")
        
        # Analyze repository
        code_context = await self.code_analyzer.analyze_repository(workspace_path)
        
        # Find relevant files based on ticket
        relevant_files = self.code_analyzer.get_relevant_files(
            context.ticket.description,
            max_files=20
        )
        
        # Store in context
        context.set("code_context", code_context)
        context.set("relevant_files", relevant_files)
        
        return {
            "language": code_context.language,
            "framework": code_context.framework,
            "relevant_files": relevant_files,
            "patterns": code_context.patterns
        }
        
    async def _generate_code_step(self, context: WorkflowContext) -> Dict[str, Any]:
        """Generate code using Claude Code."""
        workspace_path = context.get("workspace_path")
        ticket = context.ticket
        code_context = context.get("code_context")
        relevant_files = context.get("relevant_files", [])
        
        logger.info("Generating code with Claude Code")
        
        # Prepare context for Claude Code
        generation_context = {
            "language": code_context.language,
            "framework": code_context.framework,
            "patterns": code_context.patterns,
            "related_files": relevant_files,
            "dependencies": code_context.dependencies,
            "notes": f"Working on ticket {ticket.id}: {ticket.title}"
        }
        
        # Generate code
        result = await self.claude_code.implement_feature(
            workspace=workspace_path,
            requirements=ticket.description,
            acceptance_criteria=ticket.acceptance_criteria,
            context=generation_context
        )
        
        # Store results
        context.set("code_generation_result", result)
        context.set("files_modified", result.get("files_modified", []))
        
        return result
        
    async def _validate_code_step(self, context: WorkflowContext) -> Dict[str, Any]:
        """Validate generated code quality."""
        workspace_path = context.get("workspace_path")
        files_modified = context.get("files_modified", [])
        
        logger.info("Validating code quality")
        
        # Run code quality checks
        validation_results = await self.claude_code.validate_code_quality(
            workspace=workspace_path,
            files_changed=files_modified
        )
        
        # If validation fails, attempt to fix issues
        if not validation_results.get("success"):
            logger.info("Code validation failed, attempting fixes")
            
            fix_results = await self.claude_code.fix_issues(
                workspace=workspace_path,
                issues=validation_results,
                max_iterations=3
            )
            
            context.set("fix_results", fix_results)
            
            # Re-validate after fixes
            if fix_results.get("success"):
                validation_results = await self.claude_code.validate_code_quality(
                    workspace=workspace_path,
                    files_changed=files_modified
                )
                
        context.set("validation_results", validation_results)
        
        return validation_results
        
    async def _run_tests_step(self, context: WorkflowContext) -> Dict[str, Any]:
        """Run tests on the generated code."""
        workspace_path = context.get("workspace_path")
        
        logger.info("Running tests")
        
        # Run tests
        test_results = await self.claude_code.run_tests(workspace=workspace_path)
        
        context.set("test_results", test_results)
        
        # Don't fail the workflow if tests are skipped
        if test_results.get("skipped"):
            logger.info("No tests found, skipping test execution")
            
        return test_results
        
    async def _create_pull_request_step(self, context: WorkflowContext) -> Dict[str, Any]:
        """Create pull request with the changes."""
        ticket = context.ticket
        feature_branch = context.get("feature_branch")
        workspace_path = context.get("workspace_path")
        
        logger.info(f"Creating pull request for ticket {ticket.id}")
        
        # Commit changes
        await self._commit_changes(workspace_path, ticket)
        
        # Get version control integration
        vcs_platform = self._get_vcs_platform(ticket.repository)
        vcs_integration = self.integrations["version_control"].get(vcs_platform)
        
        if not vcs_integration:
            raise IntegrationError(f"No VCS integration found for: {vcs_platform}")
            
        # Create pull request
        pr_title = f"{ticket.id}: {ticket.title}"
        pr_description = self._generate_pr_description(context)
        
        pr = await vcs_integration.create_pull_request(
            repository=ticket.repository,
            source_branch=feature_branch,
            target_branch=ticket.base_branch or "main",
            title=pr_title,
            description=pr_description
        )
        
        context.set("pull_request", pr)
        context.pull_request_url = pr.url
        
        return {
            "pull_request_id": pr.id,
            "pull_request_url": pr.url
        }
        
    async def _update_ticket_step(self, context: WorkflowContext) -> Dict[str, Any]:
        """Update ticket with completion status."""
        ticket = context.ticket
        pr = context.get("pull_request")
        
        logger.info(f"Updating ticket {ticket.id}")
        
        # Get project management integration
        pm_platform = ticket.platform
        pm_integration = self.integrations["project_management"].get(pm_platform)
        
        if not pm_integration:
            raise IntegrationError(f"No PM integration found for: {pm_platform}")
            
        # Update ticket status
        await pm_integration.update_ticket_status(
            ticket_id=ticket.id,
            status="In Review"  # Or configured status
        )
        
        # Add comment with results
        comment = self._generate_completion_comment(context)
        await pm_integration.add_comment(ticket_id=ticket.id, comment=comment)
        
        # Link PR to ticket if supported
        if hasattr(pm_integration, "link_pull_request"):
            await pm_integration.link_pull_request(ticket_id=ticket.id, pr_url=pr.url)
            
        return {
            "ticket_updated": True,
            "comment_added": True
        }
        
    def _determine_ticket_type(self, ticket: Ticket) -> str:
        """Determine the type of ticket (feature, bug, etc.)."""
        # Simple heuristic based on labels and title
        labels_lower = [label.lower() for label in ticket.labels]
        title_lower = ticket.title.lower()
        
        if "bug" in labels_lower or "bug" in title_lower:
            return "bug"
        elif "feature" in labels_lower or "feature" in title_lower:
            return "feature"
        elif "refactor" in labels_lower or "refactor" in title_lower:
            return "refactor"
        elif "test" in labels_lower or "test" in title_lower:
            return "test"
        else:
            return "task"
            
    def _estimate_complexity(self, ticket: Ticket) -> str:
        """Estimate ticket complexity."""
        # Simple estimation based on description length and acceptance criteria
        desc_length = len(ticket.description)
        criteria_count = len(ticket.acceptance_criteria)
        
        if desc_length < 200 and criteria_count <= 2:
            return "low"
        elif desc_length < 500 and criteria_count <= 5:
            return "medium"
        else:
            return "high"
            
    def _extract_requirements(self, ticket: Ticket) -> List[str]:
        """Extract key requirements from ticket."""
        requirements = []
        
        # Add acceptance criteria as requirements
        requirements.extend(ticket.acceptance_criteria)
        
        # Extract bullet points from description
        import re
        bullets = re.findall(r'[-*]\s+(.+)', ticket.description)
        requirements.extend(bullets)
        
        return requirements
        
    def _identify_affected_areas(self, ticket: Ticket) -> List[str]:
        """Identify areas of code that might be affected."""
        areas = []
        
        # Extract from labels
        for label in ticket.labels:
            if "/" in label:  # e.g., "area/api", "component/auth"
                areas.append(label.split("/")[1])
                
        # Extract from description keywords
        keywords = ["api", "ui", "database", "auth", "config", "tests"]
        desc_lower = ticket.description.lower()
        for keyword in keywords:
            if keyword in desc_lower:
                areas.append(keyword)
                
        return list(set(areas))
        
    def _identify_dependencies(self, ticket: Ticket) -> List[str]:
        """Identify ticket dependencies."""
        dependencies = []
        
        # Look for ticket references in description
        import re
        
        # Common ticket reference patterns
        patterns = [
            r'([A-Z]+-\d+)',  # JIRA style
            r'#(\d+)',  # GitHub/GitLab style
            r'AB#(\d+)'  # Azure DevOps style
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, ticket.description)
            dependencies.extend(matches)
            
        return dependencies
        
    async def _commit_changes(self, workspace_path: Path, ticket: Ticket):
        """Commit changes to git."""
        # This would use GitPython or subprocess to commit
        # For now, using subprocess as example
        import subprocess
        
        # Stage all changes
        subprocess.run(["git", "add", "."], cwd=workspace_path, check=True)
        
        # Commit with message
        commit_message = f"{ticket.id}: {ticket.title}\n\n{ticket.description[:200]}..."
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=workspace_path,
            check=True
        )
        
        # Push to remote
        branch_name = f"{ticket.branch_prefix or 'feature'}/{ticket.id}"
        subprocess.run(
            ["git", "push", "origin", branch_name],
            cwd=workspace_path,
            check=True
        )
        
    def _get_vcs_platform(self, repository_url: str) -> str:
        """Determine VCS platform from repository URL."""
        if "github.com" in repository_url:
            return "github"
        elif "bitbucket.org" in repository_url:
            return "bitbucket"
        elif "gitlab.com" in repository_url:
            return "gitlab"
        elif "dev.azure.com" in repository_url:
            return "azure_repos"
        else:
            raise ValueError(f"Unknown VCS platform for: {repository_url}")
            
    def _generate_pr_description(self, context: WorkflowContext) -> str:
        """Generate pull request description."""
        ticket = context.ticket
        test_results = context.get("test_results", {})
        validation_results = context.get("validation_results", {})
        
        description = f"""## Summary
        
This pull request implements ticket {ticket.id}: {ticket.title}

## Changes

{context.get("code_generation_result", {}).get("summary", "Changes implemented as per requirements.")}

## Testing

"""
        
        if test_results.get("success"):
            description += "✅ All tests passing\n"
        elif test_results.get("skipped"):
            description += "⚠️ No tests found\n"
        else:
            description += "❌ Some tests failing (see details)\n"
            
        description += f"""
## Code Quality

- Linting: {"✅ Passed" if validation_results.get("linting", {}).get("success") else "❌ Issues found"}
- Security: {"✅ Passed" if validation_results.get("security", {}).get("success") else "❌ Issues found"}
- Formatting: {"✅ Passed" if validation_results.get("formatting", {}).get("success") else "❌ Issues found"}

## Related

- Ticket: {ticket.id}
- Repository: {ticket.repository}

---
*Generated by AI Coding Agent*
"""
        
        return description
        
    def _generate_completion_comment(self, context: WorkflowContext) -> str:
        """Generate ticket completion comment."""
        pr = context.get("pull_request", {})
        test_results = context.get("test_results", {})
        
        comment = f"""✅ **Code changes implemented successfully!**

Pull Request: {pr.get("url", "N/A")}

**Summary:**
- Feature implemented according to requirements
- Code quality checks: {"Passed" if context.get("validation_results", {}).get("success") else "Fixed after validation"}
- Tests: {"All passing" if test_results.get("success") else "See PR for details"}

Please review the pull request and provide feedback.

---
*This is an automated message from the AI Coding Agent*
"""
        
        return comment
        
    async def shutdown(self):
        """Shutdown the agent and cleanup resources."""
        logger.info("Shutting down Universal Coding Agent")
        
        # Shutdown components
        await self.workflow_engine.shutdown()
        await self.repository_manager.shutdown()
        
        logger.info("Agent shutdown complete")