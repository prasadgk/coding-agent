"""Core settings and configuration management."""

from functools import lru_cache
from typing import Dict, Any, Optional, List
from pathlib import Path
from pydantic import Field, validator, BaseModel
from pydantic_settings import BaseSettings
from pydantic.types import SecretStr
import os


class RetentionPolicy(BaseModel):
    """Repository retention policy configuration."""
    max_inactive_hours: float = Field(
        default=24.0,
        description="Maximum hours a repository can be inactive"
    )
    max_repository_age_hours: float = Field(
        default=168.0,  # 7 days
        description="Maximum age of a repository in hours"
    )
    max_total_repositories: int = Field(
        default=50,
        description="Maximum total number of repositories to retain"
    )
    cleanup_on_startup: bool = Field(
        default=True,
        description="Run cleanup when the system starts"
    )


class ConcurrentProcessingConfig(BaseModel):
    """Configuration for concurrent repository processing."""
    max_parallel_tickets: int = Field(
        default=15,
        description="Maximum number of tickets to process in parallel"
    )
    repository_lock_timeout: int = Field(
        default=300,
        description="Timeout in seconds for repository locks"
    )


class RepositoryManagementConfig(BaseSettings):
    """Configuration for repository management."""
    
    base_workspace: Path = Field(
        default=Path("/tmp/ai-agent-repos"),
        description="Base directory for repository workspaces"
    )
    max_concurrent_repos: int = Field(
        default=20,
        description="Maximum number of concurrent repository clones"
    )
    cleanup_interval_hours: float = Field(
        default=6.0,
        description="Hours between cleanup cycles"
    )
    max_branches_per_repo: int = Field(
        default=10,
        description="Maximum feature branches per repository"
    )
    disk_space_limit_gb: float = Field(
        default=100.0,
        description="Maximum disk space for all repositories in GB"
    )
    enable_repository_caching: bool = Field(
        default=True,
        description="Enable repository caching for performance"
    )
    lock_timeout_seconds: int = Field(
        default=300,
        description="Default timeout in seconds for repository locks"
    )
    health_check_interval_seconds: int = Field(
        default=300,
        description="Interval between health checks in seconds"
    )
    retention_policy: RetentionPolicy = Field(
        default_factory=RetentionPolicy,
        description="Repository retention policy"
    )
    concurrent_processing: ConcurrentProcessingConfig = Field(
        default_factory=ConcurrentProcessingConfig,
        description="Concurrent processing configuration"
    )


class AWSConfig(BaseSettings):
    """AWS-specific configuration."""
    
    region: str = Field(default="us-east-1", env="AWS_REGION")
    access_key_id: Optional[SecretStr] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    secret_access_key: Optional[SecretStr] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    secrets_manager_prefix: str = Field(
        default="ai-coding-agent",
        description="Prefix for AWS Secrets Manager keys"
    )
    ecs_cluster_name: Optional[str] = Field(default=None, env="ECS_CLUSTER_NAME")
    vpc_id: Optional[str] = Field(default=None, env="VPC_ID")


class MonitoringConfig(BaseSettings):
    """Monitoring and observability configuration."""
    
    enable_metrics: bool = Field(default=True)
    enable_tracing: bool = Field(default=True)
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    structured_logging: bool = Field(default=True)
    correlation_id_header: str = Field(default="X-Correlation-ID")
    metrics_port: int = Field(default=9090)
    health_check_port: int = Field(default=8080)


class WorkflowConfig(BaseSettings):
    """Workflow engine configuration."""
    
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_backoff_seconds: int = Field(default=60, description="Base retry backoff")
    workflow_timeout_minutes: int = Field(default=30, description="Overall workflow timeout")
    concurrent_workflows: int = Field(default=10, description="Max concurrent workflows")
    enable_auto_recovery: bool = Field(default=True)


class ClaudeCodeConfig(BaseModel):
    """Claude Code specific configuration."""
    claude_command: str = Field(default="claude", description="Claude Code CLI command")
    model: str = Field(default="claude-3-opus-20240229", description="Claude model to use")
    max_tokens: int = Field(default=4096, description="Maximum tokens for generation")
    temperature: float = Field(default=0.3, description="Temperature for generation")
    system_prompt: Optional[str] = Field(default=None, description="Custom system prompt")


