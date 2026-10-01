# bazis-async-request — guide for AI agents

Runs any HTTP request of a Bazis API in the background: a request with the header
`X-Async-Background` is queued in Kafka (bazis-async-background) and answered 202; a
consumer replays it through the ASGI application and stores the response for
`GET /async_background_response/{task_id}/`. Use it for slow endpoints and bulk changes.

## Setup

```bash
BS_INSTALLED_APPS='[..., "bazis.contrib.async_request", "bazis.contrib.async_background"]'
BS_KAFKA_TASKS='["bazis.contrib.async_request.tasks"]'   # the consumer of the requests
BS_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
BS_KAFKA_TOPIC_ASYNC_BG=myproject_async_request
BS_KAFKA_GROUP_ID=myproject
```

```python
# the main module of the application (as sample/sample/main.py)
from bazis.contrib.async_request.middleware import AsyncRequestMiddleware
from bazis.core.app import app

app.add_middleware(AsyncRequestMiddleware)      # not added automatically

# the root router
router.register('bazis.contrib.async_background.router')    # async_request.E001
```

- Services and consumers as in bazis-async-background: Kafka, Redis, and
  `python manage.py kafka_consumer_single` (or `kafka_consumer_multiple`) with the same
  settings and database as the API.
- Without Kafka settings the middleware executes these requests synchronously and only
  logs a warning (`async_request.W001`).

## Client

- Send the request as usual plus `X-Async-Background: true` (the header's presence is
  enough) and `Authorization: Bearer <token>`: a session JWT, or an anonymous token of
  bazis-ws (16–128 characters `A-Z a-z 0-9 _ -`). Without a valid token: 401. The request
  is replayed with the same header: routes that read the user (bazis-users, permit, author)
  answer 401 to an anonymous token, so use it only for routes that do not.
- Answer: 202 `{"data": null, "meta": {"async_request_id": <id>, "async_background_id": <id>}}`
  (the same task id). Status updates arrive on the WebSocket channel of the token.
- Result: `GET .../async_background_response/{task_id}/` with the same token returns
  `{"task_id", "endpoint", "status", "headers", "response"}` of the replayed request
  (an HTTP error is a `completed` task with its status); `{"status": "not ready"}` before.

## Endpoints only for background requests

```python
from fastapi import Depends
from bazis.contrib.async_request.utils import require_async

@router.post('/reports/generate/', dependencies=[Depends(require_async)])
async def generate_report(...): ...

class ShopRouteSet(JsonapiRouteBase):
    @inject_make(CrudApiAction.UPDATE)          # bazis.core.routes_abstract.initial
    class InjectRequireAsync:
        async_request: None = Depends(require_async)   # the annotation is required
```

A direct request to such an endpoint is 409.

## Rules

- Recognize the requests of the consumer only with `is_internal_request(scope)`
  (`SCOPE_INTERNAL_KEY` in the ASGI scope, which clients cannot set). Never trust a
  header: `X-Async-Background-Internal` is ignored.
- Only JSON bodies (an object or a list of objects) are queued: another body (multipart,
  form, binary) is replayed as `{}`.
- The queued request keeps all headers, `Authorization` included, in the Kafka topic; it
  runs with the client's token, so the token must still be valid when the consumer runs it.
- Requests with the same `data.id` in the body go to the same Kafka partition.
- WebSocket requests and the results route are never queued.
