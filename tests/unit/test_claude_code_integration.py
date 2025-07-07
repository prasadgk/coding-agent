"""Unit tests for Claude Code integration."""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import tempfile
import shutil

from src.core.claude_code_client import ClaudeCodeClient
from src.core.code_analyzer import CodeAnalyzer, CodeContext
from src.core.test_framework import TestFrameworkDetector, TestFramework, TestResult


class TestClaudeCodeClient:
    """Test Claude Code client functionality."""
    
    @pytest.fixture
    def claude_client(self):
        """Create Claude Code client instance."""
        config = {
            "claude_command": "claude",
            "model": "claude-3-opus-20240229",
            "max_tokens": 4096,
            "temperature": 0.3
        }
        return ClaudeCodeClient(config)
        
    @pytest.fixture
    def temp_workspace(self):
        """Create temporary workspace for testing."""
        workspace = tempfile.mkdtemp()
        yield Path(workspace)
        shutil.rmtree(workspace)
        
    @pytest.mark.asyncio
    async def test_implement_feature(self, claude_client, temp_workspace):
        """Test feature implementation with Claude Code."""
        # Mock the subprocess call
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            # Create mock process
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(
                b"Feature implemented successfully",
                b""
            ))
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process
            
            # Mock git operations
            with patch.object(claude_client, '_get_modified_files') as mock_modified:
                mock_modified.return_value = ["src/new_feature.py", "tests/test_new_feature.py"]
                
                with patch.object(claude_client, '_get_change_summary') as mock_summary:
                    mock_summary.return_value = "Added new feature implementation"
                    
                    # Test implementation
                    result = await claude_client.implement_feature(
                        workspace=temp_workspace,
                        requirements="Add user authentication feature",
                        acceptance_criteria=[
                            "Support email/password login",
                            "Include JWT token generation",
                            "Add password reset functionality"
                        ]
                    )
                    
                    # Verify results
                    assert result["success"] is True
                    assert "files_modified" in result
                    assert len(result["files_modified"]) == 2
                    assert "summary" in result
                    
    @pytest.mark.asyncio
    async def test_analyze_codebase(self, claude_client, temp_workspace):
        """Test codebase analysis functionality."""
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(
                b"Codebase analysis complete",
                b""
            ))
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process
            
            result = await claude_client.analyze_codebase(
                workspace=temp_workspace,
                focus_areas=["authentication", "database"]
            )
            
            assert "architecture" in result
            assert "components" in result
            assert "patterns" in result
            
    @pytest.mark.asyncio
    async def test_run_tests(self, claude_client, temp_workspace):
        """Test running tests in workspace."""
        # Create a fake test file
        test_file = temp_workspace / "test_example.py"
        test_file.write_text("def test_example(): pass")
        
        with patch.object(claude_client, '_detect_test_command') as mock_detect:
            mock_detect.return_value = "pytest"
            
            with patch('asyncio.create_subprocess_shell') as mock_subprocess:
                mock_process = AsyncMock()
                mock_process.communicate = AsyncMock(return_value=(
                    b"===== 1 passed in 0.01s =====",
                    b""
                ))
                mock_process.returncode = 0
                mock_subprocess.return_value = mock_process
                
                result = await claude_client.run_tests(workspace=temp_workspace)
                
                assert result["success"] is True
                assert result["command"] == "pytest"
                assert "1 passed" in result["stdout"]
                
    @pytest.mark.asyncio
    async def test_validate_code_quality(self, claude_client, temp_workspace):
        """Test code quality validation."""
        files_changed = ["src/example.py"]
        
        # Mock all validation methods
        with patch.object(claude_client, '_run_linters') as mock_linters:
            mock_linters.return_value = {"success": True, "issues": []}
            
            with patch.object(claude_client, '_run_security_checks') as mock_security:
                mock_security.return_value = {"success": True, "issues": []}
                
                with patch.object(claude_client, '_analyze_complexity') as mock_complexity:
                    mock_complexity.return_value = {"success": True, "issues": []}
                    
                    with patch.object(claude_client, '_check_formatting') as mock_formatting:
                        mock_formatting.return_value = {"success": True, "issues": []}
                        
                        result = await claude_client.validate_code_quality(
                            workspace=temp_workspace,
                            files_changed=files_changed
                        )
                        
                        assert result["success"] is True
                        assert result["linting"]["success"] is True
                        assert result["security"]["success"] is True
                        assert result["complexity"]["success"] is True
                        assert result["formatting"]["success"] is True
                        
    @pytest.mark.asyncio
    async def test_fix_issues(self, claude_client, temp_workspace):
        """Test iterative issue fixing."""
        issues = {
            "linting": {
                "success": False,
                "issues": ["Line too long", "Missing docstring"]
            }
        }
        
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(
                b"Issues fixed",
                b""
            ))
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process
            
            with patch.object(claude_client, 'validate_code_quality') as mock_validate:
                # First validation fails, second succeeds
                mock_validate.side_effect = [
                    {"success": False, "linting": {"success": False, "issues": ["One issue"]}},
                    {"success": True, "linting": {"success": True, "issues": []}}
                ]
                
                result = await claude_client.fix_issues(
                    workspace=temp_workspace,
                    issues=issues,
                    max_iterations=2
                )
                
                assert result["success"] is True
                assert result["iterations"] == 1
                assert len(result["remaining_issues"]) == 0


