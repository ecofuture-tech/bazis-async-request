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

from fastapi import HTTPException, Request, status

from .schemas import AsyncRequestPayload


logger = logging.getLogger(__name__)

#: the ASGI scope key that marks a request executed by the consumer
SCOPE_INTERNAL_KEY = "bazis_async_request_internal"


def is_internal_request(scope) -> bool:
    """
    Whether the request is executed by the consumer of async requests.
    """
    return scope.get(SCOPE_INTERNAL_KEY) is True


def build_request_payload(request: Request) -> AsyncRequestPayload:
    """Creates a payload for sending to Kafka."""
    body_raw: bytes = request.scope.get("_cached_body") or getattr(request, "_body", b"")
    try:
        body: dict = json.loads(body_raw.decode("utf-8")) if body_raw else {}
    except json.JSONDecodeError:
        body = {}

    headers: list[tuple[str, str]] = []
    for k, v in request.scope.get("headers", []):
        k_val, v_val = k.decode("latin-1"), v.decode("latin-1")
        if k_val.lower() not in ("x-async-background", "x-async-background-internal"):
            headers.append((k_val, v_val))

    return AsyncRequestPayload(
        path=request.scope["path"],
        raw_path=(request.scope.get("raw_path") or b"").decode("latin-1") or None,
        root_path=request.scope.get("root_path", ""),
        query_string=request.url.query,
        headers=headers,
        request_client=request.client,
        method=request.method,
        type=request.scope["type"],
        http_version=request.scope["http_version"],
        scheme=request.scope["scheme"],
        body=body,
    )


async def require_async(request: Request) -> None:
    """
    Allows the endpoint only for requests executed in the background. The header
    `X-Async-Background-Internal` is no longer trusted: any client could send it.
    """
    if is_internal_request(request.scope):
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="This endpoint is available only via async request.",
    )
