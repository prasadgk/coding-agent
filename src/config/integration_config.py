"""Integration-specific configuration management."""

from enum import Enum
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel, Field, validator
from abc import ABC, abstractmethod


class IntegrationType(str, Enum):
    """Types of integrations supported."""
    PROJECT_MANAGEMENT = "project_management"
    VERSION_CONTROL = "version_control"
    COMMUNICATION = "communication"
    CICD = "cicd"


class BaseIntegrationConfig(BaseModel, ABC):
    """Base configuration for all integrations."""
    
    enabled: bool = Field(default=True, description="Whether this integration is enabled")
    name: str = Field(..., description="Integration name")
    type: IntegrationType = Field(..., description="Integration type")
    webhook_path: Optional[str] = Field(default=None, description="Webhook endpoint path")
    api_timeout: int = Field(default=30, description="API timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    rate_limit: Optional[int] = Field(default=None, description="Rate limit per minute")
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Validate integration-specific configuration."""
        pass


class JiraConfig(BaseIntegrationConfig):
    """JIRA integration configuration."""
    
    type: IntegrationType = IntegrationType.PROJECT_MANAGEMENT
    server_url: str = Field(..., description="JIRA server URL")
    username: str = Field(..., description="JIRA username")
    api_token: str = Field(..., description="JIRA API token")
    project_key: Optional[str] = Field(default=None, description="Default project key")
    issue_types: list[str] = Field(
        default=["Story", "Task", "Bug"],
        description="Issue types to process"
    )
    custom_fields: Dict[str, str] = Field(
        default={},
        description="Custom field mappings"
    )
    
    def validate_config(self) -> bool:
        """Validate JIRA configuration."""
        return bool(self.server_url and self.username and self.api_token)


class AzureDevOpsConfig(BaseIntegrationConfig):
    """Azure DevOps integration configuration."""
    
    type: IntegrationType = IntegrationType.PROJECT_MANAGEMENT
    organization: str = Field(..., description="Azure DevOps organization")
    project: str = Field(..., description="Project name")
    personal_access_token: str = Field(..., description="Personal Access Token")
    work_item_types: list[str] = Field(
        default=["User Story", "Task", "Bug"],
        description="Work item types to process"
    )
    area_path: Optional[str] = Field(default=None, description="Default area path")
    iteration_path: Optional[str] = Field(default=None, description="Default iteration path")
    
    def validate_config(self) -> bool:
        """Validate Azure DevOps configuration."""
        return bool(self.organization and self.project and self.personal_access_token)


class BitbucketConfig(BaseIntegrationConfig):
    """Bitbucket integration configuration."""
    
    type: IntegrationType = IntegrationType.VERSION_CONTROL
    workspace: str = Field(..., description="Bitbucket workspace")
    username: str = Field(..., description="Bitbucket username")
    app_password: str = Field(..., description="Bitbucket app password")
    default_branch: str = Field(default="main", description="Default branch name")
    branch_prefix: str = Field(default="feature/", description="Branch name prefix")
    require_pr_approval: bool = Field(default=True, description="Require PR approval")
    
    def validate_config(self) -> bool:
        """Validate Bitbucket configuration."""
        return bool(self.workspace and self.username and self.app_password)


class GitHubConfig(BaseIntegrationConfig):
    """GitHub integration configuration."""
    
    type: IntegrationType = IntegrationType.VERSION_CONTROL
    organization: str = Field(..., description="GitHub organization")
    access_token: str = Field(..., description="GitHub personal access token")
    default_branch: str = Field(default="main", description="Default branch name")
    branch_prefix: str = Field(default="feature/", description="Branch name prefix")
    enable_auto_merge: bool = Field(default=False, description="Enable auto-merge")
    required_checks: list[str] = Field(default=[], description="Required status checks")
    
    def validate_config(self) -> bool:
        """Validate GitHub configuration."""
        return bool(self.organization and self.access_token)


class SlackConfig(BaseIntegrationConfig):
    """Slack integration configuration."""
    
    type: IntegrationType = IntegrationType.COMMUNICATION
    bot_token: str = Field(..., description="Slack bot token")
    app_token: Optional[str] = Field(default=None, description="Slack app token")
    default_channel: str = Field(..., description="Default notification channel")
    mention_users: bool = Field(default=True, description="Mention users in notifications")
    thread_notifications: bool = Field(default=True, description="Use thread replies")
    
    def validate_config(self) -> bool:
        """Validate Slack configuration."""
        return bool(self.bot_token and self.default_channel)


class IntegrationConfig:
    """Manager for all integration configurations."""
    
    # Registry of configuration classes
    CONFIG_CLASSES: Dict[str, Type[BaseIntegrationConfig]] = {
        "jira": JiraConfig,
        "azure_devops": AzureDevOpsConfig,
        "bitbucket": BitbucketConfig,
        "github": GitHubConfig,
        "slack": SlackConfig,
    }
    
    def __init__(self):
        self.configs: Dict[str, BaseIntegrationConfig] = {}
    
    def register_config(self, name: str, config_class: Type[BaseIntegrationConfig]):
        """Register a new integration configuration class."""
        self.CONFIG_CLASSES[name] = config_class
    
    def load_config(self, name: str, config_data: Dict[str, Any]) -> BaseIntegrationConfig:
        """Load configuration for a specific integration."""
        if name not in self.CONFIG_CLASSES:
            raise ValueError(f"Unknown integration: {name}")
        
        config_class = self.CONFIG_CLASSES[name]
        config = config_class(name=name, **config_data)
        
        if not config.validate_config():
            raise ValueError(f"Invalid configuration for integration: {name}")
        
        self.configs[name] = config
        return config
    
    def get_config(self, name: str) -> Optional[BaseIntegrationConfig]:
        """Get configuration for a specific integration."""
        return self.configs.get(name)
    
    def get_configs_by_type(self, integration_type: IntegrationType) -> Dict[str, BaseIntegrationConfig]:
        """Get all configurations of a specific type."""
        return {
            name: config 
            for name, config in self.configs.items() 
            if config.type == integration_type
        }
    
    def validate_all(self) -> Dict[str, bool]:
        """Validate all loaded configurations."""
        return {
            name: config.validate_config() 
            for name, config in self.configs.items()
        }