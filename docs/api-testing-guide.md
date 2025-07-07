# Universal AI Coding Agent - API Testing Guide

## Base Information
- **Base URL**: `http://localhost:8000`
- **API Version**: v1
- **API Documentation**: 
  - Swagger UI: `http://localhost:8000/docs`
  - ReDoc: `http://localhost:8000/redoc`

## Authentication
- Authentication is configurable (currently disabled in development)
- When enabled, include API key in header: `X-API-Key: your-api-key`

---

## API Endpoints

### 1. Root & Health Endpoints

#### GET `/` - Root Endpoint
**Description**: Basic service information

**Postman Setup**:
```
Method: GET
URL: http://localhost:8000/
Headers: (none required)
```

**Expected Response**:
```json
{
  "name": "Universal AI Coding Agent",
  "version": "0.1.0",
  "status": "running",
  "timestamp": "2025-06-12T09:44:03.681433Z"
}
```

#### GET `/health` - Health Check
**Description**: Service health status and component status

**Postman Setup**:
```
Method: GET
URL: http://localhost:8000/health
Headers: (none required)
```

**Expected Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-06-12T09:44:03.681433Z",
  "version": "0.1.0",
  "environment": "development",
  "agent": {
    "status": "initialized",
    "active_workflows": 0
  },
  "repository_manager": {
    "status": "healthy",
    "active_repositories": 0
  }
}
```

#### GET `/metrics` - Prometheus Metrics
**Description**: Prometheus-compatible metrics

**Postman Setup**:
```
Method: GET
URL: http://localhost:8000/metrics
Headers: (none required)
```

**Expected Response**:
```
# HELP ai_agent_active_workflows Number of active workflows
# TYPE ai_agent_active_workflows gauge
ai_agent_active_workflows 0

# HELP ai_agent_completed_workflows Number of completed workflows
# TYPE ai_agent_completed_workflows counter
ai_agent_completed_workflows 0

# HELP ai_agent_active_repositories Number of active repository clones
# TYPE ai_agent_active_repositories gauge
ai_agent_active_repositories 0
```

---

### 2. REST API Endpoints (Prefix: `/api/v1`)

#### GET `/api/v1/workflows` - List Workflows
**Description**: List workflows with optional filtering and pagination

**Postman Setup**:
```
Method: GET
URL: http://localhost:8000/api/v1/workflows
Query Parameters:
  - status: [optional] pending|running|completed|failed|cancelled
  - limit: [optional] 1-100 (default: 50)
  - offset: [optional] ≥0 (default: 0)
```

**Example URLs**:
- All workflows: `http://localhost:8000/api/v1/workflows`
- Completed workflows: `http://localhost:8000/api/v1/workflows?status=completed`
- Paginated: `http://localhost:8000/api/v1/workflows?limit=10&offset=20`

