# Universal AI Coding Agent Platform - Claude Code CLI Development Prompt

## Project Overview
Build a comprehensive, cloud-native AI coding agent platform that can integrate with multiple project management and version control systems. The platform should be modular, extensible, and production-ready for enterprise deployment on AWS.

## Core Requirements

### Platform Integration Support
Create a plugin-based architecture supporting:
- **Project Management Tools**: JIRA, Azure DevOps, Linear, Monday.com, Asana, Trello
- **Version Control Systems**: Bitbucket, GitHub, GitLab, Azure Repos
- **Communication Tools**: Slack, Microsoft Teams, Discord
- **CI/CD Platforms**: Jenkins, GitHub Actions, Azure Pipelines, GitLab CI

### Functional Requirements
1. **Ticket Assignment Detection**: Monitor when tickets are assigned to the AI agent
2. **Autonomous Code Generation**: Create code changes based on ticket requirements
3. **Git Workflow Management**: Handle branching, commits, and pull/merge requests
4. **Testing & Validation**: Run tests and validate code quality
5. **Status Synchronization**: Update tickets and notify stakeholders
6. **Error Handling & Recovery**: Graceful failure handling with human escalation

## Architecture Design

### Project Structure
```
universal-ai-coding-agent/
├── src/
│   ├── core/                    # Core platform logic
│   │   ├── agent.py            # Main orchestration engine
│   │   ├── task_processor.py   # Task processing logic
│   │   ├── code_generator.py   # Claude Code integration
│   │   ├── workflow_engine.py  # Workflow state machine
│   │   └── repository_manager.py # Repository pooling and management
│   ├── integrations/           # Platform integrations
│   │   ├── base/               # Base classes and interfaces
│   │   ├── project_management/ # PM tool integrations
│   │   ├── version_control/    # VCS integrations
│   │   ├── communication/      # Communication tool integrations
│   │   └── cicd/              # CI/CD integrations
│   ├── cloud/                  # AWS cloud components
│   │   ├── lambda/            # Lambda function handlers
│   │   ├── ecs/               # ECS container definitions
│   │   ├── infrastructure/    # CDK/CloudFormation templates
│   │   └── monitoring/        # CloudWatch and alerting
│   ├── config/                # Configuration management
│   ├── utils/                 # Utility functions
│   └── tests/                 # Comprehensive test suite
├── docker/                    # Container definitions
├── docs/                      # Documentation
├── scripts/                   # Deployment and utility scripts
└── examples/                  # Configuration examples
```

### Core Components to Implement

#### 1. Base Integration Framework
Create abstract base classes for all integrations:

```python
# src/integrations/base/project_management.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class Ticket:
    id: str
    title: str
    description: str
    assignee: str
    status: str
    priority: str
    labels: List[str]
    repository: Optional[str]
    acceptance_criteria: List[str]
    metadata: Dict[str, Any]

class ProjectManagementIntegration(ABC):
    @abstractmethod
    async def get_ticket(self, ticket_id: str) -> Ticket:
        pass
    
    @abstractmethod
    async def update_ticket_status(self, ticket_id: str, status: str) -> None:
        pass
    
    @abstractmethod
    async def add_comment(self, ticket_id: str, comment: str) -> None:
        pass
    
    @abstractmethod
    async def setup_webhook(self, callback_url: str) -> str:
        pass
```

#### 2. Configuration Management System
Implement a flexible configuration system that supports multiple environments and integrations:

```python
# src/config/settings.py
from pydantic import BaseSettings
from typing import Dict, Any

class IntegrationConfig(BaseSettings):
    enabled_integrations: Dict[str, Dict[str, Any]]
    webhook_endpoints: Dict[str, str]
    authentication: Dict[str, Dict[str, str]]
    
    class Config:
        env_file = ".env"
        case_sensitive = False
```

#### 3. Main Agent Orchestrator
#### 5. Main Agent Orchestrator
Build the core agent that coordinates all operations with repository reuse:

