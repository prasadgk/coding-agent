# Universal AI Coding Agent - Postman Collection

This directory contains a comprehensive Postman collection for testing all API endpoints of the Universal AI Coding Agent.

## Files Included

- `Universal-AI-Coding-Agent.postman_collection.json` - Complete API collection with all endpoints
- `Universal-AI-Coding-Agent.postman_environment.json` - Environment variables for development testing
- `README.md` - This documentation file

## Collection Structure

The collection is organized into logical folders:

### 1. **Health & System**
- Root Endpoint (`GET /`)
- Health Check (`GET /health`)
- Prometheus Metrics (`GET /metrics`)

### 2. **Workflows**
- List All Workflows (`GET /api/v1/workflows`)
- List Workflows with Pagination
- List Completed Workflows (filtered)
- Get Workflow Details (`GET /api/v1/workflows/{id}`)
- Cancel Workflow (`POST /api/v1/workflows/{id}/cancel`)

### 3. **Repositories**
- List Repositories (`GET /api/v1/repositories`)
- Cleanup Repositories (`POST /api/v1/repositories/cleanup`)
- Force Cleanup Repositories (with force parameter)

### 4. **Integrations & Stats**
- List Integrations (`GET /api/v1/integrations`)
- Get Statistics (`GET /api/v1/stats`)

### 5. **Testing**
- Trigger Test Workflow - JIRA
- Trigger Test Workflow - GitHub  
- Trigger Test Workflow - Azure DevOps

### 6. **Webhooks**
Organized by platform with realistic example payloads:

#### JIRA Webhooks
- Issue Assignment (when AI agent is assigned)
- Issue Created

#### GitHub Webhooks
- Issue Assignment (when AI agent is assigned)
- Issue Comment with Mention

#### Bitbucket Webhooks
- PR Comment with AI Agent Mention
- Repository Push Event

#### Azure DevOps Webhooks
- Work Item Assignment (when AI agent is assigned)
- Work Item Created

## Setup Instructions

### 1. Import Collection
1. Open Postman
2. Click "Import" button
3. Select `Universal-AI-Coding-Agent.postman_collection.json`
4. The collection will be imported with all requests

### 2. Import Environment
1. Click the gear icon (⚙️) in the top right
2. Click "Import" 
3. Select `Universal-AI-Coding-Agent.postman_environment.json`
4. Select the imported environment from the dropdown

### 3. Start the Server
Before testing, ensure the Universal AI Coding Agent is running:

```bash
cd /path/to/universal-ai-coding-agent
python -m src.main
```

The server should start on `http://localhost:8000`

### 4. Test Basic Endpoints
Start with the "Health & System" folder to verify connectivity:
1. Run "Root Endpoint" - should return service info
2. Run "Health Check" - should return healthy status
3. Run "Prometheus Metrics" - should return metrics data

## Environment Variables

The environment includes these variables:

| Variable | Default Value | Description |
|----------|---------------|-------------|
| `base_url` | `http://localhost:8000` | Base URL for the API server |
| `api_key` | `your-api-key-here` | API key (disabled by default) |
| `workflow_id` | `workflow-123` | Example workflow ID for testing |
| `test_ticket_id` | `TEST-{{$randomInt}}` | Dynamic test ticket ID |
| `jira_project_key` | `PROJ` | JIRA project key for webhooks |
| `github_repo_name` | `my-awesome-project` | GitHub repository name |
| `github_org_name` | `company` | GitHub organization name |
| `bitbucket_project_key` | `PROJ` | Bitbucket project key |
| `azure_devops_org` | `company` | Azure DevOps organization |
| `azure_devops_project` | `Company Project` | Azure DevOps project name |

## Testing Workflow

### 1. System Health Check
```
GET {{base_url}}/health
```
Verify the system is running and healthy.

### 2. List Current Workflows
```
GET {{base_url}}/api/v1/workflows
```
Should return empty list initially.

### 3. Trigger Test Workflow
```
POST {{base_url}}/api/v1/test/trigger-workflow?ticket_id=TEST-123&platform=jira
```
Creates a test workflow for development purposes.

### 4. Verify Workflow Creation
```
GET {{base_url}}/api/v1/workflows
```
Should now show the triggered workflow.

### 5. Test Webhook Integration
Send webhook payloads to test external integrations:

**JIRA Issue Assignment:**
```
POST {{base_url}}/webhooks/jira
Content-Type: application/json

{webhook payload from collection}
```

**GitHub Issue Assignment:**
```
POST {{base_url}}/webhooks/github
X-GitHub-Event: issues
Content-Type: application/json

{webhook payload from collection}
```

### 6. Monitor Statistics
```
GET {{base_url}}/api/v1/stats
```
View workflow statistics and system metrics.

## Webhook Payload Examples

The collection includes realistic webhook payloads for each platform:

### JIRA Issue Assignment
- Complete issue object with fields, assignee, project info
- Webhook event metadata
- User information

### GitHub Issue Assignment  
- Issue details with labels, assignee, repository info
- Repository clone URLs and metadata
- Sender information

### Bitbucket PR Comment
- Pull request details with source/target branches
- Comment with AI agent mention
- Repository and project information

### Azure DevOps Work Item Assignment
- Work item with complete field set
- Assignment change tracking
- Resource containers and links

## Authentication

Authentication is currently disabled in development mode. When enabled:

1. Update the `api_key` environment variable
2. Ensure the "X-API-Key" header is included in requests
3. Enable the api_key variable in the environment

## Troubleshooting

### Server Not Responding
- Verify the server is running: `curl http://localhost:8000/health`
- Check the server logs for errors
- Ensure no other process is using port 8000

### 500 Internal Server Error
- Check server logs for detailed error information
- Verify all required dependencies are installed
- Ensure the database/storage is accessible

### Webhook Signature Errors
- Webhook signature verification is optional in development
- Headers like `X-Hub-Signature-256` are disabled by default
- Enable signature headers if testing production webhook security

### Environment Variables Not Working
- Ensure the correct environment is selected in Postman
- Check variable names match exactly (case-sensitive)
- Verify variables are enabled in the environment

## Advanced Usage

### Running Collection with Newman
Install Newman CLI to run collections from command line:

```bash
npm install -g newman

# Run entire collection
newman run Universal-AI-Coding-Agent.postman_collection.json \
  -e Universal-AI-Coding-Agent.postman_environment.json

# Run specific folder
newman run Universal-AI-Coding-Agent.postman_collection.json \
  -e Universal-AI-Coding-Agent.postman_environment.json \
  --folder "Health & System"
```

### Integration Testing
Use Postman's test scripts to create automated integration tests:

1. Add test scripts to validate response status codes
2. Verify response schemas match expected format
3. Chain requests using environment variables
4. Create test suites for different scenarios

### Load Testing
Use Postman's performance testing features:

1. Configure multiple iterations
2. Add delays between requests  
3. Monitor response times
4. Test concurrent webhook processing

## Support

For issues with the Postman collection:
1. Check the API documentation: `/docs/api-testing-guide.md`
2. Verify server logs for detailed error information
3. Test individual endpoints to isolate issues
4. Review webhook payload formats against platform documentation

The collection is designed to provide comprehensive coverage of all API endpoints with realistic test data for development and integration testing.