"""Metrics collection and monitoring utilities."""

from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum
import time
from functools import wraps
import asyncio
from prometheus_client import Counter, Histogram, Gauge, Summary


class MetricType(str, Enum):
    """Types of metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class MetricsCollector:
    """Collects and exposes metrics for monitoring."""
    
    def __init__(self, namespace: str = "ai_coding_agent"):
        self.namespace = namespace
        self._metrics: Dict[str, Any] = {}
        self._initialize_default_metrics()
    
    def _initialize_default_metrics(self):
        """Initialize default metrics."""
        # Workflow metrics
        self._metrics["workflow_total"] = Counter(
            f"{self.namespace}_workflow_total",
            "Total number of workflows executed",
            ["status", "integration"]
        )
        
        self._metrics["workflow_duration"] = Histogram(
            f"{self.namespace}_workflow_duration_seconds",
            "Workflow execution duration in seconds",
            ["status", "integration"],
            buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600)
        )
        
        # Step metrics
        self._metrics["step_total"] = Counter(
            f"{self.namespace}_step_total",
            "Total number of workflow steps executed",
            ["step_name", "status"]
        )
        
        self._metrics["step_duration"] = Histogram(
            f"{self.namespace}_step_duration_seconds",
            "Step execution duration in seconds",
            ["step_name", "status"]
        )
        
        # Integration metrics
        self._metrics["integration_requests"] = Counter(
            f"{self.namespace}_integration_requests_total",
            "Total number of integration API requests",
            ["integration", "operation", "status"]
        )
        
        self._metrics["integration_request_duration"] = Histogram(
            f"{self.namespace}_integration_request_duration_seconds",
            "Integration API request duration",
            ["integration", "operation"]
        )
        
        # Repository metrics
        self._metrics["repository_operations"] = Counter(
            f"{self.namespace}_repository_operations_total",
            "Total repository operations",
            ["operation", "status"]
        )
        
        self._metrics["active_repositories"] = Gauge(
            f"{self.namespace}_active_repositories",
            "Number of active repository clones"
        )
        
        self._metrics["repository_disk_usage"] = Gauge(
            f"{self.namespace}_repository_disk_usage_bytes",
            "Total disk usage by repositories"
        )
        
        # Code generation metrics
        self._metrics["code_generation_requests"] = Counter(
            f"{self.namespace}_code_generation_requests_total",
            "Total code generation requests",
            ["model", "status"]
        )
        
        self._metrics["code_generation_tokens"] = Summary(
            f"{self.namespace}_code_generation_tokens",
            "Tokens used in code generation",
            ["model"]
        )
        
        # Error metrics
        self._metrics["errors_total"] = Counter(
            f"{self.namespace}_errors_total",
            "Total number of errors",
            ["error_type", "component", "recoverable"]
        )
        
        # Health check metrics
        self._metrics["health_check_status"] = Gauge(
            f"{self.namespace}_health_check_status",
            "Health check status (1=healthy, 0=unhealthy)",
            ["component"]
        )
    
    def record_workflow(self, integration: str, status: str, duration: float):
        """Record workflow execution metrics."""
        self._metrics["workflow_total"].labels(
            status=status,
            integration=integration
        ).inc()
        
        self._metrics["workflow_duration"].labels(
            status=status,
            integration=integration
        ).observe(duration)
    
    def record_step(self, step_name: str, status: str, duration: float):
        """Record workflow step metrics."""
        self._metrics["step_total"].labels(
            step_name=step_name,
            status=status
        ).inc()
        
        self._metrics["step_duration"].labels(
            step_name=step_name,
            status=status
        ).observe(duration)
    
    def record_integration_request(
        self,
        integration: str,
        operation: str,
        status: str,
        duration: float
    ):
        """Record integration API request metrics."""
        self._metrics["integration_requests"].labels(
            integration=integration,
            operation=operation,
            status=status
        ).inc()
        
        self._metrics["integration_request_duration"].labels(
            integration=integration,
            operation=operation
        ).observe(duration)
    
    def record_repository_operation(self, operation: str, status: str):
        """Record repository operation metrics."""
        self._metrics["repository_operations"].labels(
            operation=operation,
            status=status
        ).inc()
    
    def set_active_repositories(self, count: int):
        """Set the number of active repositories."""
        self._metrics["active_repositories"].set(count)
    
    def set_repository_disk_usage(self, bytes_used: int):
        """Set repository disk usage."""
        self._metrics["repository_disk_usage"].set(bytes_used)
    
    def record_code_generation(
        self,
        model: str,
        status: str,
        tokens_used: Optional[int] = None
    ):
        """Record code generation metrics."""
        self._metrics["code_generation_requests"].labels(
            model=model,
            status=status
        ).inc()
        
        if tokens_used:
            self._metrics["code_generation_tokens"].labels(
                model=model
            ).observe(tokens_used)
    
    def record_error(
        self,
        error_type: str,
        component: str,
        recoverable: bool = True
    ):
        """Record error metrics."""
        self._metrics["errors_total"].labels(
            error_type=error_type,
            component=component,
            recoverable=str(recoverable).lower()
        ).inc()
    
    def set_health_status(self, component: str, healthy: bool):
        """Set health check status."""
        self._metrics["health_check_status"].labels(
            component=component
        ).set(1 if healthy else 0)
    
    def get_metric(self, name: str) -> Optional[Any]:
        """Get a specific metric."""
        return self._metrics.get(name)


def track_time(metric_name: str, labels: Optional[Dict[str, str]] = None):
    """Decorator to track execution time of functions."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                # Record metric
                if hasattr(args[0], "metrics") and args[0].metrics:
                    metric = args[0].metrics.get_metric(metric_name)
                    if metric and labels:
                        metric.labels(**labels).observe(duration)
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                
                # Record metric with error
                if hasattr(args[0], "metrics") and args[0].metrics:
                    metric = args[0].metrics.get_metric(metric_name)
                    if metric and labels:
                        error_labels = {**labels, "status": "error"}
                        metric.labels(**error_labels).observe(duration)
                
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                # Record metric
                if hasattr(args[0], "metrics") and args[0].metrics:
                    metric = args[0].metrics.get_metric(metric_name)
                    if metric and labels:
                        metric.labels(**labels).observe(duration)
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                
                # Record metric with error
                if hasattr(args[0], "metrics") and args[0].metrics:
                    metric = args[0].metrics.get_metric(metric_name)
                    if metric and labels:
                        error_labels = {**labels, "status": "error"}
                        metric.labels(**error_labels).observe(duration)
                
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


class MetricsContext:
    """Context manager for recording metrics."""
    
    def __init__(self, collector: MetricsCollector, metric_type: str, **labels):
        self.collector = collector
        self.metric_type = metric_type
        self.labels = labels
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        # Add status based on exception
        if exc_type:
            self.labels["status"] = "error"
        else:
            self.labels["status"] = "success"
        
        # Record metric based on type
        if self.metric_type == "workflow":
            self.collector.record_workflow(
                integration=self.labels.get("integration", "unknown"),
                status=self.labels["status"],
                duration=duration
            )
        elif self.metric_type == "step":
            self.collector.record_step(
                step_name=self.labels.get("step_name", "unknown"),
                status=self.labels["status"],
                duration=duration
            )
        elif self.metric_type == "integration":
            self.collector.record_integration_request(
                integration=self.labels.get("integration", "unknown"),
                operation=self.labels.get("operation", "unknown"),
                status=self.labels["status"],
                duration=duration
            )