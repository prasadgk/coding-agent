# Webhook API Endpoints Documentation

## Overview

The Universal AI Coding Agent provides webhook endpoints to receive events from various project management and version control platforms. These webhooks trigger the automated code generation workflow when tickets are assigned to the AI agent.

## Base URL

- **Local Development**: `http://localhost:8000`
- **Production**: `https://your-api-gateway-url`

## Webhook Endpoints

### 1. JIRA Webhook

**Endpoint**: `POST /webhooks/jira`

**Purpose**: Receives webhook events from JIRA/Atlassian

**Headers**:
- `Content-Type: application/json`
- `X-Atlassian-Webhook-Signature` (optional): Webhook signature for verification

**Supported Events**:
- `jira:issue_updated` with `issue_event_type_name: issue_assigned`

**Example Request**:
```json
{
  "webhookEvent": "jira:issue_updated",
  "issue_event_type_name": "issue_assigned",
  "issue": {
    "key": "TEST-123",
    "fields": {
      "summary": "Implement feature X",
      "description": "Detailed requirements...",
      "assignee": {
        "accountId": "ai-agent",
        "emailAddress": "ai-agent@company.com"
      }
    }
  }
}
```

**Response**:
```json
{
  "status": "accepted",
  "message": "Webhook received and queued for processing",
  "issue_key": "TEST-123"
}
```

### 2. Bitbucket Webhook

**Endpoint**: `POST /webhooks/bitbucket`

**Purpose**: Receives webhook events from Bitbucket

**Headers**:
- `Content-Type: application/json`
- `X-Hub-Signature` (optional): Webhook signature for verification

**Supported Events**:
- `pullrequest:comment_created` (when comment mentions @ai-agent)
- `repo:push`

**Example Request**:
```json
{
  "eventKey": "pullrequest:comment_created",
  "pullRequest": {
    "id": 42,
    "title": "Feature implementation"
  },
  "comment": {
    "content": {
      "raw": "@ai-agent Please add unit tests"
    }
  }
}
```

### 3. GitHub Webhook

**Endpoint**: `POST /webhooks/github`

**Purpose**: Receives webhook events from GitHub

**Headers**:
- `Content-Type: application/json`
- `X-Hub-Signature-256`: Webhook signature for verification
- `X-GitHub-Event`: Event type

**Supported Events**:
- `issues` (action: assigned)
- `issue_comment` (when comment mentions @ai-coding-agent)

**Example Request**:
```json
{
  "action": "assigned",
  "issue": {
    "number": 123,
    "title": "Add authentication",
    "assignee": {
      "login": "ai-coding-agent"
    }
  },
  "repository": {
    "name": "test-repo",
    "full_name": "org/test-repo"
  }
}
```

### 4. Azure DevOps Webhook

**Endpoint**: `POST /webhooks/azure-devops`

**Purpose**: Receives webhook events from Azure DevOps

**Headers**:
- `Content-Type: application/json`

**Supported Events**:
- `workitem.updated` (when assigned to AI agent)

**Example Request**:
```json
{
  "eventType": "workitem.updated",
  "resource": {
    "id": 12345,
    "fields": {
      "System.AssignedTo": {
        "uniqueName": "ai-agent@company.com"
      },
      "System.Title": "Implement feature Y"
    }
  }
}
```

## REST API Endpoints

### Health & Monitoring

- `GET /` - Root endpoint with API info
- `GET /health` - Health check endpoint
- `GET /metrics` - Prometheus-compatible metrics

### Workflow Management

- `GET /api/v1/workflows` - List all workflows
- `GET /api/v1/workflows/{workflow_id}` - Get workflow details
- `POST /api/v1/workflows/{workflow_id}/cancel` - Cancel a workflow

### Repository Management

- `GET /api/v1/repositories` - List active repository clones
- `POST /api/v1/repositories/cleanup` - Trigger repository cleanup

### System Information

- `GET /api/v1/integrations` - List configured integrations
- `GET /api/v1/stats` - Get agent statistics

### Development/Testing

- `POST /api/v1/test/trigger-workflow` - Trigger test workflow (dev only)

## Authentication

API authentication can be enabled via configuration:

```yaml
enable_auth: true
api_key_header: "X-API-Key"
```

When enabled, include the API key in requests:
```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/api/v1/workflows
```

## Testing Webhooks Locally

### Using curl:
```bash
# Test JIRA webhook
curl -X POST http://localhost:8000/webhooks/jira \
  -H "Content-Type: application/json" \
  -d @examples/jira-webhook-payload.json

# Test Bitbucket webhook
curl -X POST http://localhost:8000/webhooks/bitbucket \
  -H "Content-Type: application/json" \
  -d @examples/bitbucket-webhook-payload.json
```

### Using ngrok for external access:
```bash
# Start ngrok
ngrok http 8000

# Use the ngrok URL in your webhook configuration
# Example: https://abc123.ngrok.io/webhooks/jira
```

## Implementation Files

The webhook API implementation is located in:

- **Main API**: `src/api/main.py` - FastAPI application setup
- **Webhook Routes**: `src/api/webhooks/routes.py` - Webhook endpoint handlers
- **REST Routes**: `src/api/rest/routes.py` - REST API endpoints
- **Examples**: `examples/` - Sample webhook payloads for testing

## Error Handling

All endpoints return appropriate HTTP status codes:

- `200` - Success
- `400` - Bad Request (invalid payload)
- `401` - Unauthorized (missing/invalid API key)
- `404` - Not Found (resource not found)
- `500` - Internal Server Error
- `503` - Service Unavailable (agent not initialized)

Error responses include details:
```json
{
  "error": "Error message",
  "type": "error_type"
}
```