**Expected Response**:
```json
{
  "workflows": [
    {
      "id": "workflow-123",
      "ticket_id": "PROJ-456",
      "state": "completed",
      "started_at": "2025-06-12T09:30:00Z",
      "completed_at": "2025-06-12T09:45:00Z",
      "error": null
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

#### GET `/api/v1/workflows/{workflow_id}` - Get Workflow Details
**Description**: Get detailed information about a specific workflow

**Postman Setup**:
```
Method: GET
URL: http://localhost:8000/api/v1/workflows/workflow-123
Headers: (none required)
```

**Expected Response**:
```json
{
  "id": "workflow-123",
  "ticket_id": "PROJ-456",
  "state": "completed",
  "started_at": "2025-06-12T09:30:00Z",
  "completed_at": "2025-06-12T09:45:00Z",
  "error": null,
  "steps": [
    {
      "name": "fetch_ticket",
      "status": "completed",
      "started_at": "2025-06-12T09:30:00Z",
      "completed_at": "2025-06-12T09:31:00Z",
      "error": null,
      "retries": 0
    }
  ],
  "context": {
    "repository_url": "https://github.com/user/repo",
    "branch_name": "feature/PROJ-456",
    "pull_request_url": "https://github.com/user/repo/pull/123"
  }
}
```

#### POST `/api/v1/workflows/{workflow_id}/cancel` - Cancel Workflow
**Description**: Cancel a running workflow

**Postman Setup**:
```
Method: POST
URL: http://localhost:8000/api/v1/workflows/workflow-123/cancel
Headers: Content-Type: application/json
Body: (empty)
```

**Expected Response**:
```json
{
  "id": "workflow-123",
  "status": "cancelled",
  "message": "Workflow cancelled successfully"
}
```

#### GET `/api/v1/repositories` - List Repositories
**Description**: List active repository clones

**Postman Setup**:
```
Method: GET
URL: http://localhost:8000/api/v1/repositories
Headers: (none required)
```

**Expected Response**:
```json
{
  "repositories": [
    {
      "url": "https://github.com/user/repo",
      "path": "/tmp/ai-agent-repos/repo-123",
      "last_used": "2025-06-12T09:44:00Z",
      "created_at": "2025-06-12T09:30:00Z",
      "size_bytes": 1048576,
      "active_branches": ["main", "feature/PROJ-456"],
      "lock_status": "unlocked"
    }
  ],
  "total": 1,
  "disk_usage_gb": 0.001
}
```

#### POST `/api/v1/repositories/cleanup` - Cleanup Repositories
**Description**: Trigger repository cleanup

**Postman Setup**:
```
Method: POST
URL: http://localhost:8000/api/v1/repositories/cleanup
Query Parameters:
  - force: [optional] true|false (default: false)
Headers: Content-Type: application/json
Body: (empty)
```

**Expected Response**:
```json
{
  "status": "completed",
  "repositories_cleaned": 3,
  "cleaned_repositories": [
    "/tmp/ai-agent-repos/old-repo-1",
    "/tmp/ai-agent-repos/old-repo-2",
    "/tmp/ai-agent-repos/old-repo-3"
  ]
}
```

#### GET `/api/v1/integrations` - List Integrations
**Description**: List configured integrations

**Postman Setup**:
```
Method: GET
URL: http://localhost:8000/api/v1/integrations
Headers: (none required)
```

**Expected Response**:
```json
{
  "project_management": [
    {
      "name": "jira",
      "enabled": true,
      "type": "JiraIntegration"
    }
  ],
  "version_control": [
    {
      "name": "bitbucket",
      "enabled": true,
      "type": "BitbucketIntegration"
    }
  ],
  "communication": [],
  "cicd": []
}
```

#### GET `/api/v1/stats` - Get Statistics
**Description**: Get agent statistics and metrics

**Postman Setup**:
```
Method: GET
URL: http://localhost:8000/api/v1/stats
Headers: (none required)
```

**Expected Response**:
```json
{
  "workflows": {
    "total": 10,
    "active": 2,
    "completed": 7,
    "failed": 1,
    "cancelled": 0,
    "success_rate": 0.875,
    "average_duration_seconds": 450.5
  },
  "repositories": {
    "active": 3,
    "total_disk_usage_gb": 0.25
  },
  "uptime": {
    "started_at": "2025-06-12T09:00:00Z",
    "environment": "development"
  }
}
```

#### POST `/api/v1/test/trigger-workflow` - Trigger Test Workflow (Development Only)
**Description**: Trigger a test workflow for development purposes

**Postman Setup**:
```
Method: POST
URL: http://localhost:8000/api/v1/test/trigger-workflow
Query Parameters:
  - ticket_id: [required] e.g., "TEST-123"
  - platform: [optional] jira|github|azure_devops (default: jira)
Headers: Content-Type: application/json
Body: (empty)
```

**Example URL**: `http://localhost:8000/api/v1/test/trigger-workflow?ticket_id=TEST-123&platform=jira`

**Expected Response**:
```json
{
  "status": "triggered",
  "ticket_id": "TEST-123",
  "platform": "jira",
  "message": "Test workflow triggered successfully"
}
```

---

### 3. Webhook Endpoints (Prefix: `/webhooks`)

#### POST `/webhooks/jira` - JIRA Webhook
**Description**: Handle JIRA webhook events

