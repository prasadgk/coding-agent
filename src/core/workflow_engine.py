"""Workflow engine for orchestrating the coding agent workflow."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional, Callable
import uuid
import structlog

from src.integrations.base import Ticket, TicketStatus


logger = structlog.get_logger(__name__)


class WorkflowState(str, Enum):
    """Workflow execution states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class StepStatus(str, Enum):
    """Individual step execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


@dataclass
class WorkflowStep:
    """Represents a step in the workflow."""
    name: str
    handler: Callable
    required: bool = True
    retry_count: int = 3
    timeout_seconds: int = 300
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    """Result of a workflow step execution."""
    step_name: str
    status: StepStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    retries: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowContext:
    """Context passed between workflow steps."""
    workflow_id: str
    ticket: Ticket
    repository_url: Optional[str] = None
    branch_name: Optional[str] = None
    pull_request_url: Optional[str] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from context."""
        return self.artifacts.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set value in context."""
        self.artifacts[key] = value


@dataclass
class WorkflowExecution:
    """Represents a workflow execution instance."""
    id: str
    ticket_id: str
    state: WorkflowState
    started_at: datetime
    completed_at: Optional[datetime] = None
    steps: List[StepResult] = field(default_factory=list)
    context: Optional[WorkflowContext] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkflowEngine:
    """Orchestrates the coding agent workflow."""
    
    def __init__(self, max_concurrent_workflows: int = 10):
        """Initialize workflow engine."""
        self.max_concurrent = max_concurrent_workflows
        self.workflow_steps: List[WorkflowStep] = []
        self.active_workflows: Dict[str, WorkflowExecution] = {}
        self.completed_workflows: Dict[str, WorkflowExecution] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent_workflows)
        self._shutdown = False
    
    def register_step(self, step: WorkflowStep) -> None:
        """Register a workflow step."""
        # Validate dependencies
        existing_steps = {s.name for s in self.workflow_steps}
        for dep in step.depends_on:
            if dep not in existing_steps:
                raise ValueError(f"Step '{step.name}' depends on unknown step '{dep}'")
        
        self.workflow_steps.append(step)
        logger.info("Registered workflow step", step=step.name)
    
    def _order_steps(self) -> List[WorkflowStep]:
        """Order steps based on dependencies."""
        # Simple topological sort
        ordered = []
        remaining = self.workflow_steps.copy()
        
        while remaining:
            # Find steps with no remaining dependencies
            ready = []
            for step in remaining:
                deps_satisfied = all(
                    dep in [s.name for s in ordered]
                    for dep in step.depends_on
                )
                if deps_satisfied:
                    ready.append(step)
            
            if not ready:
                raise ValueError("Circular dependency detected in workflow steps")
            
            # Add ready steps to ordered list
            ordered.extend(ready)
            for step in ready:
                remaining.remove(step)
        
        return ordered
    
    async def execute_workflow(self, ticket: Ticket) -> WorkflowExecution:
        """Execute the complete workflow for a ticket."""
        workflow_id = str(uuid.uuid4())
        
        logger.info(
            "Starting workflow execution",
            workflow_id=workflow_id,
            ticket_id=ticket.id
        )
        
        # Create workflow execution
        execution = WorkflowExecution(
            id=workflow_id,
            ticket_id=ticket.id,
            state=WorkflowState.PENDING,
            started_at=datetime.utcnow()
        )
        
        # Create workflow context
        context = WorkflowContext(
            workflow_id=workflow_id,
            ticket=ticket,
            repository_url=ticket.repository_url
        )
        execution.context = context
        
        # Acquire semaphore for concurrent execution limit
        async with self._semaphore:
            # Store active workflow
            self.active_workflows[workflow_id] = execution
            
            try:
                # Execute workflow
                execution.state = WorkflowState.RUNNING
                await self._execute_steps(execution, context)
                
                # Mark as completed
                execution.state = WorkflowState.COMPLETED
                execution.completed_at = datetime.utcnow()
                
                logger.info(
                    "Workflow completed successfully",
                    workflow_id=workflow_id,
                    duration=(execution.completed_at - execution.started_at).total_seconds()
                )
                
            except asyncio.CancelledError:
                execution.state = WorkflowState.CANCELLED
                execution.error = "Workflow cancelled"
                raise
                
            except Exception as e:
                execution.state = WorkflowState.FAILED
                execution.error = str(e)
                execution.completed_at = datetime.utcnow()
                
                logger.error(
                    "Workflow failed",
                    workflow_id=workflow_id,
                    error=str(e),
                    exc_info=True
                )
                raise
                
            finally:
                # Move to completed workflows
                self.completed_workflows[workflow_id] = execution
                del self.active_workflows[workflow_id]
        
        return execution
    
    async def _execute_steps(self, execution: WorkflowExecution, context: WorkflowContext) -> None:
        """Execute workflow steps in order."""
        ordered_steps = self._order_steps()
        completed_steps = set()
        
        for step in ordered_steps:
            if self._shutdown:
                raise asyncio.CancelledError("Workflow engine shutting down")
            
            # Check if step should be skipped
            if not self._should_execute_step(step, execution):
                result = StepResult(
                    step_name=step.name,
                    status=StepStatus.SKIPPED,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow()
                )
                execution.steps.append(result)
                continue
            
            # Execute step with retries
            result = await self._execute_step_with_retry(step, context)
            execution.steps.append(result)
            
            # Check if step failed and is required
            if result.status == StepStatus.FAILED and step.required:
                raise Exception(f"Required step '{step.name}' failed: {result.error}")
            
            completed_steps.add(step.name)
    
    async def _execute_step_with_retry(self, step: WorkflowStep, context: WorkflowContext) -> StepResult:
        """Execute a step with retry logic."""
        result = StepResult(
            step_name=step.name,
            status=StepStatus.PENDING,
            started_at=datetime.utcnow()
        )
        
        for attempt in range(step.retry_count):
            try:
                logger.info(
                    "Executing workflow step",
                    step=step.name,
                    attempt=attempt + 1,
                    max_attempts=step.retry_count
                )
                
                result.status = StepStatus.RUNNING
                
                # Execute step with timeout
                step_result = await asyncio.wait_for(
                    step.handler(context),
                    timeout=step.timeout_seconds
                )
                
                result.result = step_result
                result.status = StepStatus.COMPLETED
                result.completed_at = datetime.utcnow()
                
                logger.info(
                    "Step completed successfully",
                    step=step.name,
                    duration=(result.completed_at - result.started_at).total_seconds()
                )
                
                return result
                
            except asyncio.TimeoutError:
                result.error = f"Step timed out after {step.timeout_seconds} seconds"
                result.status = StepStatus.FAILED
                result.retries = attempt + 1
                
                logger.warning(
                    "Step timed out",
                    step=step.name,
                    attempt=attempt + 1
                )
                
            except Exception as e:
                result.error = str(e)
                result.status = StepStatus.FAILED
                result.retries = attempt + 1
                
                logger.warning(
                    "Step failed",
                    step=step.name,
                    attempt=attempt + 1,
                    error=str(e)
                )
            
            # Wait before retry
            if attempt < step.retry_count - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        result.completed_at = datetime.utcnow()
        return result
    
    def _should_execute_step(self, step: WorkflowStep, execution: WorkflowExecution) -> bool:
        """Check if a step should be executed."""
        # Check if all dependencies completed successfully
        completed_steps = {
            s.step_name: s.status 
            for s in execution.steps
        }
        
        for dep in step.depends_on:
            if dep not in completed_steps:
                return False
            if completed_steps[dep] != StepStatus.COMPLETED:
                return False
        
        return True
    
    async def cancel_workflow(self, workflow_id: str) -> None:
        """Cancel a running workflow."""
        if workflow_id in self.active_workflows:
            execution = self.active_workflows[workflow_id]
            execution.state = WorkflowState.CANCELLED
            execution.completed_at = datetime.utcnow()
            
            logger.info("Workflow cancelled", workflow_id=workflow_id)
    
    def get_workflow_status(self, workflow_id: str) -> Optional[WorkflowExecution]:
        """Get status of a workflow."""
        if workflow_id in self.active_workflows:
            return self.active_workflows[workflow_id]
        return self.completed_workflows.get(workflow_id)
    
    def get_active_workflows(self) -> List[WorkflowExecution]:
        """Get all active workflows."""
        return list(self.active_workflows.values())
    
    async def shutdown(self) -> None:
        """Shutdown the workflow engine."""
        logger.info("Shutting down workflow engine")
        self._shutdown = True
        
        # Cancel all active workflows
        for workflow_id in list(self.active_workflows.keys()):
            await self.cancel_workflow(workflow_id)
        
        logger.info("Workflow engine shutdown complete")