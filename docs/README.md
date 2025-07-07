# AI Coding Agent Documentation

Welcome to the comprehensive documentation for the Universal AI Coding Agent platform. This documentation covers everything you need to know about deploying, verifying, and running the AI Coding Agent.

## 📚 Documentation Structure

### 🚀 [Deployment](./deployment/)
- **[AWS Deployment Guide](./deployment/aws-deployment-guide.md)** - Complete guide for deploying to AWS using ECS, Lambda, and other AWS services
  - Infrastructure setup with AWS CDK
  - Docker containerization
  - Security configuration
  - Monitoring and maintenance
  - Cost optimization

### ✅ [Verification](./verification/)
- **[Verification Guide](./verification/verification-guide.md)** - Comprehensive testing and verification procedures
  - Pre-deployment verification
  - Post-deployment verification
  - Integration testing
  - End-to-end testing
  - Performance testing
  - Security verification

### 💻 [Local Development](./local-development/)
- **[Local Setup Guide](./local-development/local-setup-guide.md)** - Complete guide for local development
  - Prerequisites and system requirements
  - Environment setup
  - Configuration
  - Running locally
  - Testing and debugging
  - Development workflow

### 📋 [Requirements](./requirements/)
- **[Requirements Document](./requirements/requirements_document.md)** - Detailed functional and non-functional requirements

### 💡 [Prompts](./prompts/)
- **[Claude Code Prompt](./prompts/claude_code_prompt.md)** - Implementation prompts and guidelines
- **[User Prompts](./prompts/user_prompts.md)** - Example user prompts and interactions

### 📊 [Project Status](./project_status.md)
- Current implementation status and roadmap

## 🎯 Quick Start

### For Local Development
```bash
# Clone the repository
git clone https://github.com/your-org/ai-coding-agent.git
cd ai-coding-agent

# Run quick start script
./scripts/quick_start.sh

# Configure your API keys in .env
nano .env

# Start the application
python -m src.main
```

### For AWS Deployment
```bash
# Install AWS CDK
npm install -g aws-cdk

# Deploy infrastructure
cd infrastructure/cdk
cdk deploy --all

# Build and push Docker image
./scripts/deploy_to_aws.sh
```

## 🔑 Key Features

- **Multi-Platform Support**: Integrates with JIRA, Azure DevOps, Bitbucket, GitHub, and more
- **AI-Powered Code Generation**: Uses Claude Code for intelligent code generation
- **Automated Workflow**: From ticket assignment to pull request creation
- **Repository Management**: Efficient repository pooling and caching
- **Comprehensive Testing**: Built-in test framework detection and execution
- **Enterprise Security**: AWS Secrets Manager integration, encrypted communications
- **Scalable Architecture**: Auto-scaling with ECS Fargate

## 📖 How to Use This Documentation

1. **New Users**: Start with the [Local Setup Guide](./local-development/local-setup-guide.md) to get familiar with the platform
2. **Deployment**: Follow the [AWS Deployment Guide](./deployment/aws-deployment-guide.md) for production deployment
3. **Testing**: Use the [Verification Guide](./verification/verification-guide.md) to ensure everything is working correctly
4. **Development**: Refer to the [Requirements Document](./requirements/requirements_document.md) for detailed specifications

## 🛠️ Technology Stack

- **Language**: Python 3.9+
- **AI Model**: Claude (Anthropic)
- **Cloud Platform**: AWS (ECS, Lambda, API Gateway, Secrets Manager)
- **Integrations**: JIRA, Bitbucket, GitHub, Azure DevOps
- **Testing**: pytest, unittest
- **Monitoring**: CloudWatch, Prometheus

## 📞 Support

- **Issues**: Create an issue in the GitHub repository
- **Documentation**: This documentation is continuously updated
- **Contributing**: See CONTRIBUTING.md in the repository root

## 🔄 Version History

- **v1.0.0** - Initial release with core functionality
- **v1.1.0** - Added repository management optimization
- **v1.2.0** - Enhanced Claude Code integration

## 📝 License

This project is licensed under the terms specified in the LICENSE file in the repository root.

---

For the most up-to-date information, always refer to the latest version of this documentation.