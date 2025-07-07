"""Test framework integration for validating generated code."""

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from src.utils.logging import get_logger
from src.utils.exceptions import ValidationError

logger = get_logger(__name__)


class TestFramework(str, Enum):
    """Supported test frameworks."""
    PYTEST = "pytest"
    UNITTEST = "unittest"
    JEST = "jest"
    MOCHA = "mocha"
    JUNIT = "junit"
    GO_TEST = "go_test"
    CARGO_TEST = "cargo_test"
    UNKNOWN = "unknown"


@dataclass
class TestResult:
    """Result of a test execution."""
    framework: TestFramework
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    duration_seconds: float
    output: str
    coverage_percentage: Optional[float] = None
    failed_test_details: List[Dict[str, Any]] = None


class TestFrameworkDetector:
    """Detects and runs appropriate test framework for a project."""
    
    # Test framework detection patterns
    FRAMEWORK_PATTERNS = {
        TestFramework.PYTEST: {
            "files": ["pytest.ini", "pyproject.toml", "setup.cfg"],
            "patterns": ["pytest", "test_*.py", "*_test.py"],
            "commands": ["pytest", "python -m pytest"]
        },
        TestFramework.UNITTEST: {
            "files": ["test_*.py"],
            "patterns": ["unittest", "TestCase"],
            "commands": ["python -m unittest discover"]
        },
        TestFramework.JEST: {
            "files": ["jest.config.js", "jest.config.ts", "package.json"],
            "patterns": ["jest", "describe(", "test(", "it("],
            "commands": ["npm test", "yarn test", "jest"]
        },
        TestFramework.MOCHA: {
            "files": ["mocha.opts", ".mocharc.js", "package.json"],
            "patterns": ["mocha", "describe(", "it("],
            "commands": ["npm test", "yarn test", "mocha"]
        },
        TestFramework.JUNIT: {
            "files": ["pom.xml", "build.gradle"],
            "patterns": ["@Test", "junit"],
            "commands": ["mvn test", "gradle test"]
        },
        TestFramework.GO_TEST: {
            "files": ["go.mod"],
            "patterns": ["_test.go", "testing.T"],
            "commands": ["go test ./...", "go test -v ./..."]
        },
        TestFramework.CARGO_TEST: {
            "files": ["Cargo.toml"],
            "patterns": ["#[test]", "#[cfg(test)]"],
            "commands": ["cargo test"]
        }
    }
    
    def __init__(self):
        """Initialize test framework detector."""
        self.detected_framework: Optional[TestFramework] = None
        self.test_command: Optional[str] = None
        
    async def detect_framework(self, workspace: Path) -> TestFramework:
        """Detect the test framework used in the project.
        
        Args:
            workspace: Path to the project workspace
            
        Returns:
            Detected test framework
        """
        framework_scores = {}
        
        for framework, config in self.FRAMEWORK_PATTERNS.items():
            score = 0
            
            # Check for configuration files
            for file_pattern in config["files"]:
                if file_pattern == "package.json":
                    # Special handling for package.json
                    pkg_file = workspace / "package.json"
                    if pkg_file.exists():
                        try:
                            with open(pkg_file) as f:
                                pkg_data = json.load(f)
                                scripts = pkg_data.get("scripts", {})
                                deps = {
                                    **pkg_data.get("dependencies", {}),
                                    **pkg_data.get("devDependencies", {})
                                }
                                
                                # Check if framework is in dependencies
                                framework_name = framework.value.lower()
                                if framework_name in deps:
                                    score += 100
                                    
                                # Check test script
                                if "test" in scripts:
                                    test_script = scripts["test"]
                                    if framework_name in test_script:
                                        score += 50
                        except:
                            pass
                else:
                    # Check for other config files
                    files = list(workspace.glob(file_pattern))
                    if files:
                        score += 50
                        
            # Check for test file patterns
            for pattern in config["patterns"]:
                if "*" in pattern:
                    files = list(workspace.rglob(pattern))
                    score += len(files) * 10
                else:
                    # Search in files for pattern
                    for ext in [".py", ".js", ".ts", ".java", ".go", ".rs"]:
                        for file in workspace.rglob(f"*{ext}"):
                            try:
                                content = file.read_text()
                                if pattern in content:
                                    score += 5
                            except:
                                pass
                                
            framework_scores[framework] = score
            
        # Get framework with highest score
        if framework_scores:
            best_framework = max(framework_scores, key=framework_scores.get)
            if framework_scores[best_framework] > 0:
                self.detected_framework = best_framework
                return best_framework
                
        return TestFramework.UNKNOWN
        
    async def find_test_command(self, workspace: Path, framework: TestFramework) -> Optional[str]:
        """Find the appropriate test command for the framework.
        
        Args:
            workspace: Project workspace path
            framework: Detected test framework
            
        Returns:
            Test command to run
        """
        if framework == TestFramework.UNKNOWN:
            return None
            
        config = self.FRAMEWORK_PATTERNS.get(framework, {})
        commands = config.get("commands", [])
        
        for cmd in commands:
            # Check if command is available
            base_cmd = cmd.split()[0]
            
            # Special handling for npm/yarn
            if base_cmd in ["npm", "yarn"]:
                check_cmd = f"which {base_cmd}"
            else:
                check_cmd = f"which {base_cmd}"
                
            try:
                process = await asyncio.create_subprocess_shell(
                    check_cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await process.communicate()
                
                if process.returncode == 0:
                    self.test_command = cmd
                    return cmd
            except:
                continue
                
        return None
        
    async def run_tests(
        self,
        workspace: Path,
        test_command: Optional[str] = None,
        timeout: int = 600
    ) -> TestResult:
        """Run tests in the workspace.
        
        Args:
            workspace: Project workspace path
            test_command: Override test command
            timeout: Timeout in seconds
            
        Returns:
            Test execution results
        """
        # Use provided command or detect
        if not test_command:
            if not self.detected_framework:
                await self.detect_framework(workspace)
                
            test_command = await self.find_test_command(
                workspace,
                self.detected_framework
            )
            
        if not test_command:
            logger.warning("No test command found")
            return TestResult(
                framework=TestFramework.UNKNOWN,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                skipped_tests=0,
                duration_seconds=0,
                output="No test command found"
            )
            
        logger.info(f"Running tests with command: {test_command}")
        
        try:
            # Run test command
            start_time = asyncio.get_event_loop().time()
            
            process = await asyncio.create_subprocess_shell(
                test_command,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={
                    **asyncio.os.environ,
                    "CI": "true",  # Run in CI mode
                    "FORCE_COLOR": "0"  # Disable color output
                }
            )
            
            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.terminate()
                await process.wait()
                raise ValidationError(f"Test execution timed out after {timeout} seconds")
                
            duration = asyncio.get_event_loop().time() - start_time
            output = stdout.decode() if stdout else ""
            
            # Parse test results
            result = self._parse_test_output(
                output,
                process.returncode,
                self.detected_framework or TestFramework.UNKNOWN,
                duration
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error running tests: {str(e)}")
            return TestResult(
                framework=self.detected_framework or TestFramework.UNKNOWN,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                skipped_tests=0,
                duration_seconds=0,
                output=f"Test execution failed: {str(e)}"
            )
            
    def _parse_test_output(
        self,
        output: str,
        return_code: int,
        framework: TestFramework,
        duration: float
    ) -> TestResult:
        """Parse test output to extract results.
        
        Args:
            output: Test command output
            return_code: Process return code
            framework: Test framework used
            duration: Execution duration
            
        Returns:
            Parsed test results
        """
        # Framework-specific parsing
        if framework == TestFramework.PYTEST:
            return self._parse_pytest_output(output, return_code, duration)
        elif framework == TestFramework.JEST:
            return self._parse_jest_output(output, return_code, duration)
        elif framework == TestFramework.GO_TEST:
            return self._parse_go_test_output(output, return_code, duration)
        else:
            # Generic parsing
            return self._parse_generic_output(output, return_code, framework, duration)
            
    def _parse_pytest_output(self, output: str, return_code: int, duration: float) -> TestResult:
        """Parse pytest output."""
        import re
        
        total = 0
        passed = 0
        failed = 0
        skipped = 0
        
        # Look for pytest summary line
        # Example: "====== 5 passed, 1 failed, 2 skipped in 0.12s ======"
        summary_match = re.search(
            r'=+\s*(\d+\s+\w+(?:,\s*\d+\s+\w+)*)\s+in\s+[\d.]+s\s*=+',
            output
        )
        
        if summary_match:
            summary = summary_match.group(1)
            
            # Extract counts
            passed_match = re.search(r'(\d+)\s+passed', summary)
            if passed_match:
                passed = int(passed_match.group(1))
                
            failed_match = re.search(r'(\d+)\s+failed', summary)
            if failed_match:
                failed = int(failed_match.group(1))
                
            skipped_match = re.search(r'(\d+)\s+skipped', summary)
            if skipped_match:
                skipped = int(skipped_match.group(1))
                
            total = passed + failed + skipped
            
        # Extract failed test details
        failed_tests = []
        if failed > 0:
            # Look for FAILED lines
            failed_matches = re.findall(r'FAILED\s+(.+?)\s+-\s+(.+)', output)
            for test_name, reason in failed_matches:
                failed_tests.append({
                    "test": test_name,
                    "reason": reason
                })
                
        return TestResult(
            framework=TestFramework.PYTEST,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            skipped_tests=skipped,
            duration_seconds=duration,
            output=output,
            failed_test_details=failed_tests if failed_tests else None
        )
        
    def _parse_jest_output(self, output: str, return_code: int, duration: float) -> TestResult:
        """Parse Jest output."""
        import re
        
        total = 0
        passed = 0
        failed = 0
        skipped = 0
        
        # Look for Jest summary
        # Example: "Tests:       1 failed, 3 passed, 4 total"
        tests_match = re.search(
            r'Tests:\s+(?:(\d+)\s+failed,\s*)?(?:(\d+)\s+passed,\s*)?(\d+)\s+total',
            output
        )
        
        if tests_match:
            if tests_match.group(1):
                failed = int(tests_match.group(1))
            if tests_match.group(2):
                passed = int(tests_match.group(2))
            total = int(tests_match.group(3))
            skipped = total - passed - failed
            
        return TestResult(
            framework=TestFramework.JEST,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            skipped_tests=skipped,
            duration_seconds=duration,
            output=output
        )
        
    def _parse_go_test_output(self, output: str, return_code: int, duration: float) -> TestResult:
        """Parse go test output."""
        import re
        
        total = 0
        passed = 0
        failed = 0
        
        # Count PASS and FAIL lines
        pass_matches = re.findall(r'^PASS$', output, re.MULTILINE)
        fail_matches = re.findall(r'^FAIL$', output, re.MULTILINE)
        
        passed = len(pass_matches)
        failed = len(fail_matches)
        total = passed + failed
        
        return TestResult(
            framework=TestFramework.GO_TEST,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            skipped_tests=0,
            duration_seconds=duration,
            output=output
        )
        
    def _parse_generic_output(
        self,
        output: str,
        return_code: int,
        framework: TestFramework,
        duration: float
    ) -> TestResult:
        """Generic test output parsing."""
        # If return code is 0, assume tests passed
        success = return_code == 0
        
        return TestResult(
            framework=framework,
            total_tests=1 if output else 0,
            passed_tests=1 if success and output else 0,
            failed_tests=0 if success else 1,
            skipped_tests=0,
            duration_seconds=duration,
            output=output
        )


class TestGenerator:
    """Generates tests for code changes using Claude Code."""
    
    def __init__(self, claude_client):
        """Initialize test generator.
        
        Args:
            claude_client: Claude Code client instance
        """
        self.claude_client = claude_client
        
    async def generate_tests(
        self,
        workspace: Path,
        files_changed: List[str],
        framework: TestFramework,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate tests for changed files.
        
        Args:
            workspace: Project workspace
            files_changed: List of changed files
            framework: Test framework to use
            context: Additional context
            
        Returns:
            Test generation results
        """
        prompt = self._prepare_test_generation_prompt(
            files_changed,
            framework,
            context
        )
        
        # Use Claude Code to generate tests
        result = await self.claude_client.implement_feature(
            workspace=workspace,
            requirements=f"Generate comprehensive tests for the following changes",
            acceptance_criteria=[
                f"Use {framework.value} as the test framework",
                "Cover all new/modified functions and classes",
                "Include edge cases and error scenarios",
                "Follow existing test patterns in the codebase"
            ],
            context={
                "files_changed": files_changed,
                "framework": framework.value,
                "custom_prompt": prompt
            }
        )
        
        return result
        
    def _prepare_test_generation_prompt(
        self,
        files_changed: List[str],
        framework: TestFramework,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Prepare prompt for test generation."""
        prompt = f"""Generate comprehensive tests for the recent code changes.

## Changed Files
"""
        for file in files_changed:
            prompt += f"- {file}\n"
            
        prompt += f"""
## Test Framework
Use {framework.value} for writing tests.

## Requirements
1. Test all new and modified functions/classes
2. Include positive and negative test cases
3. Test edge cases and error conditions
4. Follow existing test patterns in the project
5. Ensure tests are isolated and repeatable
6. Add appropriate test fixtures/mocks as needed
7. Include descriptive test names and docstrings

## Test Coverage Goals
- Line coverage: > 90%
- Branch coverage: > 80%
- Include integration tests where appropriate
"""
        
        if context and context.get("existing_tests"):
            prompt += "\n## Existing Test Examples\n"
            prompt += "Follow these patterns from existing tests:\n"
            for example in context["existing_tests"][:3]:
                prompt += f"- {example}\n"
                
        return prompt