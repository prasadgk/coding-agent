#!/bin/bash

# Quick Start Script for AI Coding Agent
# This script sets up the development environment quickly

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Header
echo "🚀 AI Coding Agent - Quick Start Setup"
echo "===================================="
echo

# Check Python version
print_info "Checking Python version..."
if command -v python3.9 &> /dev/null; then
    PYTHON_CMD=python3.9
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [[ $(echo "$PYTHON_VERSION >= 3.9" | bc) -eq 1 ]]; then
        PYTHON_CMD=python3
    else
        print_error "Python 3.9+ is required. Found: Python $PYTHON_VERSION"
        exit 1
    fi
else
    print_error "Python 3.9+ is not installed"
    exit 1
fi
print_success "Python version OK: $($PYTHON_CMD --version)"

# Check Git
print_info "Checking Git..."
if ! command -v git &> /dev/null; then
    print_error "Git is not installed"
    exit 1
fi
print_success "Git is installed: $(git --version)"

# Check Claude CLI
print_info "Checking Claude CLI..."
if ! command -v claude &> /dev/null; then
    print_error "Claude CLI is not installed"
    echo "Please install Claude CLI first: https://docs.anthropic.com/claude/docs/claude-cli"
    exit 1
fi
print_success "Claude CLI is installed"

# Create virtual environment
print_info "Creating Python virtual environment..."
if [ ! -d "venv" ]; then
    $PYTHON_CMD -m venv venv
    print_success "Virtual environment created"
else
    print_info "Virtual environment already exists"
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source venv/bin/activate || source venv/Scripts/activate

# Upgrade pip
print_info "Upgrading pip..."
pip install --upgrade pip --quiet

# Install dependencies
print_info "Installing dependencies..."
pip install -r requirements.txt --quiet
print_success "Dependencies installed"

# Install dev dependencies if they exist
if [ -f "requirements-dev.txt" ]; then
    print_info "Installing development dependencies..."
    pip install -r requirements-dev.txt --quiet
    print_success "Development dependencies installed"
fi

# Install package in development mode
print_info "Installing package in development mode..."
pip install -e . --quiet
print_success "Package installed"

# Create necessary directories
print_info "Creating workspace directories..."
mkdir -p /tmp/ai-agent-workspace
mkdir -p /tmp/ai-agent-repos
mkdir -p logs
print_success "Directories created"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    print_info "Creating .env file..."
    cat > .env << EOF
# Environment
ENVIRONMENT=development
LOG_LEVEL=DEBUG

# API Keys (REPLACE WITH YOUR ACTUAL KEYS)
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# JIRA Configuration
JIRA_SERVER_URL=https://yourcompany.atlassian.net
JIRA_USERNAME=your-email@company.com
JIRA_API_TOKEN=your-jira-api-token

# Bitbucket Configuration
BITBUCKET_WORKSPACE=yourworkspace
BITBUCKET_USERNAME=your-username
BITBUCKET_APP_PASSWORD=your-app-password

# Local Development
WORKSPACE_PATH=/tmp/ai-agent-workspace
REPOSITORY_BASE_PATH=/tmp/ai-agent-repos

# API Settings
API_HOST=localhost
API_PORT=8000
EOF
    print_success ".env file created"
    print_error "⚠️  Please edit .env file and add your API keys!"
else
    print_info ".env file already exists"
fi

# Install pre-commit hooks
if command -v pre-commit &> /dev/null; then
    print_info "Installing pre-commit hooks..."
    pre-commit install
    print_success "Pre-commit hooks installed"
fi

# Run basic tests
print_info "Running basic tests..."
python -c "from src.core.agent import UniversalCodingAgent; print('✅ Import test passed')" || {
    print_error "Import test failed"
    exit 1
}

# Check if API keys are configured
if grep -q "your-anthropic-api-key-here" .env; then
    print_error "⚠️  Please configure your API keys in .env file!"
    echo
    echo "Required API keys:"
    echo "  - ANTHROPIC_API_KEY: Get from https://console.anthropic.com/"
    echo "  - JIRA credentials: Get from your Atlassian account"
    echo "  - Bitbucket credentials: Get from your Bitbucket account"
    echo
fi

# Success message
echo
print_success "🎉 Setup complete!"
echo
echo "Next steps:"
echo "1. Edit .env file and add your API keys"
echo "2. Activate virtual environment: source venv/bin/activate"
echo "3. Run the application: python -m src.main"
echo "4. Run tests: pytest"
echo
echo "For more information, see:"
echo "  - docs/local-development/local-setup-guide.md"
echo "  - docs/deployment/aws-deployment-guide.md"
echo "  - docs/verification/verification-guide.md"
echo

# Optional: Start the application
read -p "Would you like to start the application now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "Starting AI Coding Agent..."
    python -m src.main
fi