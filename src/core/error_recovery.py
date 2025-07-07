"""Error recovery implementation for the AI coding agent platform."""

import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from enum import Enum
import json

from ..utils.exceptions import (
    IntegrationError,
    AuthenticationError,
    ValidationError,
    WorkflowError,
    RepositoryError
)
from ..utils.logging import get_logger
from ..utils.retry import RetryManager, RetryConfig, error_recovery
from ..integrations.base.project_management import Ticket, TicketStatus

logger = get_logger(__name__)


class RecoveryAction(Enum):
    """Possible recovery actions."""
    RETRY = "retry"
    SKIP = "skip"
    ESCALATE = "escalate"
    ROLLBACK = "rollback"
    MANUAL_INTERVENTION = "manual_intervention"
    ALTERNATIVE_APPROACH = "alternative_approach"


class WorkflowRecoveryStrategy:
    """Recovery strategy for workflow failures."""
    
    def __init__(self):
        """Initialize workflow recovery strategy."""
        self.recovery_actions: Dict[str, RecoveryAction] = {
            "repository_clone_failed": RecoveryAction.RETRY,
            "branch_creation_failed": RecoveryAction.RETRY,
            "code_generation_failed": RecoveryAction.ALTERNATIVE_APPROACH,
            "test_execution_failed": RecoveryAction.ESCALATE,
            "pull_request_failed": RecoveryAction.RETRY,
            "authentication_failed": RecoveryAction.MANUAL_INTERVENTION,
            "validation_failed": RecoveryAction.SKIP,
            "timeout_exceeded": RecoveryAction.ESCALATE
        }
        
        self.max_recovery_attempts = 3
        self.recovery_attempts: Dict[str, int] = {}
        
    async def handle_workflow_error(
        self,
        error: Exception,
        workflow_state: Dict[str, Any],
        ticket: Ticket
    ) -> Dict[str, Any]:
        """Handle workflow error with appropriate recovery strategy.
        
        Args:
            error: The exception that occurred
            workflow_state: Current workflow state
            ticket: The ticket being processed
            
        Returns:
            Recovery result with action and metadata
        """
        error_key = self._get_error_key(error, workflow_state)
        recovery_action = self._determine_recovery_action(error, error_key)
        
        # Track recovery attempts
        self.recovery_attempts[error_key] = self.recovery_attempts.get(error_key, 0) + 1
        
        logger.info(
            f"Handling workflow error: {type(error).__name__} with action: {recovery_action.value}"
        )
        
        recovery_result = {
            "action": recovery_action,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "recovery_attempt": self.recovery_attempts[error_key],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Execute recovery action
        if recovery_action == RecoveryAction.RETRY:
            recovery_result.update(await self._retry_action(error, workflow_state, ticket))
        elif recovery_action == RecoveryAction.SKIP:
            recovery_result.update(await self._skip_action(error, workflow_state, ticket))
        elif recovery_action == RecoveryAction.ESCALATE:
            recovery_result.update(await self._escalate_action(error, workflow_state, ticket))
        elif recovery_action == RecoveryAction.ROLLBACK:
            recovery_result.update(await self._rollback_action(error, workflow_state, ticket))
        elif recovery_action == RecoveryAction.MANUAL_INTERVENTION:
            recovery_result.update(await self._manual_intervention_action(error, workflow_state, ticket))
        elif recovery_action == RecoveryAction.ALTERNATIVE_APPROACH:
            recovery_result.update(await self._alternative_approach_action(error, workflow_state, ticket))
            
        return recovery_result
        
    def _get_error_key(self, error: Exception, workflow_state: Dict[str, Any]) -> str:
        """Generate unique key for error tracking."""
        current_step = workflow_state.get("current_step", "unknown")
        return f"{current_step}_{type(error).__name__}"
        
    def _determine_recovery_action(self, error: Exception, error_key: str) -> RecoveryAction:
        """Determine appropriate recovery action based on error type."""
        # Check if max attempts exceeded
        if self.recovery_attempts.get(error_key, 0) >= self.max_recovery_attempts:
            return RecoveryAction.ESCALATE
            
        # Authentication errors require manual intervention
        if isinstance(error, AuthenticationError):
            return RecoveryAction.MANUAL_INTERVENTION
            
        # Validation errors can be skipped
        if isinstance(error, ValidationError):
            return RecoveryAction.SKIP
            
        # Repository errors should be retried
        if isinstance(error, RepositoryError):
            return RecoveryAction.RETRY
            
        # Default to configured action or escalate
        for key, action in self.recovery_actions.items():
            if key in error_key.lower():
                return action
                
        return RecoveryAction.ESCALATE
        
    async def _retry_action(
        self,
        error: Exception,
        workflow_state: Dict[str, Any],
        ticket: Ticket
    ) -> Dict[str, Any]:
        """Handle retry recovery action."""
        retry_config = RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            max_delay=30.0,
            retryable_exceptions=(IntegrationError, RepositoryError)
        )
        
        return {
            "retry_config": {
                "max_attempts": retry_config.max_attempts,
                "base_delay": retry_config.base_delay,
                "current_attempt": self.recovery_attempts.get(
                    self._get_error_key(error, workflow_state), 1
                )
            },
            "message": "Retrying operation with exponential backoff"
        }
        
    async def _skip_action(
        self,
        error: Exception,
        workflow_state: Dict[str, Any],
        ticket: Ticket
    ) -> Dict[str, Any]:
        """Handle skip recovery action."""
        skipped_step = workflow_state.get("current_step", "unknown")
        
        # Add comment to ticket
        comment = (
            f"Skipped step '{skipped_step}' due to error: {str(error)}. "
            f"Continuing with workflow."
        )
        
        return {
            "skipped_step": skipped_step,
            "message": comment,
            "continue_workflow": True
        }
        
    async def _escalate_action(
        self,
        error: Exception,
        workflow_state: Dict[str, Any],
        ticket: Ticket
    ) -> Dict[str, Any]:
        """Handle escalation recovery action."""
        escalation_message = (
            f"Workflow failed at step '{workflow_state.get('current_step', 'unknown')}' "
            f"after {self.recovery_attempts.get(self._get_error_key(error, workflow_state), 0)} attempts.\n\n"
            f"Error: {type(error).__name__}: {str(error)}\n\n"
            f"Manual intervention required."
        )
        
        return {
            "escalated": True,
            "escalation_message": escalation_message,
            "assigned_to": workflow_state.get("escalation_user", "team_lead"),
            "new_status": TicketStatus.TODO,
            "workflow_suspended": True
        }
        
    async def _rollback_action(
        self,
        error: Exception,
        workflow_state: Dict[str, Any],
        ticket: Ticket
    ) -> Dict[str, Any]:
        """Handle rollback recovery action."""
        rollback_steps = []
        
        # Determine what needs to be rolled back
        if workflow_state.get("branch_created"):
            rollback_steps.append("delete_branch")
        if workflow_state.get("files_modified"):
            rollback_steps.append("revert_changes")
        if workflow_state.get("pr_created"):
            rollback_steps.append("close_pr")
            
        return {
            "rollback_required": True,
            "rollback_steps": rollback_steps,
            "message": f"Rolling back changes due to error: {str(error)}"
        }
        
    async def _manual_intervention_action(
        self,
        error: Exception,
        workflow_state: Dict[str, Any],
        ticket: Ticket
    ) -> Dict[str, Any]:
        """Handle manual intervention recovery action."""
        intervention_message = (
            f"Manual intervention required for ticket {ticket.id}.\n\n"
            f"Error: {type(error).__name__}: {str(error)}\n\n"
            f"Current step: {workflow_state.get('current_step', 'unknown')}\n\n"
            f"Please resolve the issue and restart the workflow."
        )
        
        return {
            "manual_intervention_required": True,
            "intervention_message": intervention_message,
            "workflow_paused": True,
            "notification_sent": True
        }
        
    async def _alternative_approach_action(
        self,
        error: Exception,
        workflow_state: Dict[str, Any],
        ticket: Ticket
    ) -> Dict[str, Any]:
        """Handle alternative approach recovery action."""
        current_step = workflow_state.get("current_step", "unknown")
        
        # Define alternative approaches for different steps
        alternatives = {
            "code_generation": "simplified_implementation",
            "test_execution": "basic_validation_only",
            "complex_refactoring": "incremental_changes"
        }
        
        alternative_approach = alternatives.get(current_step, "fallback_implementation")
        
        return {
            "use_alternative": True,
            "alternative_approach": alternative_approach,
            "message": f"Switching to alternative approach: {alternative_approach}"
        }


