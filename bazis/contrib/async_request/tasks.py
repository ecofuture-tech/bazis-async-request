# Copyright 2026 EcoFuture Technology Services LLC and contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import json
import logging

from django.conf import settings

from bazis.contrib.async_background.broker import get_broker_for_consumer, subscriber_kwargs
from bazis.contrib.async_background.schemas import KafkaTask, TaskStatus
from bazis.contrib.async_background.utils import set_and_publish_status_async
from bazis.contrib.async_request.schemas import AsyncRequestPayload
from bazis.contrib.async_request.utils import SCOPE_INTERNAL_KEY


logger = logging.getLogger(__name__)


#: the headers of the original request that do not apply to the replayed request
SKIPPED_HEADERS = {"content-length", "transfer-encoding", "x-async-background"}


@get_broker_for_consumer().subscriber(settings.KAFKA_TOPIC_ASYNC_BG, **subscriber_kwargs())
async def consumer_async_requests(task: KafkaTask[AsyncRequestPayload]):
    """Executes a background HTTP request from Kafka."""

    await set_and_publish_status_async(
        task_id=task.task_id,
        channel_name=task.channel_name,
        status=TaskStatus.PROCESSING,
    )

    try:
        response = await execute_internal_request(task)
    except Exception:
        logger.exception("Failed to process task_id=%s", task.task_id)
        await set_and_publish_status_async(
            task_id=task.task_id,
            channel_name=task.channel_name,
            status=TaskStatus.FAILED,
            response={"error": "The request failed"},
        )
    else:
        logger.info("Processed task_id=%s with status=%s.", task.task_id, response.get("status"))
        await set_and_publish_status_async(
            task_id=task.task_id,
            channel_name=task.channel_name,
            status=TaskStatus.COMPLETED,
            response=response,
        )


async def execute_internal_request(task: KafkaTask[AsyncRequestPayload]) -> dict:
    """Executes an internal HTTP request and returns the result."""
    request = task.payload

    body = json.dumps(request.body).encode("utf-8") if request.body is not None else b""

    headers = []
    for key, value in request.headers:
        key_str = key.decode("latin-1") if isinstance(key, bytes) else str(key)
        if key_str.lower() in SKIPPED_HEADERS:
            continue
        value_bytes = value if isinstance(value, bytes) else str(value).encode("latin-1")
        headers.append((key_str.lower().encode("latin-1"), value_bytes))
    headers.append((b"content-length", str(len(body)).encode()))

    scope = {
        "type": request.type,
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": request.http_version,
        "method": request.method,
        "scheme": request.scheme,
        "root_path": request.root_path,
        # the stored path is already decoded (requests stored by 2.2 too)
        "path": request.path,
        "raw_path": (
            request.raw_path.encode("latin-1")
            if request.raw_path is not None
            else request.path.encode("utf-8")
        ),
        "query_string": request.query_string.encode(),
        "headers": headers,
        "client": tuple(request.request_client) if request.request_client else None,
        "server": None,
        "state": {},
        # the request is executed by the consumer: the clients cannot set a scope key, so
        # unlike a header it cannot be forged
        SCOPE_INTERNAL_KEY: True,
    }

    result = {
        "task_id": task.task_id,
        "endpoint": request.path,
        "status": None,
        "headers": [],
        "response": None,
    }

    body_sent = False

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        # the client of the replayed request never disconnects
        await asyncio.Event().wait()

    async def send(message):
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
            decoded_headers = []
            for key, value in message.get("headers", []):
                key_str = key.decode("latin-1") if isinstance(key, (bytes, bytearray)) else str(key)
                value_str = (
                    value.decode("latin-1") if isinstance(value, (bytes, bytearray)) else str(value)
                )
                decoded_headers.append([key_str, value_str])
            result["headers"] = decoded_headers
        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            try:
                result["response"] = json.loads(body)
            except Exception:
                result["response"] = body.decode("utf-8", errors="replace")

    from bazis.core.app import app
    await app(scope, receive, send)
    return result