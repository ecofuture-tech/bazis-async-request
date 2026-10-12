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

from __future__ import annotations

import logging

from django.conf import settings

from fastapi import Request

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from bazis.contrib.async_background.producer import enqueue_task_async
from bazis.contrib.async_background.utils import ChannelNameError, resolve_channel_name_async

from .utils import build_request_payload, is_internal_request, results_route_prefix


logger = logging.getLogger(__name__)


def partition_marker(body) -> str | None:
    """
    The id of the JSON:API resource of the body: the requests of one resource are kept in
    one Kafka partition, in order.
    """
    data = body.get("data") if isinstance(body, dict) else None
    item_id = data.get("id") if isinstance(data, dict) else None
    return str(item_id) if item_id is not None else None


class AsyncRequestMiddleware:
    def __init__(self, app):
        self.app = app
        #: the prefix of the route of the results, resolved at the first request (the routes
        #: are registered after the middleware)
        self._results_prefix: str | None = None

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        if self._results_prefix is None:
            self._results_prefix = results_route_prefix(scope.get("app") or self.app)
        if scope.get("path", "").startswith(self._results_prefix):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if is_internal_request(scope) or "X-Async-Background" not in headers:
            await self.app(scope, receive, send)
            return

        if not settings.KAFKA_ENABLED:
            logger.warning(
                "Incorrect Kafka settings, it is impossible to execute the request in the background."
            )
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        await request.body()
        try:
            channel_name = await resolve_channel_name_async(request)
        except ChannelNameError as err:
            response = JSONResponse(status_code=401, content={'detail': str(err)})
            await response(scope, receive, send)
            return

        payload = build_request_payload(request)
        message = await enqueue_task_async(
            topic_name=settings.KAFKA_TOPIC_ASYNC_BG,
            channel_name=channel_name,
            payload=payload,
            partition_marker=partition_marker(payload.body),
        )

        response = JSONResponse(
            status_code=202, content={"data": None, "meta": {"async_request_id": message.task_id}}
        )
        await response(scope, receive, send)
