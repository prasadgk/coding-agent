"""Custom exception classes for the AI Coding Agent."""

from typing import Optional, Dict, Any


# Alias for backward compatibility
AIAgentException = Exception


class AgentError(Exception):
    """Base exception for all agent errors."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = True
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        self.recoverable = recoverable
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details,
            "recoverable": self.recoverable
        }


class ConfigurationError(AgentError):
    """Raised when there's a configuration problem."""
    
    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        super().__init__(message, recoverable=False, **kwargs)
        if config_key:
            self.details["config_key"] = config_key


class IntegrationError(AgentError):
    """Raised when there's an integration problem."""
    
    def __init__(
        self,
        message: str,
        integration_name: str,
        integration_type: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.details["integration_name"] = integration_name
        if integration_type:
            self.details["integration_type"] = integration_type


class PluginError(IntegrationError):
    """Raised when there's a plugin-specific error."""
    pass


class WorkflowError(AgentError):
    """Raised when there's a workflow execution error."""
    
    def __init__(
        self,
        message: str,
        workflow_id: Optional[str] = None,
        step_name: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        if workflow_id:
            self.details["workflow_id"] = workflow_id
        if step_name:
            self.details["step_name"] = step_name


class RepositoryError(AgentError):
    """Raised when there's a repository operation error."""
    
    def __init__(
        self,
        message: str,
        repository_url: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        if repository_url:
            self.details["repository_url"] = repository_url
        if operation:
            self.details["operation"] = operation


class CodeGenerationError(AgentError):
    """Raised when code generation fails."""
    
    def __init__(
        self,
        message: str,
        ticket_id: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        if ticket_id:
            self.details["ticket_id"] = ticket_id
        if model:
            self.details["model"] = model


class AuthenticationError(AgentError):
    """Raised when authentication fails."""
    
    def __init__(self, message: str, service: Optional[str] = None, **kwargs):
        super().__init__(message, recoverable=False, **kwargs)
        if service:
            self.details["service"] = service


class RateLimitError(AgentError):
    """Raised when rate limit is exceeded."""
    
    def __init__(
        self,
        message: str,
        service: str,
        retry_after: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, recoverable=True, **kwargs)
        self.details["service"] = service
        if retry_after:
            self.details["retry_after"] = retry_after


class ValidationError(AgentError):
    """Raised when validation fails."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        **kwargs
    ):
        super().__init__(message, recoverable=False, **kwargs)
        if field:
            self.details["field"] = field
        if value is not None:
            self.details["value"] = str(value)


class TimeoutError(AgentError):
    """Raised when an operation times out."""
    
    def __init__(
        self,
        message: str,
        operation: str,
        timeout_seconds: int,
        **kwargs
    ):
        super().__init__(message, recoverable=True, **kwargs)
        self.details["operation"] = operation
        self.details["timeout_seconds"] = timeout_seconds


class RepositoryLockError(RepositoryError):
    """Raised when repository lock operations fail."""
    
    def __init__(
        self,
        message: str,
        repository_key: Optional[str] = None,
        ticket_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        if repository_key:
            self.details["repository_key"] = repository_key
        if ticket_id:
            self.details["ticket_id"] = ticket_id


class RepositoryNotFoundError(RepositoryError):
    """Raised when a repository is not found."""
    
    def __init__(
        self,
        message: str,
        repository_key: Optional[str] = None,
        workspace_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(message, recoverable=False, **kwargs)
        if repository_key:
            self.details["repository_key"] = repository_key
        if workspace_id:
            self.details["workspace_id"] = workspace_id