```python
# src/core/agent.py
class UniversalCodingAgent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.integrations = self._load_integrations()
        self.claude_code = ClaudeCodeClient()
        self.workflow_engine = WorkflowEngine()
        self.repository_manager = RepositoryManager(
            base_workspace=Path(config.workspace_path),
            cleanup_interval=config.repo_cleanup_interval
        )
    
    async def process_ticket_assignment(self, platform: str, ticket_data: Dict):
        # Main entry point for ticket processing with repository reuse
        pass
    
    async def execute_coding_workflow(self, ticket: Ticket):
        """
        Core coding workflow implementation with optimized repository handling
        """
        try:
            # 1. Get or reuse repository workspace
            repo_workspace = await self.repository_manager.get_repository_workspace(
                repo_url=ticket.repository,
                base_branch="development"
            )
            
            # 2. Create feature branch in existing workspace
            feature_branch = f"feature/{ticket.id}"
            workspace_path = await self.repository_manager.create_feature_branch(
                repo_url=ticket.repository,
                branch_name=feature_branch,
                base_branch="development"
            )
            
            # 3. Generate code using Claude Code
            changes = await self.claude_code.implement_feature(
                workspace=workspace_path,
                requirements=ticket.description,
                acceptance_criteria=ticket.acceptance_criteria
            )
            
            # 4. Run tests and validate
            test_results = await self.run_tests(workspace_path)
            
            # 5. Commit and push changes
            await self._git_operations(workspace_path, ticket, feature_branch)
            
            # 6. Create pull request
            pr = await self._create_pull_request(ticket, feature_branch)
            
            # 7. Clean up feature branch locally
            await self.repository_manager.cleanup_branch(ticket.repository, feature_branch)
            
            # 8. Update ticket status
            await self._update_ticket_status(ticket, pr)
            
        except Exception as e:
            await self._handle_workflow_error(ticket, e)
```
```

## Integration Specifications

### JIRA Integration
```python
# src/integrations/project_management/jira.py
class JIRAIntegration(ProjectManagementIntegration):
    def __init__(self, server_url: str, username: str, api_token: str):
        self.jira = JIRA(server=server_url, basic_auth=(username, api_token))
    
    async def get_ticket(self, ticket_id: str) -> Ticket:
        # Implementation for JIRA ticket retrieval
        pass
    
    # Webhook handling for ticket assignments
    async def handle_webhook(self, payload: Dict) -> None:
        pass
```

### Azure DevOps Integration
```python
# src/integrations/project_management/azure_devops.py
class AzureDevOpsIntegration(ProjectManagementIntegration):
    def __init__(self, organization: str, project: str, personal_access_token: str):
        self.client = AzureDevOpsClient(organization, project, personal_access_token)
    
    async def get_work_item(self, work_item_id: str) -> Ticket:
        # Azure DevOps work item handling
        pass
```

### Bitbucket Integration
```python
# src/integrations/version_control/bitbucket.py
class BitbucketIntegration(VersionControlIntegration):
    def __init__(self, workspace: str, username: str, app_password: str):
        self.client = BitbucketClient(workspace, username, app_password)
    
    async def create_pull_request(self, source_branch: str, target_branch: str, 
                                title: str, description: str) -> PullRequest:
        # Bitbucket PR creation
        pass
