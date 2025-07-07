# Local Development Setup Guide

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Running Locally](#running-locally)
6. [Testing](#testing)
7. [Debugging](#debugging)
8. [Development Workflow](#development-workflow)
9. [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements
- **Operating System**: macOS, Linux, or Windows with WSL2
- **Python**: 3.9 or higher
- **Memory**: Minimum 8GB RAM (16GB recommended)
- **Storage**: At least 20GB free space for repositories

### Required Software

1. **Python 3.9+**
```bash
# Check Python version
python --version

# Install Python (macOS with Homebrew)
brew install python@3.9

# Install Python (Ubuntu/Debian)
sudo apt update
sudo apt install python3.9 python3.9-venv python3.9-dev

# Install Python (Windows)
# Download from https://www.python.org/downloads/
```

2. **Git**
```bash
# Install Git (macOS)
brew install git

# Install Git (Ubuntu/Debian)
sudo apt install git

# Configure Git
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

3. **Docker** (optional but recommended)
```bash
# Install Docker Desktop from https://www.docker.com/products/docker-desktop/
# Or use package manager:

# macOS
brew install --cask docker

# Ubuntu
sudo apt install docker.io docker-compose
sudo usermod -aG docker $USER
```

4. **Claude CLI**
```bash
# Install Claude CLI (replace with actual installation method)
# Note: This is a placeholder - use actual Claude CLI installation instructions
curl -o /usr/local/bin/claude https://claude-cli-url/claude
chmod +x /usr/local/bin/claude

# Verify installation
claude --version
```

5. **Additional Tools**
```bash
# Install development tools
pip install --user pipenv poetry pre-commit

# Install AWS CLI (optional, for AWS integration testing)
pip install --user awscli

# Install ngrok (for webhook testing)
# macOS
brew install ngrok

# Linux
wget https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-amd64.zip
unzip ngrok-stable-linux-amd64.zip
sudo mv ngrok /usr/local/bin/
```

## Environment Setup

### 1. Clone the Repository

```bash
# Clone the repository
git clone https://github.com/your-org/ai-coding-agent.git
cd ai-coding-agent

# Create a fork for development (optional)
git remote add fork https://github.com/your-username/ai-coding-agent.git
```

### 2. Create Python Virtual Environment

```bash
# Create virtual environment
python3.9 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows (WSL/Git Bash):
source venv/Scripts/activate

# Verify activation
which python
# Should show: /path/to/project/venv/bin/python
```

### 3. Install Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install the package in development mode
pip install -e .

# Install pre-commit hooks
pre-commit install
```

### 4. Set Up Environment Variables

Create a `.env` file in the project root:

```bash
# Copy example environment file
cp .env.example .env

# Edit .env file
nano .env  # or use your preferred editor
```

Example `.env` file:

```bash
# Environment
ENVIRONMENT=development
LOG_LEVEL=DEBUG

# API Keys
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# JIRA Configuration
JIRA_SERVER_URL=https://yourcompany.atlassian.net
JIRA_USERNAME=your-email@company.com
JIRA_API_TOKEN=your-jira-api-token

# Bitbucket Configuration
BITBUCKET_WORKSPACE=yourworkspace
BITBUCKET_USERNAME=your-username
BITBUCKET_APP_PASSWORD=your-app-password

# GitHub Configuration (optional)
GITHUB_TOKEN=your-github-token

# Local Development
WORKSPACE_PATH=/tmp/ai-agent-workspace
REPOSITORY_BASE_PATH=/tmp/ai-agent-repos

# API Settings
API_HOST=localhost
API_PORT=8000

# Testing
TEST_MODE=true
MOCK_CLAUDE_RESPONSES=false
```

### 5. Create Local Directories

```bash
# Create workspace directories
mkdir -p /tmp/ai-agent-workspace
mkdir -p /tmp/ai-agent-repos
mkdir -p logs

# Set permissions
chmod 755 /tmp/ai-agent-workspace
chmod 755 /tmp/ai-agent-repos
```

## Installation

### 1. Install Package

```bash
# Install in development mode
pip install -e .

# Verify installation
python -c "from src.core.agent import UniversalCodingAgent; print('✅ Package installed successfully')"
```

### 2. Download Additional Resources

```bash
# Download any required models or resources
python scripts/setup_resources.py
```

### 3. Verify Claude CLI

```bash
# Test Claude CLI
export ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
claude --version

# Test Claude with a simple prompt
echo "Say hello" | claude
```

## Configuration

### 1. Local Configuration File

Create `config/local.yaml`:

```yaml
# Local development configuration
app:
  environment: development
  debug: true
  log_level: DEBUG

# Agent settings
agent:
  workspace_path: /tmp/ai-agent-workspace
  max_concurrent_workflows: 2
  repo_cleanup_interval: 1  # Clean up every hour in dev

# Claude Code settings
claude_code:
  claude_command: claude
  model: claude-3-opus-20240229
  max_tokens: 4096
  temperature: 0.3

# Repository management
repository_management:
  base_workspace: /tmp/ai-agent-repos
  max_concurrent_repos: 5
  cleanup_interval_hours: 1
  enable_repository_caching: true

# Integrations (for local testing)
integrations:
  project_management:
    jira:
      enabled: true
      server_url: ${JIRA_SERVER_URL}
      username: ${JIRA_USERNAME}
      api_token: ${JIRA_API_TOKEN}
      
  version_control:
    bitbucket:
      enabled: true
      workspace: ${BITBUCKET_WORKSPACE}
      username: ${BITBUCKET_USERNAME}
      app_password: ${BITBUCKET_APP_PASSWORD}
      
    github:
      enabled: false  # Enable if testing with GitHub
      token: ${GITHUB_TOKEN}

# Local webhook testing
webhooks:
  base_url: http://localhost:8000/webhooks
  secret: local-webhook-secret

# Testing settings
testing:
  mock_external_services: false
  use_test_repositories: true
  cleanup_after_tests: true
```

### 2. Logging Configuration

Create `config/logging.yaml`:

```yaml
version: 1
disable_existing_loggers: false

formatters:
  default:
    format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  json:
    class: pythonjsonlogger.jsonlogger.JsonFormatter
    format: '%(asctime)s %(name)s %(levelname)s %(message)s'

handlers:
  console:
    class: logging.StreamHandler
    level: DEBUG
    formatter: default
    stream: ext://sys.stdout
    
  file:
    class: logging.handlers.RotatingFileHandler
    level: DEBUG
    formatter: json
    filename: logs/app.log
    maxBytes: 10485760  # 10MB
    backupCount: 5

root:
  level: INFO
  handlers: [console, file]

loggers:
  src:
    level: DEBUG
    handlers: [console, file]
    propagate: false
    
  asyncio:
    level: WARNING
    
  urllib3:
    level: WARNING
```

## Running Locally

### 1. Start the API Server

```bash
# Using Python directly
python -m src.main

# Using uvicorn for FastAPI
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Using the CLI script
./scripts/run_local.sh
```

### 2. Run in Docker (Optional)

```bash
# Build Docker image
docker build -t ai-coding-agent:local .

# Run container
docker run -it --rm \
  -v /tmp/ai-agent-workspace:/workspace \
  -v /tmp/ai-agent-repos:/repos \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e JIRA_USERNAME=$JIRA_USERNAME \
  -e JIRA_API_TOKEN=$JIRA_API_TOKEN \
  -p 8000:8000 \
  ai-coding-agent:local
```

### 3. Test Webhook Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Test JIRA webhook
curl -X POST http://localhost:8000/webhooks/jira \
  -H "Content-Type: application/json" \
  -d @examples/jira-webhook-payload.json

# Test Bitbucket webhook
curl -X POST http://localhost:8000/webhooks/bitbucket \
  -H "Content-Type: application/json" \
  -d @examples/bitbucket-webhook-payload.json
```

### 4. Using ngrok for External Webhooks

```bash
# Start ngrok tunnel
ngrok http 8000

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
# Use this URL in JIRA/Bitbucket webhook configuration
```

## Testing

### 1. Run Unit Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_claude_code_integration.py

# Run tests with verbose output
pytest -v

# Run tests matching pattern
pytest -k "test_claude"
```

### 2. Run Integration Tests

```bash
# Set test environment variables
export TEST_MODE=true

# Run integration tests
pytest tests/integration/ -v

# Run specific integration
pytest tests/integration/test_jira_integration.py::test_webhook_processing
```

### 3. Run Linting and Type Checking

```bash
# Run flake8
flake8 src/

# Run black (formatting)
black src/ --check

# Run mypy (type checking)
mypy src/

# Run all checks
pre-commit run --all-files
```

### 4. Test Workflow Locally

Create `scripts/test_workflow.py`:

```python
#!/usr/bin/env python3
import asyncio
from src.core.agent import UniversalCodingAgent
from src.config.settings import get_settings
from src.integrations.base.project_management import Ticket

async def test_local_workflow():
    """Test a complete workflow locally."""
    settings = get_settings()
    agent_config = settings.get_agent_config()
    
    # Initialize agent
    agent = UniversalCodingAgent(agent_config)
    
    # Create test ticket
    test_ticket = Ticket(
        id="TEST-001",
        title="Add hello world function",
        description="Create a simple hello world function",
        assignee="ai-agent",
        status="To Do",
        priority="Medium",
        labels=["test", "feature"],
        repository="https://github.com/test/test-repo",
        acceptance_criteria=["Function returns 'Hello, World!'"],
        platform="jira"
    )
    
    # Execute workflow
    try:
        execution = await agent.workflow_engine.execute_workflow(test_ticket)
        print(f"✅ Workflow completed: {execution.id}")
        print(f"Status: {execution.state}")
        
        # Print step results
        for step in execution.steps:
            print(f"  - {step.step_name}: {step.status}")
            
    except Exception as e:
        print(f"❌ Workflow failed: {e}")
        
    # Cleanup
    await agent.shutdown()

if __name__ == "__main__":
    asyncio.run(test_local_workflow())
```

## Debugging

### 1. Enable Debug Logging

```python
# In your code
import logging
logging.basicConfig(level=logging.DEBUG)

# Or set environment variable
export LOG_LEVEL=DEBUG
```

### 2. Use Python Debugger

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use IPython debugger
import ipdb; ipdb.set_trace()
```

### 3. VS Code Debug Configuration

Create `.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: AI Agent",
            "type": "python",
            "request": "launch",
            "module": "src.main",
            "env": {
                "PYTHONPATH": "${workspaceFolder}",
                "LOG_LEVEL": "DEBUG"
            },
            "envFile": "${workspaceFolder}/.env",
            "console": "integratedTerminal"
        },
        {
            "name": "Python: Current File",
            "type": "python",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal"
        },
        {
            "name": "Python: Test",
            "type": "python",
            "request": "launch",
            "module": "pytest",
            "args": ["-v", "${file}"],
            "console": "integratedTerminal"
        }
    ]
}
```

### 4. Debug API Requests

```bash
# Use httpie for better formatting
pip install httpie

# Make API request with httpie
http POST localhost:8000/webhooks/jira < examples/jira-webhook-payload.json

# Use curl with verbose output
curl -v -X POST http://localhost:8000/webhooks/jira \
  -H "Content-Type: application/json" \
  -d @examples/jira-webhook-payload.json
```

## Development Workflow

### 1. Feature Development

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes
# ... edit files ...

# Run tests
pytest tests/

# Commit changes
git add .
git commit -m "feat: add your feature description"

# Push to fork
git push fork feature/your-feature-name
```

### 2. Testing with Real Services

1. **Create Test JIRA Project**
   - Create a sandbox JIRA project
   - Create test tickets
   - Configure webhook to point to ngrok URL

2. **Create Test Repository**
   - Create a test repository in Bitbucket/GitHub
   - Add sample code
   - Configure repository access

3. **Run End-to-End Test**
   ```bash
   # Start local server with ngrok
   ./scripts/run_local_with_ngrok.sh
   
   # Assign ticket to AI agent in JIRA
   # Monitor logs
   tail -f logs/app.log | jq '.'
   ```

### 3. Mock Services for Testing

Create `tests/mocks/mock_claude.py`:

```python
class MockClaudeClient:
    """Mock Claude client for testing."""
    
    async def implement_feature(self, workspace, requirements, acceptance_criteria, context=None):
        """Mock feature implementation."""
        # Create a simple file
        test_file = workspace / "hello.py"
        test_file.write_text('''
def hello_world():
    """Say hello."""
    return "Hello, World!"
''')
        
        return {
            "success": True,
            "files_modified": ["hello.py"],
            "summary": "Created hello world function"
        }
```

### 4. Performance Profiling

```python
# Add profiling decorator
import cProfile
import pstats
from functools import wraps

def profile(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        result = func(*args, **kwargs)
        pr.disable()
        
        stats = pstats.Stats(pr)
        stats.sort_stats('cumulative')
        stats.print_stats(20)
        
        return result
    return wrapper

# Use on slow functions
@profile
async def slow_function():
    # ... code ...
```

## Troubleshooting

### Common Issues

1. **Claude CLI not found**
   ```bash
   # Check if claude is in PATH
   which claude
   
   # Add to PATH if needed
   export PATH=$PATH:/path/to/claude
   
   # Or use full path in config
   claude_command: /usr/local/bin/claude
   ```

2. **API Key Issues**
   ```bash
   # Verify API key is set
   echo $ANTHROPIC_API_KEY
   
   # Test API key
   curl https://api.anthropic.com/v1/messages \
     -H "x-api-key: $ANTHROPIC_API_KEY" \
     -H "anthropic-version: 2023-06-01"
   ```

3. **Repository Permission Issues**
   ```bash
   # Fix permissions
   sudo chown -R $USER:$USER /tmp/ai-agent-repos
   chmod -R 755 /tmp/ai-agent-repos
   ```

4. **Memory Issues**
   ```bash
   # Increase Python memory limit
   export PYTHONMAXMEM=4G
   
   # Or use Docker with memory limits
   docker run -m 4g ai-coding-agent:local
   ```

5. **Port Already in Use**
   ```bash
   # Find process using port
   lsof -i :8000
   
   # Kill process
   kill -9 <PID>
   
   # Or use different port
   API_PORT=8001 python -m src.main
   ```

### Debug Checklist

- [ ] Environment variables loaded correctly
- [ ] Claude CLI accessible and authenticated
- [ ] JIRA/Bitbucket credentials valid
- [ ] Workspace directories exist and writable
- [ ] No port conflicts
- [ ] Sufficient disk space
- [ ] Python dependencies installed
- [ ] Git configured correctly

### Getting Help

1. Check logs: `tail -f logs/app.log`
2. Enable debug mode: `LOG_LEVEL=DEBUG`
3. Run health check: `curl localhost:8000/health`
4. Check documentation: `docs/`
5. Run diagnostics: `python scripts/diagnose.py`

## Development Tools

### Recommended VS Code Extensions

```json
{
    "recommendations": [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "ms-python.black-formatter",
        "charliermarsh.ruff",
        "tamasfe.even-better-toml",
        "redhat.vscode-yaml",
        "ms-azuretools.vscode-docker",
        "github.copilot"
    ]
}
```

### Useful Scripts

1. **Clean workspace**
   ```bash
   ./scripts/clean_workspace.sh
   ```

2. **Reset database**
   ```bash
   ./scripts/reset_db.sh
   ```

3. **Generate test data**
   ```bash
   python scripts/generate_test_data.py
   ```

4. **Monitor performance**
   ```bash
   ./scripts/monitor.sh
   ```

This completes the comprehensive local development setup guide.