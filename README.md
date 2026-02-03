# Bazis Async Request

[![PyPI version](https://img.shields.io/pypi/v/bazis-async-request.svg)](https://pypi.org/project/bazis-async-request/)
[![Python Versions](https://img.shields.io/pypi/pyversions/bazis-async-request.svg)](https://pypi.org/project/bazis-async-request/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

An extension package for Bazis that provides background processing for "heavy" HTTP requests on top of bazis-async-background.

## Quick Start

```bash
# Install the package
uv add bazis-async-request

# Configure environment variables / settings (.env uses BS_ prefix)
BS_INSTALLED_APPS='["bazis.contrib.async_request", "bazis.contrib.async_background", ...]'
BS_BAZIS_CONFIG_APPS='["bazis.contrib.async_request", "bazis.contrib.async_background", ...]'
BS_KAFKA_TASKS='["bazis.contrib.async_request.tasks"]'
BS_KAFKA_BOOTSTRAP_SERVERS=localhost:9093
BS_KAFKA_TOPIC_ASYNC_BG=my_app_develop_async_request
BS_KAFKA_GROUP_ID=my_app_develop

# Run consumer in Kubernetes
python manage.py kafka_consumer_single

# Run multiple consumers locally
python manage.py kafka_consumer_multiple --consumers-count=5
```

## Table of Contents

- [Description](#description)
- [Requirements](#requirements)
- [Installation](#installation)
- [Architecture](#architecture)
- [Configuration](#configuration)
  - [Environment Variables / Settings](#environment-variables--settings)
  - [Route Registration](#route-registration)
- [Usage](#usage)
  - [Project-Level Middleware](#project-level-middleware)
  - [Running Consumers](#running-consumers)
- [Working with Frontend](#working-with-frontend)
  - [Sending a Request](#sending-a-request)
  - [Getting Result via WebSocket](#getting-result-via-websocket)
  - [Getting Result via API](#getting-result-via-api)
- [Examples](#examples)
- [License](#license)
- [Links](#links)

## Description

**Bazis Async Request** is an extension package for the Bazis framework that allows processing "heavy" requests in the background. The package includes:

- **AsyncRequestMiddleware** — project-level middleware for automatic background processing of any request
- **Kafka Producer** — sending tasks to Kafka queue
- **Kafka Consumer** — processing tasks from the queue
- **Redis storage** — storing task execution results
- **WebSocket notifications** — automatic user notification about task status
- **API endpoint** — retrieving results by task_id

**How it works**: When sending a request with the `X-Async-Request: true` header, the request is not executed immediately but is placed in the Kafka queue. The consumer retrieves the task from the queue, executes it, saves the result in Redis, and sends a notification to the user via WebSocket.

**This package requires the installation of `bazis`, `bazis-users`, `bazis-ws` packages and running Kafka and Redis servers.**

## Requirements

- **Python**: 3.12+
- **bazis**: latest version
- **bazis-async-background**: latest version
- **bazis-ws**: latest version (for WebSocket notifications)
- **PostgreSQL**: 12+
- **Redis**: For storing results and caching
- **Kafka**: For task queue

## Installation

### Using uv (recommended)

```bash
uv add bazis-async-request
```

### Using pip

```bash
pip install bazis-async-request
```

## Running Tests

Run from the project root:

```bash
docker compose -f sample/docker-compose.test.yml up --build --exit-code-from bazis-async-request-pytest --attach bazis-async-request-pytest --attach bazis-async-request-consumer-test
```

This waits for the pytest container to finish and streams logs only from the Python containers, so test completion and output are easy to follow.

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST + X-Async-Request: true
       ▼
┌─────────────────────┐
│   API Endpoint      │
│  (AsyncRequestMiddleware)│
└──────┬──────────────┘
       │ 1. Return task_id (202)
       │ 2. Send to Kafka
       ▼
┌─────────────────────┐
│   Kafka Topic       │
│   (async_request)        │
└──────┬──────────────┘
       │
       │ Consumer polls
       ▼
┌─────────────────────┐
│  Kafka Consumer     │
│  (Background Worker)│
└──────┬──────────────┘
       │ 3. Process request
       │ 4. Save result to Redis
       │ 5. Send WebSocket notification
       ▼
┌─────────────────────┐         ┌──────────────┐
│      Redis          │◄────────┤  WebSocket   │
│   (Results Store)   │         │              │
└──────┬──────────────┘         └───────┬──────┘
       │                                │
       │ 6. GET /async_request_         │ 6. Receive notification
       │    response/{task_id}/         │    {status: "completed"}
       ▼                                ▼
┌─────────────────────┐         ┌──────────────┐
│   API Endpoint      │────────►│   Client     │
│   (Get Result)      │         │              │
└─────────────────────┘         └──────────────┘
```

## Configuration

### Environment Variables / Settings

Add to your `.env` (use `BS_` prefix for Bazis settings) or `settings.py`:

```bash
# Required settings
INSTALLED_APPS='["bazis.contrib.async_request", "bazis.contrib.async_background", ...]'
BAZIS_CONFIG_APPS='["bazis.contrib.async_request", "bazis.contrib.async_background", ...]'
KAFKA_TASKS='["bazis.contrib.async_request.tasks"]'

# Kafka settings
KAFKA_BOOTSTRAP_SERVERS=localhost:9093
KAFKA_TOPIC_ASYNC_BG=my_app_develop_async_request
KAFKA_GROUP_ID=my_app_develop

# Optional settings
KAFKA_CONSUMER_LIFETIME_SEC=900           # Consumer lifetime (15 minutes)
KAFKA_CONSUMER_LIFETIME_JITTER_SEC=180    # Random deviation (3 minutes)
KAFKA_AUTO_OFFSET_RESET=latest
KAFKA_ENABLE_AUTO_COMMIT=true
KAFKA_AUTO_COMMIT_INTERVAL_MS=5000
KAFKA_LOG_LEVEL=INFO
```

When placing these in a `.env` file, prefix them with `BS_`, for example:

```bash
BS_INSTALLED_APPS='["bazis.contrib.async_request", "bazis.contrib.async_background", ...]'
BS_BAZIS_CONFIG_APPS='["bazis.contrib.async_request", "bazis.contrib.async_background", ...]'
BS_KAFKA_TASKS='["bazis.contrib.async_request.tasks"]'
```

**Parameters**:

- `KAFKA_TASKS` — dotted module paths imported by the consumer to register tasks
- `KAFKA_BOOTSTRAP_SERVERS` — Kafka broker address
- `KAFKA_TOPIC_ASYNC_BG` — topic for async tasks
- `KAFKA_GROUP_ID` — consumer group
- `KAFKA_CONSUMER_LIFETIME_SEC` — consumer working time before restart
- `KAFKA_CONSUMER_LIFETIME_JITTER_SEC` — random deviation to avoid simultaneous restart
- `KAFKA_AUTO_OFFSET_RESET` — Kafka auto offset reset policy
- `KAFKA_ENABLE_AUTO_COMMIT` — Kafka auto-commit toggle
- `KAFKA_AUTO_COMMIT_INTERVAL_MS` — auto-commit interval in ms
- `KAFKA_LOG_LEVEL` — log level for consumers

### Route Registration

Add the route for getting results to your `router.py`:

```python
from bazis.core.routing import BazisRouter

router = BazisRouter(prefix='/api/v1')

# Register background task results route
router.register('bazis.contrib.async_background.router')
```

This adds the endpoint: `GET /api/v1/async_background_response/{task_id}/`

## Usage

### Project-Level Middleware

AsyncRequestMiddleware is registered automatically when `bazis.contrib.async_request` is loaded.
Any request can be moved to background using the `X-Async-Request: true` header.

**Location**: `bazis.contrib.async_request.middleware.AsyncRequestMiddleware`

### Endpoint-Only Async Request (Dependency)

Use a dependency to mark specific endpoints as async-only. Such routes will return `409 Conflict`
unless the request includes `X-Async-Request` (or an internal background call with
`X-Async-Request-Internal: true`).

**Location**: `bazis.contrib.async_request.dependencies.require_async`

#### Attach to a Single Route

```python
from fastapi import Depends
from bazis.contrib.async_request.dependencies import require_async

@router.post(
    "/reports/generate/",
    dependencies=[Depends(require_async)],
)
async def generate_report(...):
    ...
```

#### Attach via Function Signature

```python
from fastapi import Depends
from bazis.contrib.async_request.dependencies import require_async

@router.post("/reports/generate/")
async def generate_report(
    ...,
    _async_request: None = Depends(require_async),
):
    ...
```
### Running Consumers

#### For Kubernetes (one consumer per pod)

```bash
python manage.py kafka_consumer_single
```

Runs one consumer that processes tasks from Kafka. Suitable for horizontal scaling in Kubernetes.

#### For Local Development (multiple consumers)

```bash
python manage.py kafka_consumer_multiple --consumers-count=5
```

Runs 5 consumers in separate processes. Suitable for local development or deployment without orchestration.

**Parameters**:

- `--consumers-count` — number of consumers to run (default: 1)

## Working with Frontend

### Sending a Request

Add the `X-Async-Request: true` header to your request:

```bash
curl -X POST \
  http://localhost/api/v1/orders/order/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/vnd.api+json" \
  -H "X-Async-Request: true" \
  -d '{
    "data": {
      "type": "myapp.order",
      "attributes": {
        "description": "New Order",
        "amount": 1000
      }
    }
  }'
```

**Response** (status 202 Accepted):

```json
{
  "data": null,
  "meta": {
    "async_request_id": "371564b0-29a5-457a-aabb-9c43661148a7"
  }
}
```

If the request has no `Authorization` header, pass a channel name directly:

```bash
X-Async-Request: <channel_name>
```

Save the `async_request_id` — this is the task identifier for retrieving the result.

### Getting Result via WebSocket

After sending the task, connect to WebSocket (requires `bazis-ws` package) and wait for notifications:

```javascript
// Connect to WebSocket (see bazis-ws documentation)
const ws = new WebSocket(`ws://api.example.com/ws?token=${jwtToken}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'data') {
    const message = JSON.parse(data.data);
    
    if (message.action === 'async_bg') {
      console.log('Task ID:', message.task_id);
      console.log('Status:', message.status);
      
      if (message.status === 'completed') {
        // Task completed, get result
        fetchResult(message.task_id);
      } else if (message.status === 'failed') {
        // Task failed
        console.error('Task failed');
      }
    }
  }
};
```

**WebSocket Notification Format**:

```json
{
  "type": "data",
  "data": "{\"task_id\": \"371564b0-29a5-457a-aabb-9c43661148a7\", \"status\": \"completed\", \"action\": \"async_request\"}"
}
```

**Task Statuses**:

- `completed` — task successfully completed
- `failed` — task failed with error

### Getting Result via API

After receiving notification about task completion, request the result:

```bash
GET /api/v1/async_background_response/{task_id}/
Authorization: Bearer YOUR_JWT_TOKEN
```

**Example Request**:

```bash
curl -X GET \
  http://localhost/api/v1/async_background_response/371564b0-29a5-457a-aabb-9c43661148a7/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Success Response** (status 200):

```json
{
  "task_id": "371564b0-29a5-457a-aabb-9c43661148a7",
  "status": 200,
  "endpoint": "/api/v1/orders/order/e7cc4c8c-3ed1-4576-96ad-b3fd7c0b2a5a/",
  "headers": [
    ["content-length", "217"],
    ["content-type", "application/vnd.api+json"]
  ],
  "response": {
    "data": {
      "type": "myapp.order",
      "id": "e7cc4c8c-3ed1-4576-96ad-b3fd7c0b2a5a",
      "attributes": {
        "description": "New Order",
        "amount": 1000,
        "status": "draft"
      }
    }
  }
}
```

**Error Response** (status 403):

```json
{
  "task_id": "371564b0-29a5-457a-aabb-9c43661148a7",
  "status": 403,
  "endpoint": "/api/v1/orders/order/e7cc4c8c-3ed1-4576-96ad-b3fd7c0b2a5a/",
  "headers": [
    ["content-length", "4496"],
    ["content-type", "application/json"]
  ],
  "response": {
    "errors": [
      {
        "detail": "Permission denied: check access",
        "status": 403
      }
    ]
  }
}
```

## Examples

### Complete Example with Frontend

**Backend (models.py)**:

```python
from bazis.core.models_abstract import DtMixin, UuidMixin, JsonApiMixin
from django.db import models

class Report(DtMixin, UuidMixin, JsonApiMixin):
    """Report whose generation takes time"""
    title = models.CharField('Title', max_length=255)
    date_from = models.DateField('Date From')
    date_to = models.DateField('Date To')
    status = models.CharField('Status', max_length=50, default='pending')
    result_data = models.JSONField('Report Data', null=True, blank=True)
    
    class Meta:
        verbose_name = 'Report'
        verbose_name_plural = 'Reports'
```

**Frontend (JavaScript)**:

```javascript
class AsyncReportClient {
  constructor(apiUrl, wsUrl, token) {
    this.apiUrl = apiUrl;
    this.token = token;
    this.ws = null;
    this.pendingTasks = new Map();
    
    // Connect to WebSocket
    this.connectWebSocket(wsUrl);
  }

  connectWebSocket(wsUrl) {
    this.ws = new WebSocket(`${wsUrl}?token=${this.token}`);
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'data') {
        const message = JSON.parse(data.data);
        
        if (message.action === 'async_bg') {
          this.handleTaskUpdate(message.task_id, message.status);
        }
      }
    };
  }

  async createReport(title, dateFrom, dateTo) {
    // Send request to create report
    const response = await fetch(`${this.apiUrl}/reports/report/`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/vnd.api+json',
        'X-Async-Request': 'true'
      },
      body: JSON.stringify({
        data: {
          type: 'myapp.report',
          attributes: {
            title: title,
            date_from: dateFrom,
            date_to: dateTo
          }
        }
      })
    });

    const result = await response.json();
    const taskId = result.meta.async_request_id;
    
    // Save promise to wait for result
    return new Promise((resolve, reject) => {
      this.pendingTasks.set(taskId, { resolve, reject });
    });
  }

  async handleTaskUpdate(taskId, status) {
    if (!this.pendingTasks.has(taskId)) return;

    const { resolve, reject } = this.pendingTasks.get(taskId);

    if (status === 'completed') {
      // Get result
      const result = await this.getResult(taskId);
      this.pendingTasks.delete(taskId);
      resolve(result);
    } else if (status === 'failed') {
      const error = await this.getResult(taskId);
      this.pendingTasks.delete(taskId);
      reject(error);
    }
  }

  async getResult(taskId) {
    const response = await fetch(
      `${this.apiUrl}/async_background_response/${taskId}/`,
      {
        headers: {
          'Authorization': `Bearer ${this.token}`
        }
      }
    );
    return await response.json();
  }
}

// Usage
const client = new AsyncReportClient(
  'http://api.example.com/api/v1',
  'ws://api.example.com/ws',
  jwtToken
);

// Create report
client.createReport('Monthly Report', '2024-01-01', '2024-01-31')
  .then(result => {
    console.log('Report created:', result);
    // Display result to user
  })
  .catch(error => {
    console.error('Report generation failed:', error);
  });
```

### Example for Custom Endpoint

**Backend**:

```python
from fastapi import Request, Depends
from django.contrib.auth import get_user_model
from bazis.core.routing import BazisRouter
from bazis.contrib.users.service import get_user_from_token
import time

User = get_user_model()
router = BazisRouter(tags=["Analytics"])

@router.post('/generate-analytics/', response_model=dict)
async def generate_analytics(
    report_type: str,
    date_from: str,
    date_to: str,
    request: Request,
    user: User = Depends(get_user_from_token)
):
    """
    Generate analytics report (long operation)
    """
    # Simulate long processing
    time.sleep(10)
    
    # Generate report
    analytics_data = {
        'report_type': report_type,
        'period': f'{date_from} - {date_to}',
        'total_orders': 1250,
        'revenue': 125000.50,
        'average_order': 100.00
    }
    
    return {
        'status': 'success',
        'data': analytics_data
    }
```

**Frontend**:

```bash
# Synchronous request (will wait 10 seconds)
POST /api/v1/generate-analytics/
Content-Type: application/json

{
  "report_type": "sales",
  "date_from": "2024-01-01",
  "date_to": "2024-01-31"
}

# Asynchronous request (returns task_id immediately)
POST /api/v1/generate-analytics/
Content-Type: application/json
X-Async-Request: true

{
  "report_type": "sales",
  "date_from": "2024-01-01",
  "date_to": "2024-01-31"
}
```

### Error Handling Example

```python
from bazis.core.routes_abstract.jsonapi import JsonapiRouteBase
from django.apps import apps

class OrderRouteSet(JsonapiRouteBase):
    model = apps.get_model("myapp", "Order")
    
    def hook_before_update(self, item):
        """Check before update"""
        if item.status == 'draft' and not self.inject.user.is_staff:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail="Permission denied: check access"
            )
        super().hook_before_update(item)
```

**Result with async processing**:

```json
{
  "task_id": "371564b0-29a5-457a-aabb-9c43661148a7",
  "status": 403,
  "response": {
    "errors": [
      {
        "detail": "Permission denied: check access",
        "status": 403
      }
    ]
  }
}
```

## License

Apache License 2.0

See [LICENSE](LICENSE) file for details.

## Links

- [Bazis Documentation](https://github.com/ecofuture-tech/bazis) — main repository
- [Bazis WS](https://github.com/ecofuture-tech/bazis-ws) — WebSocket package
- [Bazis Async Background Repository](https://github.com/ecofuture-tech/bazis-async-background) — core background framework
- [Bazis Async Request Repository](https://github.com/ecofuture-tech/bazis-async-request) — package repository
- [Issue Tracker](https://github.com/ecofuture-tech/bazis-async-request/issues) — report bugs or request features
- [Apache Kafka](https://kafka.apache.org/) — Kafka documentation

## Support

If you have questions or issues:
- Review the [Bazis documentation](https://github.com/ecofuture-tech/bazis)
- Search [existing issues](https://github.com/ecofuture-tech/bazis-async-request/issues)
- Create a [new issue](https://github.com/ecofuture-tech/bazis-async-request/issues/new) with detailed information

---

Made with ❤️ by the Bazis team