**Postman Setup**:
```
Method: POST
URL: http://localhost:8000/webhooks/jira
Headers: 
  - Content-Type: application/json
  - X-Atlassian-Webhook-Signature: [optional] webhook signature
Body: (JIRA webhook payload)
```

**Example Body** (JIRA Issue Assignment):
```json
{
  "webhookEvent": "jira:issue_updated",
  "issue_event_type_name": "issue_assigned",
  "issue": {
    "key": "PROJ-123",
    "fields": {
      "summary": "Fix user login bug",
      "description": "Users cannot log in with email",
      "assignee": {
        "accountId": "ai-agent",
        "emailAddress": "ai-agent@company.com"
      }
    }
  }
}
```

**Expected Response**:
```json
{
  "status": "accepted",
  "message": "Webhook received and queued for processing",
  "issue_key": "PROJ-123"
}
```

#### POST `/webhooks/github` - GitHub Webhook
**Description**: Handle GitHub webhook events

**Postman Setup**:
```
Method: POST
URL: http://localhost:8000/webhooks/github
Headers:
  - Content-Type: application/json
  - X-GitHub-Event: issues
  - X-Hub-Signature-256: [optional] webhook signature
Body: (GitHub webhook payload)
```

**Example Body** (Issue Assignment):
```json
{
  "action": "assigned",
  "issue": {
    "number": 123,
    "title": "Fix user login bug",
    "body": "Users cannot log in with email",
    "assignee": {
      "login": "ai-coding-agent"
    }
  },
  "repository": {
    "name": "my-project",
    "full_name": "user/my-project",
    "clone_url": "https://github.com/user/my-project.git"
  }
}
```

**Expected Response**:
```json
{
  "status": "accepted",
  "message": "Webhook received",
  "event": "issues"
}
```

#### POST `/webhooks/bitbucket` - Bitbucket Webhook
**Description**: Handle Bitbucket webhook events

**Postman Setup**:
```
Method: POST
URL: http://localhost:8000/webhooks/bitbucket
Headers:
  - Content-Type: application/json
  - X-Hub-Signature: [optional] webhook signature
Body: (Bitbucket webhook payload)
```

**Example Body** (PR Comment):
```json
{
  "eventKey": "pullrequest:comment_created",
  "comment": {
    "text": "@ai-agent please review this code",
    "author": {
      "username": "developer"
    }
  },
  "pullRequest": {
    "id": 42,
    "title": "Feature implementation"
  }
}
```

#### POST `/webhooks/azure-devops` - Azure DevOps Webhook
**Description**: Handle Azure DevOps webhook events

**Postman Setup**:
```
Method: POST
URL: http://localhost:8000/webhooks/azure-devops
Headers: Content-Type: application/json
Body: (Azure DevOps webhook payload)
```

**Example Body** (Work Item Assignment):
```json
{
  "eventType": "workitem.updated",
  "resource": {
    "id": 123,
    "fields": {
      "System.Title": "Fix user login bug",
      "System.AssignedTo": {
        "uniqueName": "ai-agent@company.com"
      }
    }
  }
}
```

---

## Postman Collection Setup

### Environment Variables
Create a Postman environment with these variables:
```
base_url: http://localhost:8000
api_key: your-api-key-here (if authentication enabled)
```

### Common Headers (if auth enabled)
```
X-API-Key: {{api_key}}
Content-Type: application/json
```

### Testing Workflow
1. **Start with health check**: Verify service is running
2. **Test basic endpoints**: Root, health, metrics
3. **Test workflow endpoints**: List workflows, trigger test workflow
4. **Test repository endpoints**: List repositories, cleanup
5. **Test webhook endpoints**: Send sample webhook payloads
6. **Monitor logs**: Check application logs for processing status

### Error Responses
All endpoints may return these error responses:
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Missing or invalid API key (if auth enabled)
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Service not ready

**Example Error Response**:
```json
{
  "detail": "Agent not initialized",
  "error": "Service temporarily unavailable",
  "type": "service_error"
}
```

This documentation provides complete coverage of all available API endpoints with examples for testing in Postman or any other REST client.