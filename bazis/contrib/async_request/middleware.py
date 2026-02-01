from __future__ import annotations

import logging

from django.conf import settings

from fastapi import Request

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from bazis.contrib.async_background.producer import enqueue_task_async
from bazis.contrib.async_background.routes import get_async_background_response
from bazis.contrib.async_background.utils import ChannelNameError, resolve_channel_name_async

from .utils import build_request_payload


logger = logging.getLogger(__name__)


class AsyncRequestMiddleware:
    def __init__(self, app):
        self.app = app
        self._no_bg_prefixes: tuple[str, ...] | None = None

    def _build_no_bg_prefixes(self, app) -> tuple[str, ...]:
        prefixes: list[str] = []
        path = app.url_path_for(get_async_background_response.__name__, task_id="__dummy__")
        if path:
            prefix = str(path).replace("/__dummy__/", "/")
            while "//" in prefix:
                prefix = prefix.replace("//", "/")
            prefixes.append(prefix)
        return tuple(prefixes)

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        if self._no_bg_prefixes is None:
            scope_app = scope.get("app")
            print(scope_app.user_middleware)
            self._no_bg_prefixes = self._build_no_bg_prefixes(scope_app or self.app)

        path = scope.get("path", "")
        if self._no_bg_prefixes and any(path.startswith(prefix) for prefix in self._no_bg_prefixes):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if (
            headers.get("X-Async-Background-Internal", "").lower() == "true"
            or "X-Async-Background" not in headers
        ):
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
            topic_name=settings.KAFKA_TOPIC_ASYNC_REQUEST,
            channel_name=channel_name,
            payload=payload,
            partition_marker=(
                payload.body.get("data", {}).get("id") if isinstance(payload.body, dict) else None
            ),
        )

        response = JSONResponse(
            status_code=202,
            content={"data": None, "meta": {"async_request_id": message.task_id}},
        )
        await response(scope, receive, send)
