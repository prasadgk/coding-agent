"""Claude Code integration for autonomous code generation."""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import tempfile
import shutil

from src.utils.exceptions import IntegrationError, ValidationError
from src.utils.logging import get_logger
from src.utils.retry import with_retry, RetryConfig
from src.integrations.base.project_management import Ticket

logger = get_logger(__name__)


class ClaudeCodeClient:
    """Client for interacting with Claude Code CLI for code generation."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize Claude Code client.
        
        Args:
            config: Configuration for Claude Code
        """
        self.config = config or {}
        self.claude_command = self.config.get("claude_command", "claude")
        self.model = self.config.get("model", "claude-3-opus-20240229")
        self.max_tokens = self.config.get("max_tokens", 4096)
        self.temperature = self.config.get("temperature", 0.3)
        self.system_prompt = self.config.get("system_prompt", self._get_default_system_prompt())
        
    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for code generation."""
        return """You are an expert software engineer working on implementing features based on ticket requirements.
Your task is to analyze the codebase, understand the requirements, and implement high-quality code that:
1. Follows existing code patterns and conventions
2. Includes appropriate error handling
3. Is well-documented with clear comments
4. Passes all existing tests
5. Follows security best practices

When implementing features:
- First understand the existing code structure
- Identify the appropriate locations for new code
- Reuse existing utilities and patterns
- Write clean, maintainable code
- Add appropriate logging
- Handle edge cases
"""
    
    @with_retry(max_attempts=3, base_delay=2.0)
    async def implement_feature(
        self,
        workspace: Path,
        requirements: str,
        acceptance_criteria: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Implement a feature using Claude Code.
        
        Args:
            workspace: Path to the repository workspace
            requirements: Feature requirements from ticket
            acceptance_criteria: List of acceptance criteria
            context: Additional context for code generation
            
        Returns:
            Dictionary with implementation details
        """
        try:
            # Prepare the prompt
            prompt = self._prepare_implementation_prompt(
                requirements, acceptance_criteria, context
            )
            
            # Create a temporary file for the prompt
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(prompt)
                prompt_file = f.name
                
            try:
                # Run Claude Code in the workspace
                result = await self._run_claude_code(
                    workspace,
                    prompt_file,
                    "implement"
                )
                
                # Parse the results
                implementation_details = self._parse_implementation_results(result)
                
                return implementation_details
                
            finally:
                # Clean up temp file
                if os.path.exists(prompt_file):
                    os.unlink(prompt_file)
                    
        except Exception as e:
            logger.error(f"Error implementing feature: {str(e)}")
            raise IntegrationError(f"Failed to implement feature: {str(e)}")
            
    async def analyze_codebase(
        self,
        workspace: Path,
        focus_areas: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Analyze codebase to understand structure and patterns.
        
        Args:
            workspace: Path to the repository workspace
            focus_areas: Specific areas to focus on
            
        Returns:
            Analysis results
        """
        try:
            prompt = self._prepare_analysis_prompt(focus_areas)
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(prompt)
                prompt_file = f.name
                
            try:
                result = await self._run_claude_code(
                    workspace,
                    prompt_file,
                    "analyze"
                )
                
                return self._parse_analysis_results(result)
                
            finally:
                if os.path.exists(prompt_file):
                    os.unlink(prompt_file)
                    
        except Exception as e:
            logger.error(f"Error analyzing codebase: {str(e)}")
            raise IntegrationError(f"Failed to analyze codebase: {str(e)}")
            
    async def run_tests(
        self,
        workspace: Path,
        test_command: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run tests in the workspace.
        
        Args:
            workspace: Path to the repository workspace
            test_command: Custom test command (auto-detected if not provided)
            
        Returns:
            Test results
        """
        try:
            if not test_command:
                test_command = await self._detect_test_command(workspace)
                
            if not test_command:
                logger.warning("No test command detected")
                return {
                    "success": True,
                    "skipped": True,
                    "message": "No test command found"
                }
                
            # Run tests
            logger.info(f"Running tests with command: {test_command}")
            
            process = await asyncio.create_subprocess_shell(
                test_command,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            return {
                "success": process.returncode == 0,
                "exit_code": process.returncode,
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else "",
                "command": test_command
            }
            
        except Exception as e:
            logger.error(f"Error running tests: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "command": test_command
            }
            
    async def validate_code_quality(
        self,
        workspace: Path,
        files_changed: List[str]
    ) -> Dict[str, Any]:
        """Validate code quality for changed files.
        
        Args:
            workspace: Path to the repository workspace
            files_changed: List of changed file paths
            
        Returns:
            Validation results
        """
        try:
            results = {
                "linting": await self._run_linters(workspace, files_changed),
                "security": await self._run_security_checks(workspace, files_changed),
                "complexity": await self._analyze_complexity(workspace, files_changed),
                "formatting": await self._check_formatting(workspace, files_changed)
            }
            
            # Overall success if all checks pass
            results["success"] = all(
                check.get("success", False)
                for check in results.values()
                if isinstance(check, dict)
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error validating code quality: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def fix_issues(
        self,
        workspace: Path,
        issues: Dict[str, Any],
        max_iterations: int = 3
    ) -> Dict[str, Any]:
        """Iteratively fix issues found in code.
        
        Args:
            workspace: Path to the repository workspace
            issues: Issues to fix
            max_iterations: Maximum iterations for fixes
            
        Returns:
            Fix results
        """
        try:
            iteration = 0
            remaining_issues = issues.copy()
            fix_history = []
            
            while remaining_issues and iteration < max_iterations:
                iteration += 1
                logger.info(f"Fix iteration {iteration}/{max_iterations}")
                
                # Prepare fix prompt
                prompt = self._prepare_fix_prompt(remaining_issues)
                
                with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                    f.write(prompt)
                    prompt_file = f.name
                    
                try:
                    # Run Claude Code to fix issues
                    result = await self._run_claude_code(
                        workspace,
                        prompt_file,
                        f"fix_iteration_{iteration}"
                    )
                    
                    fix_details = self._parse_fix_results(result)
                    fix_history.append(fix_details)
                    
                    # Re-run validation
                    validation_results = await self.validate_code_quality(
                        workspace,
                        fix_details.get("files_modified", [])
                    )
                    
                    # Update remaining issues
                    remaining_issues = self._extract_remaining_issues(validation_results)
                    
                    if not remaining_issues:
                        logger.info("All issues fixed successfully")
                        break
                        
                finally:
                    if os.path.exists(prompt_file):
                        os.unlink(prompt_file)
                        
            return {
                "success": not remaining_issues,
                "iterations": iteration,
                "fix_history": fix_history,
                "remaining_issues": remaining_issues
            }
            
        except Exception as e:
            logger.error(f"Error fixing issues: {str(e)}")
            raise IntegrationError(f"Failed to fix issues: {str(e)}")
            
    async def _run_claude_code(
        self,
        workspace: Path,
        prompt_file: str,
        operation: str
    ) -> Dict[str, Any]:
        """Run Claude Code CLI command.
        
        Args:
            workspace: Working directory
            prompt_file: Path to prompt file
            operation: Operation being performed
            
        Returns:
            Command output
        """
        try:
            # Read the prompt from file
            with open(prompt_file, 'r') as f:
                prompt_content = f.read()
                
            # Log command (without sensitive data)
            logger.info(f"Running Claude Code for {operation}")
            
            # Create a more interactive prompt that guides Claude Code
            full_prompt = f"""<task>
{prompt_content}
</task>

Please complete this task. Use the following approach:
1. First understand the existing codebase structure
2. Implement the requested changes
3. Ensure code quality and follow existing patterns
4. Add appropriate tests if needed

Remember to:
- Use the available tools to explore and modify files
- Follow the project's coding standards
- Commit changes with descriptive messages when appropriate
"""
            
            # Run Claude Code using subprocess with proper interactive mode
            # Using echo to pipe the prompt as this is more reliable than file input
            cmd = f'echo {json.dumps(full_prompt)} | {self.claude_command}'
            
            if self.model:
                cmd += f' --model {self.model}'
                
            # Run command in the workspace directory
            process = await asyncio.create_subprocess_shell(
                cmd,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    **os.environ, 
                    "CLAUDE_CODE_OPERATION": operation,
                    "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "")
                }
            )
            
            stdout, stderr = await process.communicate()
            
            # Parse output
            output = stdout.decode() if stdout else ""
            error_output = stderr.decode() if stderr else ""
            
            # Claude Code may return 0 even with some stderr output (warnings)
            if process.returncode != 0 and "error" in error_output.lower():
                raise IntegrationError(f"Claude Code failed: {error_output}")
                
            # Extract file changes by analyzing git status in the workspace
            files_modified = await self._get_modified_files(workspace)
            
            # Get summary of changes
            summary = await self._get_change_summary(workspace)
            
            return {
                "success": True,
                "output": output,
                "error_output": error_output,
                "files_modified": files_modified,
                "operation": operation,
                "summary": summary
            }
            
        except Exception as e:
            logger.error(f"Error running Claude Code: {str(e)}")
            raise
            
    def _prepare_implementation_prompt(
        self,
        requirements: str,
        acceptance_criteria: List[str],
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Prepare prompt for feature implementation."""
        prompt = f"""{self.system_prompt}

## Feature Requirements

{requirements}

## Acceptance Criteria

"""
        for i, criterion in enumerate(acceptance_criteria, 1):
            prompt += f"{i}. {criterion}\n"
            
        if context:
            prompt += "\n## Additional Context\n\n"
            if context.get("related_files"):
                prompt += "### Related Files\n"
                for file in context["related_files"]:
                    prompt += f"- {file}\n"
                    
            if context.get("dependencies"):
                prompt += "\n### Dependencies\n"
                for dep in context["dependencies"]:
                    prompt += f"- {dep}\n"
                    
            if context.get("notes"):
                prompt += f"\n### Notes\n{context['notes']}\n"
                
        prompt += """

## Instructions

1. Analyze the existing codebase to understand patterns and conventions
2. Implement the feature according to the requirements
3. Ensure all acceptance criteria are met
4. Add appropriate tests for the new functionality
5. Include error handling and logging
6. Follow security best practices
7. Document your code with clear comments

Please implement this feature now.
"""
        
        return prompt
        
    def _prepare_analysis_prompt(self, focus_areas: Optional[List[str]]) -> str:
        """Prepare prompt for codebase analysis."""
        prompt = """Please analyze this codebase and provide insights on:

1. Overall architecture and structure
2. Key components and their responsibilities
3. Coding patterns and conventions used
4. Testing approach and frameworks
5. Build and deployment setup
6. Configuration management
7. Error handling patterns
8. Security considerations
"""
        
        if focus_areas:
            prompt += "\n\n## Focus Areas\n\n"
            for area in focus_areas:
                prompt += f"- {area}\n"
                
        prompt += "\n\nProvide a comprehensive analysis with specific examples from the code."
        
        return prompt
        
    def _prepare_fix_prompt(self, issues: Dict[str, Any]) -> str:
        """Prepare prompt for fixing issues."""
        prompt = """Please fix the following issues found in the code:

## Issues to Fix

"""
        
        if issues.get("linting"):
            prompt += "### Linting Issues\n"
            for issue in issues["linting"].get("issues", []):
                prompt += f"- {issue}\n"
                
        if issues.get("security"):
            prompt += "\n### Security Issues\n"
            for issue in issues["security"].get("issues", []):
                prompt += f"- {issue}\n"
                
        if issues.get("complexity"):
            prompt += "\n### Complexity Issues\n"
            for issue in issues["complexity"].get("issues", []):
                prompt += f"- {issue}\n"
                
        if issues.get("formatting"):
            prompt += "\n### Formatting Issues\n"
            for issue in issues["formatting"].get("issues", []):
                prompt += f"- {issue}\n"
                
        prompt += """

## Instructions

1. Fix each issue while maintaining functionality
2. Ensure fixes don't introduce new issues
3. Follow existing code patterns
4. Add comments explaining significant changes
5. Run tests to verify fixes don't break anything

Please fix these issues now.
"""
        
        return prompt
        
    def _parse_implementation_results(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Parse results from implementation."""
        return {
            "success": result.get("success", False),
            "files_modified": result.get("files_modified", []),
            "summary": self._extract_summary(result.get("output", "")),
            "tests_added": self._extract_tests(result.get("output", "")),
            "documentation_updated": self._check_documentation_updates(
                result.get("files_modified", [])
            )
        }
        
    def _parse_analysis_results(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Parse results from codebase analysis."""
        output = result.get("output", "")
        
        return {
            "architecture": self._extract_section(output, "architecture"),
            "components": self._extract_section(output, "components"),
            "patterns": self._extract_section(output, "patterns"),
            "testing": self._extract_section(output, "testing"),
            "configuration": self._extract_section(output, "configuration"),
            "summary": self._extract_summary(output)
        }
        
    def _parse_fix_results(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Parse results from issue fixes."""
        return {
            "success": result.get("success", False),
            "files_modified": result.get("files_modified", []),
            "fixes_applied": self._extract_fixes(result.get("output", "")),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    async def _detect_test_command(self, workspace: Path) -> Optional[str]:
        """Auto-detect test command for the project."""
        # Check for common test configurations
        test_configs = [
            ("package.json", ["npm test", "npm run test", "yarn test"]),
            ("Makefile", ["make test", "make check"]),
            ("setup.py", ["python -m pytest", "python setup.py test"]),
            ("pyproject.toml", ["pytest", "python -m pytest"]),
            ("go.mod", ["go test ./...", "go test -v ./..."]),
            ("pom.xml", ["mvn test", "mvn verify"]),
            ("build.gradle", ["gradle test", "./gradlew test"]),
            ("Cargo.toml", ["cargo test"]),
            (".github/workflows", ["npm test", "pytest"])  # Check CI configs
        ]
        
        for config_file, commands in test_configs:
            config_path = workspace / config_file
            if config_path.exists():
                # Try to find which command works
                for cmd in commands:
                    try:
                        # Test if command exists
                        test_process = await asyncio.create_subprocess_shell(
                            f"which {cmd.split()[0]}",
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL
                        )
                        await test_process.communicate()
                        
                        if test_process.returncode == 0:
                            return cmd
                    except:
                        continue
                        
        return None
        
    async def _run_linters(
        self,
        workspace: Path,
        files: List[str]
    ) -> Dict[str, Any]:
        """Run linters on files."""
        # Detect and run appropriate linters
        linters = {
            ".py": ["flake8", "pylint", "mypy"],
            ".js": ["eslint", "jshint"],
            ".ts": ["tslint", "eslint"],
            ".go": ["golint", "go vet"],
            ".java": ["checkstyle", "spotbugs"]
        }
        
        results = {"issues": [], "success": True}
        
        for file in files:
            ext = Path(file).suffix
            file_linters = linters.get(ext, [])
            
            for linter in file_linters:
                try:
                    process = await asyncio.create_subprocess_exec(
                        linter,
                        file,
                        cwd=workspace,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode != 0:
                        results["issues"].append({
                            "file": file,
                            "linter": linter,
                            "output": stdout.decode() if stdout else stderr.decode()
                        })
                        results["success"] = False
                except:
                    # Linter not available
                    continue
                    
        return results
        
    async def _run_security_checks(
        self,
        workspace: Path,
        files: List[str]
    ) -> Dict[str, Any]:
        """Run security checks on files."""
        # Basic security checks
        security_patterns = [
            r"password\s*=\s*[\"'][^\"']+[\"']",
            r"api_key\s*=\s*[\"'][^\"']+[\"']",
            r"secret\s*=\s*[\"'][^\"']+[\"']",
            r"token\s*=\s*[\"'][^\"']+[\"']"
        ]
        
        results = {"issues": [], "success": True}
        
        for file in files:
            try:
                file_path = workspace / file
                if file_path.exists():
                    content = file_path.read_text()
                    
                    for pattern in security_patterns:
                        import re
                        if re.search(pattern, content, re.IGNORECASE):
                            results["issues"].append({
                                "file": file,
                                "type": "hardcoded_secret",
                                "pattern": pattern
                            })
                            results["success"] = False
            except:
                continue
                
        return results
        
    async def _analyze_complexity(
        self,
        workspace: Path,
        files: List[str]
    ) -> Dict[str, Any]:
        """Analyze code complexity."""
        # Basic complexity analysis
        results = {"issues": [], "success": True}
        
        # This would use tools like radon, lizard, etc.
        # For now, basic implementation
        
        return results
        
    async def _check_formatting(
        self,
        workspace: Path,
        files: List[str]
    ) -> Dict[str, Any]:
        """Check code formatting."""
        # Check formatting with appropriate tools
        formatters = {
            ".py": "black --check",
            ".js": "prettier --check",
            ".go": "gofmt -l",
            ".java": "google-java-format --dry-run"
        }
        
        results = {"issues": [], "success": True}
        
        for file in files:
            ext = Path(file).suffix
            formatter = formatters.get(ext)
            
            if formatter:
                try:
                    cmd = f"{formatter} {file}"
                    process = await asyncio.create_subprocess_shell(
                        cmd,
                        cwd=workspace,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode != 0:
                        results["issues"].append({
                            "file": file,
                            "formatter": formatter,
                            "needs_formatting": True
                        })
                        results["success"] = False
                except:
                    continue
                    
        return results
        
    def _extract_modified_files(self, output: str) -> List[str]:
        """Extract list of modified files from output."""
        # Parse Claude Code output for file modifications
        files = []
        
        # Look for common patterns
        patterns = [
            r"Modified: (.+)",
            r"Created: (.+)",
            r"Updated: (.+)",
            r"\+\+\+ b/(.+)"
        ]
        
        import re
        for pattern in patterns:
            matches = re.findall(pattern, output)
            files.extend(matches)
            
        return list(set(files))
        
    def _extract_summary(self, output: str) -> str:
        """Extract summary from output."""
        # Look for summary section
        import re
        
        summary_match = re.search(
            r"(?:Summary|SUMMARY|## Summary)(.*?)(?=\n##|\n###|$)",
            output,
            re.DOTALL | re.IGNORECASE
        )
        
        if summary_match:
            return summary_match.group(1).strip()
            
        # Fallback to first paragraph
        paragraphs = output.split("\n\n")
        return paragraphs[0] if paragraphs else ""
        
    def _extract_tests(self, output: str) -> List[str]:
        """Extract test files from output."""
        test_patterns = [
            r"test_\w+\.py",
            r"\w+_test\.py",
            r"\w+\.test\.\w+",
            r"\w+\.spec\.\w+"
        ]
        
        tests = []
        import re
        
        for pattern in test_patterns:
            matches = re.findall(pattern, output)
            tests.extend(matches)
            
        return list(set(tests))
        
    def _check_documentation_updates(self, files: List[str]) -> bool:
        """Check if documentation was updated."""
        doc_extensions = [".md", ".rst", ".txt", ".adoc"]
        doc_folders = ["docs", "documentation", "doc"]
        
        for file in files:
            # Check extension
            if any(file.endswith(ext) for ext in doc_extensions):
                return True
                
            # Check if in doc folder
            if any(folder in file.lower() for folder in doc_folders):
                return True
                
        return False
        
    def _extract_section(self, output: str, section: str) -> str:
        """Extract specific section from output."""
        import re
        
        pattern = rf"(?:#{1,3}\s*{section}|{section.upper()})(.*?)(?=\n#{1,3}|\n[A-Z]+:|$)"
        match = re.search(pattern, output, re.DOTALL | re.IGNORECASE)
        
        if match:
            return match.group(1).strip()
            
        return ""
        
    def _extract_fixes(self, output: str) -> List[Dict[str, str]]:
        """Extract fixes applied from output."""
        fixes = []
        
        # Look for fix patterns
        import re
        
        fix_patterns = [
            r"Fixed: (.+)",
            r"Resolved: (.+)",
            r"Corrected: (.+)"
        ]
        
        for pattern in fix_patterns:
            matches = re.findall(pattern, output)
            for match in matches:
                fixes.append({"description": match})
                
        return fixes
        
    def _extract_remaining_issues(self, validation_results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract remaining issues from validation results."""
        remaining = {}
        
        for check_type, results in validation_results.items():
            if isinstance(results, dict) and not results.get("success", True):
                if results.get("issues"):
                    remaining[check_type] = results
                    
        return remaining
        
    async def _get_modified_files(self, workspace: Path) -> List[str]:
        """Get list of modified files using git status."""
        try:
            # Run git status to get modified files
            process = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.warning(f"Git status failed: {stderr.decode()}")
                return []
                
            files = []
            for line in stdout.decode().splitlines():
                if line.strip():
                    # Extract filename from git status output
                    # Format: XY filename
                    parts = line.strip().split(maxsplit=1)
                    if len(parts) >= 2:
                        files.append(parts[1])
                        
            return files
            
        except Exception as e:
            logger.error(f"Error getting modified files: {str(e)}")
            return []
            
    async def _get_change_summary(self, workspace: Path) -> str:
        """Get summary of changes using git diff."""
        try:
            # Run git diff to get change summary
            process = await asyncio.create_subprocess_exec(
                "git", "diff", "--stat",
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                # Try diff for staged files
                process = await asyncio.create_subprocess_exec(
                    "git", "diff", "--staged", "--stat",
                    cwd=workspace,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
            return stdout.decode() if stdout else "No changes detected"
            
        except Exception as e:
            logger.error(f"Error getting change summary: {str(e)}")
            return "Unable to get change summary"