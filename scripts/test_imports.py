#!/usr/bin/env python3
"""Test script to verify all imports are working correctly."""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """Test all major imports."""
    print("Testing imports...")
    
    try:
        # Config imports
        print("  - Testing config imports...")
        from src.config.settings import get_settings, AgentConfig
        
        # Core imports
        print("  - Testing core imports...")
        from src.core.agent import UniversalCodingAgent
        from src.core.claude_code_client import ClaudeCodeClient
        from src.core.code_analyzer import CodeAnalyzer
        from src.core.workflow_engine import WorkflowEngine
        from src.core.plugin_loader import PluginLoader
        from src.core.error_recovery import ErrorRecoveryManager
        
        # Repository management imports
        print("  - Testing repository management imports...")
        from src.core.repository_management.manager import RepositoryManager
        from src.core.repository_management.pool import RepositoryPool
        from src.core.repository_management.locking import RepositoryLockManager
        
        # Integration imports
        print("  - Testing integration imports...")
        from src.integrations.base.project_management import Ticket, ProjectManagementIntegration
        from src.integrations.base.version_control import VersionControlIntegration
        from src.integrations.project_management.jira import JIRAIntegration
        from src.integrations.version_control.bitbucket import BitbucketIntegration
        
        # Utils imports
        print("  - Testing utils imports...")
        from src.utils.logging import get_logger, setup_logging
        from src.utils.exceptions import IntegrationError, WorkflowError
        from src.utils.metrics import MetricsCollector
        from src.utils.retry import with_retry
        
        # API imports
        print("  - Testing API imports...")
        from src.api.main import app
        from src.api.webhooks import router as webhook_router
        from src.api.rest import router as rest_router
        
        print("\n✅ All imports successful!")
        return True
        
    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False

def test_basic_initialization():
    """Test basic initialization of key components."""
    print("\nTesting basic initialization...")
    
    try:
        from src.config.settings import get_settings
        settings = get_settings()
        print(f"  - Settings loaded: {settings.app_name}")
        
        # Test logger
        from src.utils.logging import get_logger
        logger = get_logger(__name__)
        print("  - Logger initialized")
        
        print("\n✅ Basic initialization successful!")
        return True
        
    except Exception as e:
        print(f"\n❌ Initialization error: {e}")
        return False

if __name__ == "__main__":
    print("AI Coding Agent - Build Verification Test")
    print("=" * 50)
    
    success = True
    
    # Test imports
    if not test_imports():
        success = False
        
    # Test basic initialization
    if not test_basic_initialization():
        success = False
        
    # Final result
    print("\n" + "=" * 50)
    if success:
        print("✅ All tests passed! Build is working correctly.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Please check the errors above.")
        sys.exit(1)