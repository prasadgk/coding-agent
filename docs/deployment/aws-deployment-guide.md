# AWS Deployment Guide for Universal AI Coding Agent

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Architecture Overview](#architecture-overview)
3. [Infrastructure Setup](#infrastructure-setup)
4. [Deployment Steps](#deployment-steps)
5. [Configuration](#configuration)
6. [Monitoring and Maintenance](#monitoring-and-maintenance)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Tools
- AWS CLI configured with appropriate credentials
- Docker installed locally
- Python 3.9+ installed
- AWS CDK (Cloud Development Kit) installed
- Terraform (optional, if using Terraform instead of CDK)

### AWS Services Required
- ECS (Elastic Container Service) with Fargate
- ECR (Elastic Container Registry)
- Lambda for webhook handlers
- API Gateway for webhook endpoints
- Secrets Manager for credentials
- CloudWatch for logging and monitoring
- VPC with private subnets
- S3 for artifact storage (optional)
- RDS or DynamoDB for state management (optional)

### AWS Account Setup
```bash
# Install AWS CLI
pip install awscli

# Configure AWS credentials
aws configure

# Install AWS CDK
npm install -g aws-cdk

# Bootstrap CDK (one-time setup)
cdk bootstrap aws://ACCOUNT-NUMBER/REGION
```

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   API Gateway   │────▶│     Lambda      │────▶│   ECS Tasks     │
│   (Webhooks)    │     │   (Handlers)    │     │ (Agent Workers) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                │                         │
                                ▼                         ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │ Secrets Manager │     │  EFS/Storage    │
                        │  (Credentials)   │     │ (Repositories)  │
                        └─────────────────┘     └─────────────────┘
```

## Infrastructure Setup

### 1. Create Infrastructure as Code

Create `infrastructure/cdk/app.py`:

```python
#!/usr/bin/env python3
import os
from aws_cdk import App
from stacks.agent_stack import AIAgentStack
from stacks.network_stack import NetworkStack
from stacks.storage_stack import StorageStack

app = App()

# Network infrastructure
network_stack = NetworkStack(app, "AIAgentNetwork",
    env={
        'account': os.environ['CDK_DEFAULT_ACCOUNT'],
        'region': os.environ['CDK_DEFAULT_REGION']
    }
)

# Storage infrastructure
storage_stack = StorageStack(app, "AIAgentStorage",
    vpc=network_stack.vpc
)

# Main application stack
agent_stack = AIAgentStack(app, "AIAgentStack",
    vpc=network_stack.vpc,
    storage=storage_stack.efs_filesystem
)

app.synth()
```

### 2. Network Stack

Create `infrastructure/cdk/stacks/network_stack.py`:

```python
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
)
from constructs import Construct

class NetworkStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        # Create VPC
        self.vpc = ec2.Vpc(self, "AIAgentVPC",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT,
                    cidr_mask=24
                )
            ]
        )
        
        # Security groups
        self.ecs_security_group = ec2.SecurityGroup(
            self, "ECSSecurityGroup",
            vpc=self.vpc,
            description="Security group for ECS tasks",
            allow_all_outbound=True
        )
        
        self.lambda_security_group = ec2.SecurityGroup(
            self, "LambdaSecurityGroup",
            vpc=self.vpc,
            description="Security group for Lambda functions",
            allow_all_outbound=True
        )
```

### 3. Main Application Stack

Create `infrastructure/cdk/stacks/agent_stack.py`:

```python
from aws_cdk import (
    Stack,
    Duration,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_secretsmanager as secrets,
    aws_iam as iam,
    aws_logs as logs,
    aws_ecr as ecr,
)
from constructs import Construct

class AIAgentStack(Stack):
    def __init__(self, scope: Construct, id: str, vpc, storage, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        # ECR Repository
        ecr_repo = ecr.Repository(self, "AIAgentRepo",
            repository_name="ai-coding-agent",
            lifecycle_rules=[{
                "max_image_count": 10
            }]
        )
        
        # ECS Cluster
        cluster = ecs.Cluster(self, "AIAgentCluster",
            vpc=vpc,
            cluster_name="ai-agent-cluster"
        )
        
        # Task Definition
        task_definition = ecs.FargateTaskDefinition(
            self, "AIAgentTaskDef",
            memory_limit_mib=4096,
            cpu=2048,
            volumes=[{
                "name": "workspace",
                "efs_volume_configuration": {
                    "file_system_id": storage.file_system_id,
                    "root_directory": "/",
                    "transit_encryption": "ENABLED"
                }
            }]
        )
        
        # Container
        container = task_definition.add_container(
            "ai-agent",
            image=ecs.ContainerImage.from_ecr_repository(ecr_repo),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ai-agent",
                log_retention=logs.RetentionDays.ONE_MONTH
            ),
            environment={
                "ENVIRONMENT": "production",
                "LOG_LEVEL": "INFO"
            },
            secrets={
                "ANTHROPIC_API_KEY": ecs.Secret.from_secrets_manager(
                    secrets.Secret.from_secret_name_v2(
                        self, "AnthropicKey", "ai-agent/anthropic-api-key"
                    )
                ),
                "JIRA_API_TOKEN": ecs.Secret.from_secrets_manager(
                    secrets.Secret.from_secret_name_v2(
                        self, "JiraToken", "ai-agent/jira-api-token"
                    )
                ),
                "BITBUCKET_APP_PASSWORD": ecs.Secret.from_secrets_manager(
                    secrets.Secret.from_secret_name_v2(
                        self, "BitbucketPassword", "ai-agent/bitbucket-app-password"
                    )
                )
            }
        )
        
        # Mount volume
        container.add_mount_points({
            "source_volume": "workspace",
            "container_path": "/workspace",
            "read_only": False
        })
        
        # Lambda for webhook handling
        webhook_handler = lambda_.Function(
            self, "WebhookHandler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("lambda"),
            handler="webhook_handler.handler",
            vpc=vpc,
            environment={
                "ECS_CLUSTER_NAME": cluster.cluster_name,
                "TASK_DEFINITION_ARN": task_definition.task_definition_arn,
                "SUBNET_IDS": ",".join([subnet.subnet_id for subnet in vpc.private_subnets]),
                "SECURITY_GROUP_ID": vpc.security_groups[0].security_group_id
            },
            timeout=Duration.seconds(30)
        )
        
        # Grant permissions to Lambda
        task_definition.grant_run(webhook_handler)
        cluster.grant(webhook_handler, "ecs:RunTask")
        
        # API Gateway
        api = apigw.RestApi(self, "AIAgentAPI",
            rest_api_name="ai-agent-api",
            description="AI Coding Agent Webhook API"
        )
        
        # Webhook endpoints
        webhooks = api.root.add_resource("webhooks")
        
        # JIRA webhook
        jira_webhook = webhooks.add_resource("jira")
        jira_webhook.add_method("POST", 
            apigw.LambdaIntegration(webhook_handler)
        )
        
        # Bitbucket webhook
        bitbucket_webhook = webhooks.add_resource("bitbucket")
        bitbucket_webhook.add_method("POST",
            apigw.LambdaIntegration(webhook_handler)
        )
```

## Deployment Steps

### 1. Build Docker Image

Create `Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI (adjust based on actual installation method)
RUN curl -o /usr/local/bin/claude https://claude-cli-url/claude \
    && chmod +x /usr/local/bin/claude

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Set environment variables
ENV PYTHONPATH=/app
ENV WORKSPACE_PATH=/workspace

# Run the application
CMD ["python", "-m", "src.main"]
```

### 2. Build and Push to ECR

```bash
# Build Docker image
docker build -t ai-coding-agent .

# Get ECR login token
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Tag image
docker tag ai-coding-agent:latest $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/ai-coding-agent:latest

# Push image
docker push $AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/ai-coding-agent:latest
```

### 3. Deploy Infrastructure

```bash
# Navigate to infrastructure directory
cd infrastructure/cdk

# Install dependencies
pip install -r requirements.txt

# Deploy stacks
cdk deploy AIAgentNetwork
cdk deploy AIAgentStorage
cdk deploy AIAgentStack
```

### 4. Create Secrets in AWS Secrets Manager

```bash
# Create Anthropic API key secret
aws secretsmanager create-secret \
    --name ai-agent/anthropic-api-key \
    --description "Anthropic API key for Claude" \
    --secret-string "your-anthropic-api-key"

# Create JIRA API token
aws secretsmanager create-secret \
    --name ai-agent/jira-api-token \
    --description "JIRA API token" \
    --secret-string "your-jira-api-token"

# Create Bitbucket app password
aws secretsmanager create-secret \
    --name ai-agent/bitbucket-app-password \
    --description "Bitbucket app password" \
    --secret-string "your-bitbucket-app-password"
```

### 5. Configure Webhooks in External Services

#### JIRA Webhook Configuration
1. Go to JIRA Settings → System → Webhooks
2. Click "Create webhook"
3. Set URL: `https://your-api-gateway-url/webhooks/jira`
4. Select events: "Issue assigned"
5. Add JQL filter: `assignee = "ai-agent@company.com"`

#### Bitbucket Webhook Configuration
1. Go to Repository Settings → Webhooks
2. Click "Add webhook"
3. Set URL: `https://your-api-gateway-url/webhooks/bitbucket`
4. Select triggers: "Pull request created", "Pull request updated"

## Configuration

### Environment Variables

Create `.env.production`:

```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012

# Application Configuration
ENVIRONMENT=production
LOG_LEVEL=INFO
API_BASE_URL=https://your-api-gateway-url

# Repository Management
WORKSPACE_PATH=/workspace
MAX_CONCURRENT_WORKFLOWS=10
REPOSITORY_CLEANUP_INTERVAL=24

# Integration Settings
JIRA_SERVER_URL=https://yourcompany.atlassian.net
BITBUCKET_WORKSPACE=yourworkspace
```

### Production Configuration

Create `config/production.yaml`:

```yaml
app:
  environment: production
  log_level: INFO
  
aws:
  region: us-east-1
  
repository_management:
  base_workspace: /workspace
  max_concurrent_repos: 20
  cleanup_interval_hours: 6
  retention_policy:
    max_inactive_hours: 48
    max_total_repositories: 50
    
workflow:
  max_retries: 3
  workflow_timeout_minutes: 30
  concurrent_workflows: 10
  
monitoring:
  enable_metrics: true
  enable_tracing: true
  health_check_interval: 30
```

## Monitoring and Maintenance

### CloudWatch Dashboards

Create CloudWatch dashboard with:
- ECS task metrics (CPU, memory usage)
- Lambda invocation metrics
- API Gateway request metrics
- Custom application metrics

### Alarms

Set up CloudWatch alarms for:
- High error rates
- Task failures
- API Gateway 4xx/5xx errors
- ECS task CPU/memory thresholds

### Logs

Access logs via CloudWatch Logs:
```bash
# View ECS logs
aws logs tail /ecs/ai-agent --follow

# View Lambda logs
aws logs tail /aws/lambda/WebhookHandler --follow
```

### Scaling

Configure auto-scaling for ECS:
```bash
aws application-autoscaling register-scalable-target \
    --service-namespace ecs \
    --resource-id service/ai-agent-cluster/ai-agent-service \
    --scalable-dimension ecs:service:DesiredCount \
    --min-capacity 1 \
    --max-capacity 10

aws application-autoscaling put-scaling-policy \
    --service-namespace ecs \
    --scalable-dimension ecs:service:DesiredCount \
    --resource-id service/ai-agent-cluster/ai-agent-service \
    --policy-name cpu-scaling \
    --policy-type TargetTrackingScaling \
    --target-tracking-scaling-policy-configuration file://scaling-policy.json
```

## Troubleshooting

### Common Issues

1. **ECS Task Fails to Start**
   - Check CloudWatch logs for error messages
   - Verify Docker image exists in ECR
   - Check IAM permissions
   - Verify secrets exist in Secrets Manager

2. **Webhooks Not Triggering**
   - Verify API Gateway endpoint is accessible
   - Check webhook configuration in external services
   - Review Lambda function logs
   - Test with curl: `curl -X POST https://api-url/webhooks/jira -d '{"test": "data"}'`

3. **Repository Access Issues**
   - Verify EFS mount is working
   - Check security group rules
   - Ensure task has proper IAM permissions

4. **High Costs**
   - Review ECS task sizing
   - Check for orphaned resources
   - Monitor data transfer costs
   - Use Fargate Spot for non-critical workloads

### Debug Commands

```bash
# List ECS services
aws ecs list-services --cluster ai-agent-cluster

# Describe service
aws ecs describe-services --cluster ai-agent-cluster --services ai-agent-service

# View task definition
aws ecs describe-task-definition --task-definition ai-agent-task

# Check API Gateway
aws apigateway get-rest-apis

# View recent Lambda invocations
aws logs filter-log-events --log-group-name /aws/lambda/WebhookHandler --start-time $(date -u -d '1 hour ago' +%s)000
```

### Support

For issues:
1. Check CloudWatch logs
2. Review AWS service health
3. Verify all credentials are valid
4. Check network connectivity
5. Review IAM permissions