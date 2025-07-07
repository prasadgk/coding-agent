#!/usr/bin/env python3
"""Script to run the API server locally."""

import os
import sys
import uvicorn
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config.settings import get_settings

def main():
    """Run the API server."""
    settings = get_settings()
    
    print(f"Starting {settings.app_name} API Server...")
    print(f"Environment: {settings.environment}")
    print(f"API URL: http://{settings.api_host}:{settings.api_port}")
    print(f"Docs: http://{settings.api_host}:{settings.api_port}/docs")
    print("\nWebhook endpoints:")
    print(f"  - JIRA: http://{settings.api_host}:{settings.api_port}/webhooks/jira")
    print(f"  - Bitbucket: http://{settings.api_host}:{settings.api_port}/webhooks/bitbucket")
    print(f"  - GitHub: http://{settings.api_host}:{settings.api_port}/webhooks/github")
    print(f"  - Azure DevOps: http://{settings.api_host}:{settings.api_port}/webhooks/azure-devops")
    print("\nPress CTRL+C to stop the server\n")
    
    # Run the server
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
        log_level=settings.monitoring.log_level.lower(),
        access_log=True
    )

if __name__ == "__main__":
    main()