class AgentConfig(BaseModel):
    """Configuration for the Universal Coding Agent."""
    workspace_path: str = Field(
        default="/tmp/ai-agent-workspace",
        description="Base workspace path for agent operations"
    )
    max_concurrent_workflows: int = Field(
        default=10,
        description="Maximum concurrent workflows"
    )
    repo_cleanup_interval: int = Field(
        default=24,
        description="Repository cleanup interval in hours"
    )
    max_repositories: int = Field(
        default=50,
        description="Maximum number of repositories to maintain"
    )
    claude_code_config: ClaudeCodeConfig = Field(
        default_factory=ClaudeCodeConfig,
        description="Claude Code configuration"
    )
    integrations: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Integration configurations"
    )


class Settings(BaseSettings):
    """Main application settings."""
    
    # Application metadata
    app_name: str = Field(default="universal-ai-coding-agent")
    environment: str = Field(default="development", env="ENVIRONMENT")
    version: str = Field(default="0.1.0")
    
    # Core configurations
    repository_management: RepositoryManagementConfig = Field(default_factory=RepositoryManagementConfig)
    aws: AWSConfig = Field(default_factory=AWSConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    
    # Integration settings
    enabled_integrations: Dict[str, List[str]] = Field(
        default={
            "project_management": ["jira"],
            "version_control": ["bitbucket"],
            "communication": ["slack"],
            "cicd": ["jenkins"]
        }
    )
    
    # API settings
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")
    api_base_path: str = Field(default="/api/v1")
    webhook_base_path: str = Field(default="/webhooks")
    
    # Security settings
    api_key_header: str = Field(default="X-API-Key")
    enable_auth: bool = Field(default=True, env="ENABLE_AUTH")
    allowed_origins: List[str] = Field(default=["*"])
    
    # Claude Code settings
    claude_api_key: Optional[SecretStr] = Field(default=None, env="ANTHROPIC_API_KEY")
    claude_model: str = Field(default="claude-3-opus-20240229")
    claude_max_tokens: int = Field(default=4096)
    claude_temperature: float = Field(default=0.3)
    claude_command: str = Field(default="claude", description="Claude Code CLI command")
    
    # Plugin directories
    plugin_directories: List[Path] = Field(
        default=[Path("src/integrations")]
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"
        
    @validator("repository_management", pre=True)
    def validate_repository_management_config(cls, v):
        if isinstance(v, dict):
            return RepositoryManagementConfig(**v)
        return v
    
    @validator("plugin_directories", pre=True)
    def validate_plugin_dirs(cls, v):
        if isinstance(v, list):
            return [Path(p) if not isinstance(p, Path) else p for p in v]
        return v
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() == "development"
    
    def get_secret(self, key: str) -> Optional[str]:
        """Get secret from environment or AWS Secrets Manager."""
        # First try environment variable
        env_value = os.getenv(key.upper())
        if env_value:
            return env_value
        
        # In production, use AWS Secrets Manager
        if self.is_production and self.aws.secrets_manager_prefix:
            # This would be implemented with boto3
            # For now, return None
            pass
        
        return None
    
    def get_agent_config(self) -> AgentConfig:
        """Get agent configuration from settings."""
        claude_config = ClaudeCodeConfig(
            claude_command=self.claude_command,
            model=self.claude_model,
            max_tokens=self.claude_max_tokens,
            temperature=self.claude_temperature
        )
        
        # Build integrations config from enabled integrations
        integrations_config = {}
        for category, platforms in self.enabled_integrations.items():
            integrations_config[category] = {}
            for platform in platforms:
                integrations_config[category][platform] = {
                    "enabled": True,
                    # Additional platform-specific config would go here
                }
        
        return AgentConfig(
            workspace_path=str(self.repository_management.base_workspace),
            max_concurrent_workflows=self.workflow.concurrent_workflows,
            repo_cleanup_interval=int(self.repository_management.cleanup_interval_hours),
            max_repositories=self.repository_management.max_concurrent_repos,
            claude_code_config=claude_config,
            integrations=integrations_config
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()