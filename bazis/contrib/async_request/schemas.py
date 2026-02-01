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