class ErrorMetricsCollector:
    """Collects and tracks error metrics for monitoring."""
    
    def __init__(self):
        """Initialize error metrics collector."""
        self.error_counts: Dict[str, int] = {}
        self.error_timestamps: Dict[str, List[datetime]] = {}
        self.recovery_success: Dict[str, int] = {}
        self.recovery_failure: Dict[str, int] = {}
        
    def record_error(self, error: Exception, context: Dict[str, Any]):
        """Record error occurrence."""
        error_type = type(error).__name__
        
        # Increment error count
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        # Track timestamp
        if error_type not in self.error_timestamps:
            self.error_timestamps[error_type] = []
        self.error_timestamps[error_type].append(datetime.utcnow())
        
        # Clean up old timestamps (keep last 24 hours)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        self.error_timestamps[error_type] = [
            ts for ts in self.error_timestamps[error_type] if ts > cutoff
        ]
        
    def record_recovery_result(self, error_type: str, success: bool):
        """Record recovery attempt result."""
        if success:
            self.recovery_success[error_type] = self.recovery_success.get(error_type, 0) + 1
        else:
            self.recovery_failure[error_type] = self.recovery_failure.get(error_type, 0) + 1
            
    def get_error_rate(self, error_type: str, hours: int = 1) -> float:
        """Get error rate for specific error type."""
        if error_type not in self.error_timestamps:
            return 0.0
            
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        recent_errors = [
            ts for ts in self.error_timestamps[error_type] if ts > cutoff
        ]
        
        return len(recent_errors) / hours
        
    def get_recovery_success_rate(self, error_type: str) -> float:
        """Get recovery success rate for error type."""
        success = self.recovery_success.get(error_type, 0)
        failure = self.recovery_failure.get(error_type, 0)
        
        total = success + failure
        if total == 0:
            return 0.0
            
        return success / total
        
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of error metrics."""
        return {
            "error_counts": self.error_counts,
            "error_rates": {
                error_type: self.get_error_rate(error_type)
                for error_type in self.error_counts
            },
            "recovery_success_rates": {
                error_type: self.get_recovery_success_rate(error_type)
                for error_type in set(
                    list(self.recovery_success.keys()) + 
                    list(self.recovery_failure.keys())
                )
            },
            "total_errors_24h": sum(
                len(timestamps) for timestamps in self.error_timestamps.values()
            )
        }


class WorkflowErrorHandler:
    """Main error handler for workflow execution."""
    
    def __init__(self):
        """Initialize workflow error handler."""
        self.recovery_strategy = WorkflowRecoveryStrategy()
        self.metrics_collector = ErrorMetricsCollector()
        self.notification_handlers: List[Callable] = []
        
    def register_notification_handler(self, handler: Callable):
        """Register a notification handler for errors."""
        self.notification_handlers.append(handler)
        
    async def handle_error(
        self,
        error: Exception,
        workflow_state: Dict[str, Any],
        ticket: Ticket
    ) -> Dict[str, Any]:
        """Handle workflow error with recovery and notifications.
        
        Args:
            error: The exception that occurred
            workflow_state: Current workflow state
            ticket: The ticket being processed
            
        Returns:
            Error handling result
        """
        # Record error metrics
        self.metrics_collector.record_error(error, {
            "workflow_state": workflow_state,
            "ticket_id": ticket.id
        })
        
        # Log error details
        logger.error(
            f"Workflow error for ticket {ticket.id}: {type(error).__name__}: {str(error)}",
            exc_info=True,
            extra={
                "ticket_id": ticket.id,
                "workflow_step": workflow_state.get("current_step"),
                "error_type": type(error).__name__
            }
        )
        
        # Attempt recovery
        recovery_result = await self.recovery_strategy.handle_workflow_error(
            error, workflow_state, ticket
        )
        
        # Record recovery result
        self.metrics_collector.record_recovery_result(
            type(error).__name__,
            recovery_result.get("action") != RecoveryAction.ESCALATE
        )
        
        # Send notifications if needed
        if recovery_result.get("action") in [
            RecoveryAction.ESCALATE,
            RecoveryAction.MANUAL_INTERVENTION
        ]:
            await self._send_notifications(error, workflow_state, ticket, recovery_result)
            
        # Add error details to ticket
        await self._update_ticket_with_error(ticket, error, recovery_result)
        
        return recovery_result
        
    async def _send_notifications(
        self,
        error: Exception,
        workflow_state: Dict[str, Any],
        ticket: Ticket,
        recovery_result: Dict[str, Any]
    ):
        """Send error notifications."""
        notification_data = {
            "error": str(error),
            "error_type": type(error).__name__,
            "ticket_id": ticket.id,
            "ticket_title": ticket.title,
            "workflow_step": workflow_state.get("current_step"),
            "recovery_action": recovery_result.get("action"),
            "message": recovery_result.get("escalation_message") or recovery_result.get("intervention_message"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        for handler in self.notification_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(notification_data)
                else:
                    handler(notification_data)
            except Exception as e:
                logger.error(f"Error sending notification: {str(e)}")
                
    async def _update_ticket_with_error(
        self,
        ticket: Ticket,
        error: Exception,
        recovery_result: Dict[str, Any]
    ):
        """Update ticket with error information."""
        error_comment = f"""
### Workflow Error Encountered

**Error Type:** {type(error).__name__}
**Error Message:** {str(error)}
**Recovery Action:** {recovery_result.get('action', RecoveryAction.ESCALATE).value}
**Recovery Attempt:** {recovery_result.get('recovery_attempt', 1)}

{recovery_result.get('message', '')}

**Timestamp:** {datetime.utcnow().isoformat()}
"""
        
        # This would be implemented by the actual integration
        # await ticket_integration.add_comment(ticket.id, error_comment)
        
    def get_error_metrics(self) -> Dict[str, Any]:
        """Get current error metrics."""
        return self.metrics_collector.get_metrics_summary()


# Global error handler instance
workflow_error_handler = WorkflowErrorHandler()


# Register default recovery strategies
error_recovery.register_recovery_strategy(
    RepositoryError,
    lambda error, context: {
        "action": "cleanup_and_retry",
        "cleanup_required": True
    }
)

error_recovery.register_recovery_strategy(
    AuthenticationError,
    lambda error, context: {
        "action": "refresh_credentials",
        "manual_intervention": True
    }
)

error_recovery.register_recovery_strategy(
    ValidationError,
    lambda error, context: {
        "action": "skip_validation",
        "warning": str(error)
    }
)