```

## Cloud Infrastructure Components

### AWS Lambda Functions
Create serverless functions for webhook handling:

```python
# src/cloud/lambda/webhook_handler.py
import json
from typing import Dict, Any

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle incoming webhooks from various platforms
    Route to appropriate integration handler
    Trigger ECS task for main processing
    """
    pass
```

### ECS Task Definition
```python
# src/cloud/ecs/task_runner.py
class ECSTaskRunner:
    """
    Main container that runs the coding workflow
    Handles long-running operations
    Manages workspace cleanup
    """
    async def run_coding_task(self, ticket_data: Dict) -> None:
        pass
```

### Infrastructure as Code
```python
# src/cloud/infrastructure/stack.py
from aws_cdk import (
    Stack, Duration,
    aws_ecs as ecs,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_secretsmanager as secrets,
    aws_iam as iam
)

class AIAgentStack(Stack):
    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # ECS Cluster for main agent
        # Lambda functions for webhooks
        # API Gateway for webhook endpoints
        # Secrets Manager for credentials
        # CloudWatch for monitoring
```

## Implementation Steps

### Phase 1: Core Framework (Week 1-2)
1. Set up project structure and base classes
2. Implement configuration management system
3. Create plugin loading mechanism
4. Build basic workflow engine
5. Set up comprehensive logging and monitoring

### Phase 3: Repository Management & Optimization (Week 3-4)
1. Implement repository pooling and management system
2. Add repository locking mechanism for concurrent access
3. Create automatic cleanup and maintenance routines
4. Build repository health monitoring and recovery
5. Implement configurable retention policies

### Phase 4: Primary Integrations (Week 5-6)
1. Implement JIRA integration with webhook handling
2. Build Bitbucket integration with Git operations
3. Create Azure DevOps integration
4. Implement GitHub integration as reference
5. Add basic error handling and retry logic

### Phase 5: Claude Code Integration (Week 7-8)
1. Integrate Claude Code SDK for code generation
2. Implement code analysis and understanding with repository context
3. Build testing and validation framework
4. Create code quality checks and linting
5. Add iterative improvement capabilities

### Phase 6: Cloud Deployment (Week 9-10)
1. Create AWS infrastructure components
2. Build Docker containers and ECS definitions with persistent storage
3. Implement Lambda webhook handlers
4. Set up API Gateway and routing
5. Configure monitoring and alerting

### Phase 7: Testing & Documentation (Week 11-12)
1. Comprehensive unit and integration testing
2. End-to-end workflow testing
3. Performance and load testing
4. Security testing and vulnerability scanning
5. Complete documentation and deployment guides

## Specific Implementation Requirements

### Repository Management Strategy
```python
class RepositoryPool:
    """
    Manages a pool of persistent repository clones for optimal resource usage
    Supports concurrent access through locking mechanisms
    """
    def __init__(self, base_path: Path, max_repositories: int = 50):
        self.base_path = base_path
        self.max_repositories = max_repositories
        self.active_repos: Dict[str, RepositoryInfo] = {}
        self.repo_locks: Dict[str, asyncio.Lock] = {}
    
    async def acquire_repository(self, repo_url: str, ticket_id: str) -> RepositoryWorkspace:
        """
        Acquire a repository workspace for a specific ticket
        Reuses existing clones when possible, creates new ones when needed
        """
        repo_key = self._normalize_repo_url(repo_url)
        
        # Ensure we have a lock for this repository
        if repo_key not in self.repo_locks:
            self.repo_locks[repo_key] = asyncio.Lock()
        
        async with self.repo_locks[repo_key]:
            if repo_key in self.active_repos:
                # Reuse existing repository
                repo_info = self.active_repos[repo_key]
                await self._update_repository(repo_info)
                return await self._create_workspace(repo_info, ticket_id)
            else:
                # Clone new repository
                repo_info = await self._clone_repository(repo_url, repo_key)
                self.active_repos[repo_key] = repo_info
                return await self._create_workspace(repo_info, ticket_id)

class ConcurrentWorkflowManager:
    """
    Manages multiple concurrent coding workflows
    Ensures repository access coordination and resource optimization
    """
    def __init__(self, repository_pool: RepositoryPool):
        self.repository_pool = repository_pool
        self.active_workflows: Dict[str, WorkflowState] = {}
    
    async def process_tickets_concurrently(self, tickets: List[Ticket]) -> List[WorkflowResult]:
        """
        Process multiple tickets concurrently while managing repository access
        """
        tasks = []
        for ticket in tickets:
            task = asyncio.create_task(self._process_single_ticket(ticket))
            tasks.append(task)
        
        return await asyncio.gather(*tasks, return_exceptions=True)
```

### Error Handling Strategy
```python
class AgentError(Exception):
    def __init__(self, message: str, error_type: str, recoverable: bool = True):
        self.message = message
        self.error_type = error_type
        self.recoverable = recoverable
        super().__init__(message)

class ErrorHandler:
    async def handle_error(self, error: AgentError, context: Dict) -> None:
        # Log error
        # Attempt recovery if recoverable
        # Escalate to human if necessary
        # Update ticket with error status
```

### Security Implementation
1. **Credential Management**: Use AWS Secrets Manager for all API keys
2. **Network Security**: VPC with private subnets and NAT Gateway
3. **Code Security**: Implement code scanning and vulnerability detection
4. **Audit Logging**: Comprehensive audit trail for all operations

### Monitoring and Observability
```python
# src/core/monitoring.py
class MetricsCollector:
    def __init__(self):
        self.cloudwatch = boto3.client('cloudwatch')
    
    def record_ticket_processed(self, platform: str, success: bool, duration: float):
        # CloudWatch custom metrics
        pass
    
    def record_code_generation_metrics(self, lines_changed: int, files_modified: int):
        pass
```

### Configuration Examples
Provide configuration templates for common setups with repository management:

```yaml
# examples/jira-bitbucket-config.yaml
integrations:
  project_management:
    jira:
      enabled: true
      server_url: "https://yourcompany.atlassian.net"
      webhook_path: "/webhooks/jira"
  
  version_control:
    bitbucket:
      enabled: true
      workspace: "yourworkspace"
      webhook_path: "/webhooks/bitbucket"

repository_management:
  base_workspace: "/tmp/ai-agent-repos"
  max_concurrent_repos: 20
  cleanup_interval_hours: 24
  max_branches_per_repo: 10
  disk_space_limit_gb: 100
  enable_repository_caching: true

# examples/azure-devops-config.yaml
integrations:
  project_management:
    azure_devops:
      enabled: true
      organization: "yourorg"
      project: "yourproject"
      webhook_path: "/webhooks/azuredevops"

repository_management:
  base_workspace: "/opt/ai-agent-workspace"
  repository_retention_policy:
    max_inactive_hours: 48
    max_total_repositories: 50
    cleanup_on_startup: true
  concurrent_processing:
    max_parallel_tickets: 15
    repository_lock_timeout: 300
```

## Testing Strategy

### Unit Tests
Create comprehensive test suites for each component:
```python
# src/tests/test_integrations.py
@pytest.mark.asyncio
async def test_jira_integration():
    # Test JIRA ticket retrieval and updates
    pass

@pytest.mark.asyncio
async def test_code_generation():
    # Test Claude Code integration
    pass
```

### Integration Tests
```python
# src/tests/integration/test_workflows.py
@pytest.mark.asyncio
async def test_end_to_end_workflow():
    # Test complete ticket → code → PR workflow
    pass
```

### Performance Tests
```python
# src/tests/performance/test_load.py
async def test_concurrent_ticket_processing():
    # Test handling multiple tickets simultaneously
    pass
```

## Deployment Instructions

### Local Development Setup
```bash
# Setup commands
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configuration
cp examples/local-config.yaml config/config.yaml
# Edit config with your credentials

# Run locally
python -m src.main
```

### Cloud Deployment
```bash
# Deploy infrastructure
cd src/cloud/infrastructure
cdk bootstrap
cdk deploy

# Build and push containers
docker build -t ai-coding-agent .
aws ecr get-login-password | docker login --username AWS --password-stdin
docker push your-ecr-repo/ai-coding-agent
```

## Success Metrics

Define success criteria:
1. **Functionality**: Successfully process tickets from all supported platforms
2. **Reliability**: 99.9% uptime with proper error handling
3. **Performance**: Process tickets within 5 minutes average
4. **Security**: Pass security audits and vulnerability scans
5. **Maintainability**: Clean, documented, and extensible code

## Future Enhancements

Plan for extensibility:
1. **Additional Integrations**: ServiceNow, Monday.com, Linear
2. **Advanced AI Features**: Code review, optimization suggestions
3. **Analytics Dashboard**: Usage metrics and performance insights
4. **Multi-language Support**: Expand beyond Python to Java, JavaScript, etc.
5. **Enterprise Features**: Role-based access, audit trails, compliance reporting

---

**Implementation Note**: Start with a minimal viable product focusing on one PM tool (JIRA) and one VCS (Bitbucket), then expand the integration framework to support additional platforms. Prioritize reliability and security from the beginning, as this will be handling production code changes autonomously.

**Claude Code CLI Usage**: Use this prompt as your comprehensive guide. Break it down into smaller, focused prompts for each phase, and use Claude Code's iterative capabilities to refine and improve each component as you build the platform.