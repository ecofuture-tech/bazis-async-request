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

import json
import logging
from urllib.parse import urlparse

from django.conf import settings

from bazis.contrib.async_background.broker import get_broker_for_consumer
from bazis.contrib.async_background.schemas import KafkaTask, TaskStatus
from bazis.contrib.async_background.utils import set_and_publish_status_async
from bazis.contrib.async_request.schemas import AsyncRequestPayload


logger = logging.getLogger(__name__)


_subscriber_kwargs: dict[str, object] = {
    "auto_offset_reset": settings.KAFKA_AUTO_OFFSET_RESET,
    "auto_commit": settings.KAFKA_ENABLE_AUTO_COMMIT,
    "auto_commit_interval_ms": settings.KAFKA_AUTO_COMMIT_INTERVAL_MS,
}
if settings.KAFKA_GROUP_ID:
    _subscriber_kwargs["group_id"] = settings.KAFKA_GROUP_ID


@get_broker_for_consumer().subscriber(settings.KAFKA_TOPIC_ASYNC_BG, **_subscriber_kwargs)
async def consumer_async_requests(task: KafkaTask[AsyncRequestPayload]):
    """Executes a background HTTP request from Kafka."""

    await set_and_publish_status_async(
        task_id=task.task_id,
        channel_name=task.channel_name,
        status=TaskStatus.PROCESSING,
    )

    try:
        response = await execute_internal_request(task)
    except Exception as err:
        logger.exception("Failed to process task_id=%s", task.task_id)
        await set_and_publish_status_async(
            task_id=task.task_id,
            channel_name=task.channel_name,
            status=TaskStatus.FAILED,
            response={"error": str(err)},
        )
        raise

    await set_and_publish_status_async(
        task_id=task.task_id,
        channel_name=task.channel_name,
        status=TaskStatus.COMPLETED,
        response=response,
    )

    logger.info(
        "Processed task_id=%s with status=%s.",
        task.task_id,
        response.get("status"),
    )


async def execute_internal_request(task: KafkaTask[AsyncRequestPayload]) -> dict:
    """Executes an internal HTTP request and returns the result."""
    request = task.payload

    url = urlparse(request.path)

    headers = []
    for key, value in request.headers:
        key_bytes = key if isinstance(key, bytes) else str(key).encode("utf-8")
        value_bytes = value if isinstance(value, bytes) else str(value).encode("utf-8")
        headers.append((key_bytes, value_bytes))

    scope = {
        "type": request.type,
        "http_version": request.http_version,
        "method": request.method,
        "scheme": request.scheme,
        "path": url.path,
        "raw_path": url.path.encode("utf-8"),
        "query_string": request.query_string.encode(),
        "headers": headers,
        "client": request.request_client,
    }

    result = {
        "task_id": task.task_id,
        "endpoint": request.path,
        "status": None,
        "headers": [],
        "response": None,
    }

    async def receive():
        return {
            "type": "http.request",
            "body": json.dumps(request.body).encode("utf-8"),
        }

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