class TestCodeAnalyzer:
    """Test code analyzer functionality."""
    
    @pytest.fixture
    def analyzer(self):
        """Create code analyzer instance."""
        return CodeAnalyzer()
        
    @pytest.fixture
    def python_workspace(self, tmp_path):
        """Create a Python project workspace."""
        # Create project structure
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        
        # Create Python files
        (tmp_path / "setup.py").write_text("from setuptools import setup")
        (tmp_path / "requirements.txt").write_text("flask==2.0.0\npytest==6.0.0")
        (tmp_path / "src" / "__init__.py").touch()
        (tmp_path / "src" / "app.py").write_text("""
from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello World!'
""")
        (tmp_path / "tests" / "test_app.py").write_text("""
def test_hello():
    assert True
""")
        
        return tmp_path
        
    @pytest.mark.asyncio
    async def test_analyze_repository(self, analyzer, python_workspace):
        """Test repository analysis."""
        context = await analyzer.analyze_repository(python_workspace)
        
        assert context.language == "python"
        assert context.framework == "flask"
        assert "flask" in context.dependencies
        assert "pytest" in context.dependencies
        assert len(context.test_files) > 0
        assert len(context.entry_points) > 0
        
    def test_detect_language(self, analyzer, python_workspace):
        """Test language detection."""
        analyzer.workspace = python_workspace
        language = analyzer._detect_language()
        
        assert language == "python"
        
    def test_detect_framework(self, analyzer, python_workspace):
        """Test framework detection."""
        analyzer.workspace = python_workspace
        framework = analyzer._detect_framework("python")
        
        assert framework == "flask"
        
    def test_get_relevant_files(self, analyzer, python_workspace):
        """Test finding relevant files."""
        analyzer.workspace = python_workspace
        analyzer.context = CodeContext(
            language="python",
            framework="flask",
            dependencies=["flask", "pytest"],
            file_structure={},
            entry_points=["src/app.py"],
            test_files=["tests/test_app.py"],
            config_files=[],
            patterns={},
            metadata={}
        )
        
        files = analyzer.get_relevant_files(
            "Add authentication to the Flask app",
            max_files=10
        )
        
        # Should find app.py as relevant
        assert any("app.py" in f for f in files)


class TestTestFramework:
    """Test the test framework detection and execution."""
    
    @pytest.fixture
    def detector(self):
        """Create test framework detector."""
        return TestFrameworkDetector()
        
    @pytest.fixture
    def pytest_project(self, tmp_path):
        """Create a pytest project."""
        (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_example.py").write_text("""
def test_example():
    assert 1 + 1 == 2
    
def test_another():
    assert True
""")
        return tmp_path
        
    @pytest.mark.asyncio
    async def test_detect_framework_pytest(self, detector, pytest_project):
        """Test pytest framework detection."""
        framework = await detector.detect_framework(pytest_project)
        assert framework == TestFramework.PYTEST
        
    @pytest.mark.asyncio
    async def test_find_test_command(self, detector, pytest_project):
        """Test finding test command."""
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            # Mock 'which pytest' command
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process
            
            command = await detector.find_test_command(
                pytest_project,
                TestFramework.PYTEST
            )
            
            assert command in ["pytest", "python -m pytest"]
            
    @pytest.mark.asyncio
    async def test_run_tests_success(self, detector, pytest_project):
        """Test running tests successfully."""
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(
                b"===== 2 passed in 0.01s =====",
                b""
            ))
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process
            
            detector.detected_framework = TestFramework.PYTEST
            detector.test_command = "pytest"
            
            result = await detector.run_tests(pytest_project)
            
            assert result.framework == TestFramework.PYTEST
            assert result.total_tests == 2
            assert result.passed_tests == 2
            assert result.failed_tests == 0
            
    def test_parse_pytest_output(self, detector):
        """Test parsing pytest output."""
        output = """
collected 5 items

test_example.py::test_one PASSED
test_example.py::test_two PASSED
test_example.py::test_three FAILED
test_example.py::test_four PASSED
test_example.py::test_five SKIPPED

===== 3 passed, 1 failed, 1 skipped in 0.12s =====
"""
        
        result = detector._parse_pytest_output(output, 1, 0.12)
        
        assert result.total_tests == 5
        assert result.passed_tests == 3
        assert result.failed_tests == 1
        assert result.skipped_tests == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])