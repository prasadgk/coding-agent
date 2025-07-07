"""Base classes for CI/CD integrations."""

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Any, Optional
from .plugin import Plugin


class BuildStatus(str, Enum):
    """Standard build statuses."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class ArtifactType(str, Enum):
    """Types of build artifacts."""
    LOG = "log"
    BINARY = "binary"
    REPORT = "report"
    COVERAGE = "coverage"
    TEST_RESULTS = "test_results"
    OTHER = "other"


@dataclass
class Pipeline:
    """Represents a CI/CD pipeline."""
    id: str
    name: str
    project: str
    branch: str
    status: BuildStatus
    commit_sha: str
    trigger: str  # manual, push, pr, schedule
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration: Optional[timedelta] = None
    url: Optional[str] = None
    stages: List['Stage'] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert pipeline to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "project": self.project,
            "branch": self.branch,
            "status": self.status.value,
            "commit_sha": self.commit_sha,
            "trigger": self.trigger,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration": str(self.duration) if self.duration else None,
            "url": self.url,
            "stages": [s.to_dict() for s in self.stages],
            "metadata": self.metadata
        }


@dataclass
class Stage:
    """Represents a stage in a pipeline."""
    id: str
    name: str
    status: BuildStatus
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    jobs: List['Job'] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stage to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "jobs": [j.to_dict() for j in self.jobs],
            "metadata": self.metadata
        }


@dataclass
class Job:
    """Represents a job in a stage."""
    id: str
    name: str
    status: BuildStatus
    runner: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    log_url: Optional[str] = None
    artifacts: List['Artifact'] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "runner": self.runner,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "log_url": self.log_url,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "metadata": self.metadata
        }


@dataclass
class Artifact:
    """Represents a build artifact."""
    id: str
    name: str
    type: ArtifactType
    size_bytes: int
    download_url: str
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert artifact to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "size_bytes": self.size_bytes,
            "download_url": self.download_url,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata
        }


@dataclass
class TestResult:
    """Represents test execution results."""
    total_tests: int
    passed: int
    failed: int
    skipped: int
    duration_seconds: float
    test_suite: str
    failures: List[Dict[str, Any]] = field(default_factory=list)
    coverage_percentage: Optional[float] = None
    report_url: Optional[str] = None


class CICDPlugin(Plugin):
    """Base class for CI/CD integrations."""
    
    @abstractmethod
    async def trigger_pipeline(
        self,
        project: str,
        pipeline_name: str,
        branch: str,
        variables: Optional[Dict[str, str]] = None
    ) -> Pipeline:
        """Trigger a pipeline execution."""
        pass
    
    @abstractmethod
    async def get_pipeline(self, project: str, pipeline_id: str) -> Pipeline:
        """Get pipeline details."""
        pass
    
    @abstractmethod
    async def cancel_pipeline(self, project: str, pipeline_id: str) -> None:
        """Cancel a running pipeline."""
        pass
    
    @abstractmethod
    async def retry_pipeline(self, project: str, pipeline_id: str) -> Pipeline:
        """Retry a failed pipeline."""
        pass
    
    @abstractmethod
    async def get_pipeline_logs(self, project: str, pipeline_id: str, job_id: Optional[str] = None) -> str:
        """Get logs from a pipeline or specific job."""
        pass
    
    @abstractmethod
    async def list_pipelines(
        self,
        project: str,
        branch: Optional[str] = None,
        status: Optional[BuildStatus] = None,
        limit: int = 20
    ) -> List[Pipeline]:
        """List pipelines for a project."""
        pass
    
    @abstractmethod
    async def get_artifacts(self, project: str, pipeline_id: str) -> List[Artifact]:
        """Get artifacts from a pipeline."""
        pass
    
    @abstractmethod
    async def download_artifact(self, artifact_url: str, destination: str) -> str:
        """Download an artifact."""
        pass
    
    @abstractmethod
    async def get_test_results(self, project: str, pipeline_id: str) -> TestResult:
        """Get test results from a pipeline."""
        pass
    
    @abstractmethod
    async def create_pipeline_config(
        self,
        project: str,
        config_content: str,
        branch: str = "main",
        commit_message: str = "Update pipeline configuration"
    ) -> None:
        """Create or update pipeline configuration file."""
        pass
    
    @abstractmethod
    async def validate_pipeline_config(self, project: str, config_content: str) -> Dict[str, Any]:
        """Validate pipeline configuration."""
        pass
    
    @abstractmethod
    async def setup_webhook(self, project: str, webhook_url: str, events: List[str]) -> str:
        """Setup webhook for CI/CD events."""
        pass
    
    @abstractmethod
    async def delete_webhook(self, project: str, webhook_id: str) -> None:
        """Delete a webhook."""
        pass
    
    def should_block_on_failure(self, pipeline: Pipeline) -> bool:
        """Determine if workflow should be blocked on pipeline failure."""
        # Can be overridden for custom logic
        critical_stages = ["test", "security", "quality"]
        for stage in pipeline.stages:
            if any(critical in stage.name.lower() for critical in critical_stages):
                if stage.status == BuildStatus.FAILED:
                    return True
        return False
    
    def extract_quality_metrics(self, test_result: TestResult) -> Dict[str, Any]:
        """Extract quality metrics from test results."""
        total = test_result.total_tests
        if total == 0:
            success_rate = 100.0
        else:
            success_rate = (test_result.passed / total) * 100
        
        return {
            "test_success_rate": success_rate,
            "total_tests": total,
            "passed_tests": test_result.passed,
            "failed_tests": test_result.failed,
            "skipped_tests": test_result.skipped,
            "test_duration": test_result.duration_seconds,
            "coverage": test_result.coverage_percentage
        }