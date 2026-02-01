import json
import logging

from fastapi import HTTPException, Request, status

from .schemas import AsyncRequestPayload


logger = logging.getLogger(__name__)


def build_request_payload(request: Request) -> AsyncRequestPayload:
    """Creates a payload for sending to Kafka."""
    body_raw: bytes = request.scope.get("_cached_body") or getattr(request, "_body", b"")
    try:
        body: dict = json.loads(body_raw.decode("utf-8")) if body_raw else {}
    except json.JSONDecodeError:
        body = {}

    headers: list[tuple[str, str]] = []
    for k, v in request.scope.get("headers", []):
        try:
            k_val, v_val = k.decode(), v.decode()
            if k_val.lower() not in ("x-async-background",):
                headers.append((k_val, v_val))
        except Exception as e:
            logger.exception("Error decoding header: %s", e)

    headers.append(("x-async-background-internal", "true"))

    return AsyncRequestPayload(
        path=request.url.path,
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
    """Allow only async-request or internal async-request requests."""
    if request.headers.get("X-Async-Background-Internal", "").lower() == "true":
        return
    if "X-Async-Background" in request.headers:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="This endpoint is available only via async request.",
    )
