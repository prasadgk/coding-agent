"""Code analysis module for understanding repository context."""

import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass
import json
import yaml

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CodeContext:
    """Context information about the codebase."""
    language: str
    framework: Optional[str]
    dependencies: List[str]
    file_structure: Dict[str, Any]
    entry_points: List[str]
    test_files: List[str]
    config_files: List[str]
    patterns: Dict[str, Any]
    metadata: Dict[str, Any]


class CodeAnalyzer:
    """Analyzes codebase to provide context for code generation."""
    
    # Language detection patterns
    LANGUAGE_PATTERNS = {
        "python": {
            "extensions": [".py", ".pyw"],
            "files": ["setup.py", "requirements.txt", "pyproject.toml"],
            "patterns": ["import ", "from ", "def ", "class "]
        },
        "javascript": {
            "extensions": [".js", ".jsx", ".mjs"],
            "files": ["package.json", "yarn.lock", "npm-shrinkwrap.json"],
            "patterns": ["const ", "let ", "var ", "function ", "require(", "import "]
        },
        "typescript": {
            "extensions": [".ts", ".tsx"],
            "files": ["tsconfig.json", "package.json"],
            "patterns": ["interface ", "type ", "enum ", ": string", ": number"]
        },
        "java": {
            "extensions": [".java"],
            "files": ["pom.xml", "build.gradle", "build.gradle.kts"],
            "patterns": ["public class ", "private ", "protected ", "package "]
        },
        "go": {
            "extensions": [".go"],
            "files": ["go.mod", "go.sum"],
            "patterns": ["package ", "func ", "type ", "struct {", "interface {"]
        },
        "rust": {
            "extensions": [".rs"],
            "files": ["Cargo.toml", "Cargo.lock"],
            "patterns": ["fn ", "struct ", "impl ", "trait ", "mod "]
        }
    }
    
    # Framework detection patterns
    FRAMEWORK_PATTERNS = {
        "python": {
            "django": ["django", "settings.py", "manage.py", "urls.py"],
            "flask": ["flask", "app.py", "application.py"],
            "fastapi": ["fastapi", "uvicorn", "pydantic"],
            "pytest": ["pytest", "conftest.py", "test_*.py", "*_test.py"]
        },
        "javascript": {
            "react": ["react", "jsx", "useState", "useEffect"],
            "angular": ["@angular/core", "angular.json", "ng-"],
            "vue": ["vue", ".vue", "v-model", "v-if"],
            "express": ["express", "app.listen", "router.get"],
            "jest": ["jest", "describe(", "it(", "expect("]
        },
        "java": {
            "spring": ["org.springframework", "@SpringBootApplication", "@RestController"],
            "junit": ["org.junit", "@Test", "@Before", "@After"]
        }
    }
    
    def __init__(self):
        """Initialize code analyzer."""
        self.workspace: Optional[Path] = None
        self.context: Optional[CodeContext] = None
        
    async def analyze_repository(self, workspace: Path) -> CodeContext:
        """Analyze repository to build context.
        
        Args:
            workspace: Path to repository workspace
            
        Returns:
            CodeContext with analysis results
        """
        self.workspace = workspace
        
        # Detect primary language
        language = self._detect_language()
        
        # Detect framework
        framework = self._detect_framework(language)
        
        # Extract dependencies
        dependencies = await self._extract_dependencies(language)
        
        # Analyze file structure
        file_structure = self._analyze_file_structure()
        
        # Find entry points
        entry_points = self._find_entry_points(language)
        
        # Find test files
        test_files = self._find_test_files(language)
        
        # Find config files
        config_files = self._find_config_files()
        
        # Analyze coding patterns
        patterns = await self._analyze_patterns(language)
        
        # Gather metadata
        metadata = self._gather_metadata()
        
        self.context = CodeContext(
            language=language,
            framework=framework,
            dependencies=dependencies,
            file_structure=file_structure,
            entry_points=entry_points,
            test_files=test_files,
            config_files=config_files,
            patterns=patterns,
            metadata=metadata
        )
        
        return self.context
        
    def _detect_language(self) -> str:
        """Detect primary programming language."""
        language_scores = {}
        
        for language, patterns in self.LANGUAGE_PATTERNS.items():
            score = 0
            
            # Check file extensions
            for ext in patterns["extensions"]:
                files = list(self.workspace.rglob(f"*{ext}"))
                score += len(files) * 10
                
            # Check specific files
            for file in patterns["files"]:
                if (self.workspace / file).exists():
                    score += 50
                    
            language_scores[language] = score
            
        # Return language with highest score
        if language_scores:
            return max(language_scores, key=language_scores.get)
            
        return "unknown"
        
    def _detect_framework(self, language: str) -> Optional[str]:
        """Detect framework being used."""
        if language not in self.FRAMEWORK_PATTERNS:
            return None
            
        framework_scores = {}
        patterns = self.FRAMEWORK_PATTERNS[language]
        
        for framework, indicators in patterns.items():
            score = 0
            
            # Check for framework indicators
            for indicator in indicators:
                # Check in dependencies
                if language == "python":
                    req_file = self.workspace / "requirements.txt"
                    if req_file.exists() and indicator in req_file.read_text():
                        score += 100
                elif language in ["javascript", "typescript"]:
                    pkg_file = self.workspace / "package.json"
                    if pkg_file.exists():
                        try:
                            pkg_data = json.loads(pkg_file.read_text())
                            deps = {**pkg_data.get("dependencies", {}), 
                                   **pkg_data.get("devDependencies", {})}
                            if indicator in deps:
                                score += 100
                        except:
                            pass
                            
                # Check in files
                files = list(self.workspace.rglob(f"*{indicator}*"))
                score += len(files) * 5
                
            framework_scores[framework] = score
            
        if framework_scores:
            best_framework = max(framework_scores, key=framework_scores.get)
            if framework_scores[best_framework] > 50:
                return best_framework
                
        return None
        
    async def _extract_dependencies(self, language: str) -> List[str]:
        """Extract project dependencies."""
        dependencies = []
        
        if language == "python":
            # Check requirements.txt
            req_file = self.workspace / "requirements.txt"
            if req_file.exists():
                for line in req_file.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        dep = line.split("==")[0].split(">=")[0].split("<=")[0]
                        dependencies.append(dep)
                        
            # Check pyproject.toml
            pyproject = self.workspace / "pyproject.toml"
            if pyproject.exists():
                try:
                    import toml
                    data = toml.loads(pyproject.read_text())
                    deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                    dependencies.extend(deps.keys())
                except:
                    pass
                    
        elif language in ["javascript", "typescript"]:
            pkg_file = self.workspace / "package.json"
            if pkg_file.exists():
                try:
                    data = json.loads(pkg_file.read_text())
                    deps = data.get("dependencies", {})
                    dependencies.extend(deps.keys())
                except:
                    pass
                    
        elif language == "java":
            # Check pom.xml
            pom_file = self.workspace / "pom.xml"
            if pom_file.exists():
                # Simple XML parsing for dependencies
                content = pom_file.read_text()
                import re
                matches = re.findall(r'<artifactId>([^<]+)</artifactId>', content)
                dependencies.extend(matches)
                
        elif language == "go":
            go_mod = self.workspace / "go.mod"
            if go_mod.exists():
                for line in go_mod.read_text().splitlines():
                    if line.strip().startswith("require "):
                        parts = line.split()
                        if len(parts) >= 2:
                            dependencies.append(parts[1])
                            
        return list(set(dependencies))
        
    def _analyze_file_structure(self) -> Dict[str, Any]:
        """Analyze repository file structure."""
        structure = {
            "root_files": [],
            "directories": {},
            "total_files": 0,
            "file_types": {}
        }
        
        # Analyze root files
        for item in self.workspace.iterdir():
            if item.is_file():
                structure["root_files"].append(item.name)
                
        # Analyze directories
        for item in self.workspace.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                dir_info = self._analyze_directory(item)
                structure["directories"][item.name] = dir_info
                
        # Count file types
        for ext in [".py", ".js", ".ts", ".java", ".go", ".rs", ".md", ".json", ".yaml", ".yml"]:
            count = len(list(self.workspace.rglob(f"*{ext}")))
            if count > 0:
                structure["file_types"][ext] = count
                structure["total_files"] += count
                
        return structure
        
    def _analyze_directory(self, directory: Path) -> Dict[str, Any]:
        """Analyze a specific directory."""
        return {
            "files": len(list(directory.glob("*.*"))),
            "subdirs": len(list(directory.glob("*/"))),
            "purpose": self._infer_directory_purpose(directory.name)
        }
        
    def _infer_directory_purpose(self, name: str) -> str:
        """Infer the purpose of a directory from its name."""
        purpose_map = {
            "src": "source code",
            "lib": "library code",
            "test": "tests",
            "tests": "tests",
            "spec": "tests",
            "docs": "documentation",
            "doc": "documentation",
            "bin": "executables",
            "scripts": "utility scripts",
            "config": "configuration",
            "conf": "configuration",
            "static": "static assets",
            "public": "public assets",
            "templates": "templates",
            "models": "data models",
            "controllers": "controllers",
            "views": "views",
            "api": "API code",
            "utils": "utilities",
            "helpers": "helper functions",
            "migrations": "database migrations",
            "fixtures": "test fixtures"
        }
        
        name_lower = name.lower()
        for key, purpose in purpose_map.items():
            if key in name_lower:
                return purpose
                
        return "general"
        
    def _find_entry_points(self, language: str) -> List[str]:
        """Find application entry points."""
        entry_points = []
        
        common_entry_points = {
            "python": ["main.py", "app.py", "application.py", "run.py", "__main__.py", "manage.py"],
            "javascript": ["index.js", "app.js", "main.js", "server.js", "index.ts", "app.ts"],
            "java": ["Main.java", "Application.java", "*Application.java"],
            "go": ["main.go", "cmd/*/main.go"],
            "rust": ["main.rs", "src/main.rs"]
        }
        
        if language in common_entry_points:
            for pattern in common_entry_points[language]:
                if "*" in pattern:
                    files = list(self.workspace.rglob(pattern))
                else:
                    files = list(self.workspace.rglob(pattern))
                    
                entry_points.extend([str(f.relative_to(self.workspace)) for f in files])
                
        return entry_points
        
    def _find_test_files(self, language: str) -> List[str]:
        """Find test files in the repository."""
        test_patterns = {
            "python": ["test_*.py", "*_test.py", "tests/*.py", "test/*.py"],
            "javascript": ["*.test.js", "*.spec.js", "test/*.js", "tests/*.js", "__tests__/*.js"],
            "typescript": ["*.test.ts", "*.spec.ts", "test/*.ts", "tests/*.ts", "__tests__/*.ts"],
            "java": ["*Test.java", "*Tests.java", "src/test/**/*.java"],
            "go": ["*_test.go"],
            "rust": ["*_test.rs", "tests/*.rs"]
        }
        
        test_files = []
        
        if language in test_patterns:
            for pattern in test_patterns[language]:
                files = list(self.workspace.rglob(pattern))
                test_files.extend([str(f.relative_to(self.workspace)) for f in files])
                
        return list(set(test_files))
        
    def _find_config_files(self) -> List[str]:
        """Find configuration files."""
        config_patterns = [
            "*.json", "*.yaml", "*.yml", "*.toml", "*.ini", "*.cfg",
            "*.conf", ".env", ".env.*", "config/*", "conf/*",
            ".gitignore", ".dockerignore", "Dockerfile", "docker-compose.yml",
            "Makefile", "setup.py", "setup.cfg"
        ]
        
        config_files = []
        
        for pattern in config_patterns:
            files = list(self.workspace.rglob(pattern))
            config_files.extend([
                str(f.relative_to(self.workspace)) 
                for f in files 
                if f.is_file() and not any(part.startswith('.') for part in f.parts[:-1])
            ])
            
        return list(set(config_files))
        
    async def _analyze_patterns(self, language: str) -> Dict[str, Any]:
        """Analyze coding patterns in the repository."""
        patterns = {
            "naming_convention": self._detect_naming_convention(language),
            "indentation": self._detect_indentation(language),
            "imports_style": self._analyze_import_style(language),
            "error_handling": self._analyze_error_handling(language),
            "documentation": self._analyze_documentation(language),
            "testing_patterns": self._analyze_testing_patterns(language)
        }
        
        return patterns
        
    def _detect_naming_convention(self, language: str) -> str:
        """Detect naming convention used in the code."""
        if language == "python":
            # Check for snake_case vs camelCase
            snake_count = 0
            camel_count = 0
            
            for py_file in self.workspace.rglob("*.py"):
                try:
                    content = py_file.read_text()
                    snake_count += len(re.findall(r'\b[a-z]+_[a-z]+\b', content))
                    camel_count += len(re.findall(r'\b[a-z]+[A-Z][a-z]+\b', content))
                except:
                    pass
                    
            return "snake_case" if snake_count > camel_count else "camelCase"
            
        elif language in ["javascript", "typescript"]:
            return "camelCase"
        elif language == "java":
            return "camelCase"
        elif language == "go":
            return "camelCase"
            
        return "unknown"
        
    def _detect_indentation(self, language: str) -> str:
        """Detect indentation style."""
        space_count = 0
        tab_count = 0
        space_sizes = {2: 0, 4: 0}
        
        extensions = self.LANGUAGE_PATTERNS.get(language, {}).get("extensions", [])
        
        for ext in extensions:
            for file in self.workspace.rglob(f"*{ext}"):
                try:
                    lines = file.read_text().splitlines()[:100]  # Check first 100 lines
                    for line in lines:
                        if line.startswith('\t'):
                            tab_count += 1
                        elif line.startswith('  '):
                            space_count += 1
                            # Detect space size
                            indent = len(line) - len(line.lstrip())
                            if indent in space_sizes:
                                space_sizes[indent] += 1
                except:
                    pass
                    
        if tab_count > space_count:
            return "tabs"
        else:
            # Determine space size
            if space_sizes[2] > space_sizes[4]:
                return "2 spaces"
            else:
                return "4 spaces"
                
    def _analyze_import_style(self, language: str) -> Dict[str, Any]:
        """Analyze import/include style."""
        style = {"type": "unknown", "grouping": False, "sorting": False}
        
        if language == "python":
            # Check for import grouping and style
            for py_file in self.workspace.rglob("*.py"):
                try:
                    tree = ast.parse(py_file.read_text())
                    imports = [node for node in ast.walk(tree) 
                              if isinstance(node, (ast.Import, ast.ImportFrom))]
                    
                    if imports:
                        # Check if imports are grouped
                        # This is simplified; real implementation would be more complex
                        style["type"] = "standard"
                        style["grouping"] = True
                        break
                except:
                    pass
                    
        return style
        
    def _analyze_error_handling(self, language: str) -> Dict[str, Any]:
        """Analyze error handling patterns."""
        patterns = {"style": "unknown", "logging": False, "custom_exceptions": False}
        
        if language == "python":
            try_count = 0
            logging_count = 0
            custom_exc_count = 0
            
            for py_file in self.workspace.rglob("*.py"):
                try:
                    content = py_file.read_text()
                    try_count += content.count("try:")
                    logging_count += content.count("logger.") + content.count("logging.")
                    custom_exc_count += len(re.findall(r'class \w+Exception', content))
                except:
                    pass
                    
            if try_count > 0:
                patterns["style"] = "try-except"
            patterns["logging"] = logging_count > 10
            patterns["custom_exceptions"] = custom_exc_count > 0
            
        return patterns
        
    def _analyze_documentation(self, language: str) -> Dict[str, Any]:
        """Analyze documentation patterns."""
        doc_info = {
            "style": "unknown",
            "coverage": "low",
            "readme_exists": (self.workspace / "README.md").exists()
        }
        
        if language == "python":
            docstring_count = 0
            function_count = 0
            
            for py_file in self.workspace.rglob("*.py"):
                try:
                    content = py_file.read_text()
                    docstring_count += len(re.findall(r'"""[\s\S]*?"""', content))
                    function_count += content.count("def ")
                except:
                    pass
                    
            if function_count > 0:
                ratio = docstring_count / function_count
                if ratio > 0.7:
                    doc_info["coverage"] = "high"
                elif ratio > 0.3:
                    doc_info["coverage"] = "medium"
                    
            doc_info["style"] = "docstrings"
            
        return doc_info
        
    def _analyze_testing_patterns(self, language: str) -> Dict[str, Any]:
        """Analyze testing patterns."""
        test_info = {
            "framework": "unknown",
            "style": "unknown",
            "coverage_tool": None
        }
        
        if language == "python":
            # Check for testing frameworks
            if any(self.workspace.rglob("*pytest*")):
                test_info["framework"] = "pytest"
            elif any(self.workspace.rglob("*unittest*")):
                test_info["framework"] = "unittest"
                
            # Check for coverage tools
            if (self.workspace / ".coveragerc").exists():
                test_info["coverage_tool"] = "coverage.py"
                
        elif language in ["javascript", "typescript"]:
            pkg_file = self.workspace / "package.json"
            if pkg_file.exists():
                try:
                    data = json.loads(pkg_file.read_text())
                    deps = {**data.get("dependencies", {}), 
                           **data.get("devDependencies", {})}
                    
                    if "jest" in deps:
                        test_info["framework"] = "jest"
                    elif "mocha" in deps:
                        test_info["framework"] = "mocha"
                    elif "jasmine" in deps:
                        test_info["framework"] = "jasmine"
                except:
                    pass
                    
        return test_info
        
    def _gather_metadata(self) -> Dict[str, Any]:
        """Gather additional metadata about the repository."""
        metadata = {
            "size": self._calculate_repo_size(),
            "file_count": len(list(self.workspace.rglob("*.*"))),
            "has_ci": self._check_ci_config(),
            "has_docker": (self.workspace / "Dockerfile").exists(),
            "has_tests": len(self._find_test_files("*")) > 0,
            "last_modified": self._get_last_modified()
        }
        
        return metadata
        
    def _calculate_repo_size(self) -> int:
        """Calculate total repository size in bytes."""
        total_size = 0
        
        for file in self.workspace.rglob("*"):
            if file.is_file():
                try:
                    total_size += file.stat().st_size
                except:
                    pass
                    
        return total_size
        
    def _check_ci_config(self) -> bool:
        """Check if CI/CD configuration exists."""
        ci_indicators = [
            ".github/workflows",
            ".gitlab-ci.yml",
            "Jenkinsfile",
            ".travis.yml",
            ".circleci",
            "azure-pipelines.yml",
            "bitbucket-pipelines.yml"
        ]
        
        for indicator in ci_indicators:
            if (self.workspace / indicator).exists():
                return True
                
        return False
        
    def _get_last_modified(self) -> str:
        """Get last modification time of the repository."""
        import datetime
        
        latest_time = 0
        
        for file in self.workspace.rglob("*"):
            if file.is_file():
                try:
                    mtime = file.stat().st_mtime
                    if mtime > latest_time:
                        latest_time = mtime
                except:
                    pass
                    
        if latest_time > 0:
            return datetime.datetime.fromtimestamp(latest_time).isoformat()
            
        return "unknown"
        
    def get_relevant_files(self, ticket_description: str, max_files: int = 20) -> List[str]:
        """Get files most relevant to the ticket description.
        
        Args:
            ticket_description: Description of the ticket
            max_files: Maximum number of files to return
            
        Returns:
            List of relevant file paths
        """
        if not self.context:
            return []
            
        # Extract keywords from ticket description
        keywords = self._extract_keywords(ticket_description)
        
        # Score files based on relevance
        file_scores = {}
        
        for file in self.workspace.rglob("*.*"):
            if file.is_file():
                try:
                    relative_path = str(file.relative_to(self.workspace))
                    score = 0
                    
                    # Check filename
                    for keyword in keywords:
                        if keyword.lower() in file.name.lower():
                            score += 10
                            
                    # Check file path
                    for keyword in keywords:
                        if keyword.lower() in relative_path.lower():
                            score += 5
                            
                    # Boost test files if "test" is mentioned
                    if "test" in ticket_description.lower() and relative_path in self.context.test_files:
                        score += 20
                        
                    # Boost entry points for major features
                    if relative_path in self.context.entry_points:
                        score += 15
                        
                    if score > 0:
                        file_scores[relative_path] = score
                        
                except:
                    pass
                    
        # Sort by score and return top files
        sorted_files = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)
        return [file for file, _ in sorted_files[:max_files]]
        
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        # Remove common words
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "up", "about", "into", "through", "during",
            "before", "after", "above", "below", "between", "under", "again",
            "further", "then", "once", "that", "this", "these", "those", "is",
            "are", "was", "were", "been", "be", "have", "has", "had", "do",
            "does", "did", "will", "would", "could", "should", "may", "might",
            "must", "can", "need", "add", "update", "fix", "implement", "create"
        }
        
        # Extract words
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Filter keywords
        keywords = [
            word for word in words 
            if word not in stop_words and len(word) > 2
        ]
        
        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for word in keywords:
            if word not in seen:
                seen.add(word)
                unique_keywords.append(word)
                
        return unique_keywords