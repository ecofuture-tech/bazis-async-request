
from pydantic import BaseModel, Field


class AsyncRequestPayload(BaseModel):
    """Payload of a background HTTP request serialized for Kafka."""

    path: str = Field(..., description="Request path")
    query_string: str = Field(..., description="Query string")
    headers: list[tuple[str | bytes, str | bytes]] = Field(
        ..., description="List of HTTP headers"
    )  # List of tuples (header_name, header_value)
    request_client: str | tuple | None = Field(..., description="Client address of the request")
    method: str = Field(..., description="HTTP method")
    type: str = Field(..., description="Request type: http or websocket")
    http_version: str = Field(..., description="HTTP version")
    scheme: str = Field(..., description="Request scheme")
    body: dict | list[dict] = Field(default_factory=dict, description="Request body")

    class Config:
        json_encoders = {bytes: lambda v: v.decode("utf-8")}
        use_enum_values = True
