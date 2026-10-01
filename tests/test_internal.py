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

import pytest
from bazis_test_utils.utils import get_api_client

from bazis.contrib.async_background.schemas import KafkaTask
from bazis.contrib.async_request.schemas import AsyncRequestPayload
from bazis.contrib.async_request.tasks import execute_internal_request


def _patch_payload(shop) -> dict:
    return {
        "data": {
            "id": str(shop.id),
            "type": "fast_start.shop",
            "bs:action": "change",
            "attributes": {"name": "Changed"},
        }
    }


@pytest.mark.django_db(transaction=True)
def test_forged_internal_header_does_not_bypass_require_async(create_test_data, sample_app):
    """
    The update of a shop is allowed only in the background. The internal header used to
    mark the requests of the consumer, so any client could send it and update synchronously.
    """
    shop, manager, *_ = create_test_data

    response = get_api_client(sample_app, manager.jwt_build()).patch(
        f"/api/v1/fast_start/shop/{shop.id}/",
        json_data=_patch_payload(shop),
        headers={"X-Async-Background-Internal": "true"},
    )

    assert response.status_code == 409
    shop.refresh_from_db()
    assert shop.name != "Changed"


@pytest.mark.django_db(transaction=True)
def test_consumer_executes_the_request(create_test_data, sample_app):
    """
    The consumer replays the request with a body of another length than the original one.
    """
    shop, manager, *_ = create_test_data
    task = KafkaTask[AsyncRequestPayload](
        task_id="task-1",
        channel_name="channel",
        payload=AsyncRequestPayload(
            path=f"/api/v1/fast_start/shop/{shop.id}/",
            query_string="",
            headers=[
                ("authorization", f"Bearer {manager.jwt_build()}"),
                ("content-type", "application/vnd.api+json"),
                ("content-length", "1"),
                ("x-async-background-internal", "true"),
            ],
            request_client=("127.0.0.1", 50000),
            method="PATCH",
            type="http",
            http_version="1.1",
            scheme="http",
            body=_patch_payload(shop),
        ),
    )

    result = asyncio.run(execute_internal_request(task))

    assert result["status"] == 200, result
    assert result["response"]["data"]["attributes"]["name"] == "Changed"
    shop.refresh_from_db()
    assert shop.name == "Changed"


def test_payload_keeps_the_path_as_received():
    """
    The path used to be taken from the URL (percent-encoded) and decoded once more on
    replay, so "%2541" became "A" instead of "%41"; the root path was lost.
    """
    from starlette.requests import Request

    from bazis.contrib.async_request.utils import build_request_payload

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "http_version": "1.1",
            "root_path": "/prefix",
            "path": "/prefix/api/v1/file/%41 b/",
            "raw_path": b"/prefix/api/v1/file/%2541%20b/",
            "query_string": b"x=1",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("testserver", 80),
        }
    )

    payload = build_request_payload(request)

    assert payload.path == "/prefix/api/v1/file/%41 b/"
    assert payload.raw_path == "/prefix/api/v1/file/%2541%20b/"
    assert payload.root_path == "/prefix"


@pytest.mark.parametrize('body', [b'\xff\xfe binary', b'"a string"', b'[1, 2]'])
def test_payload_of_a_body_that_is_not_a_resource(body):
    """
    A binary body failed with UnicodeDecodeError and a JSON body that is not an object (or
    a list of objects) failed the validation of the payload: 500.
    """
    from starlette.requests import Request

    from bazis.contrib.async_request.utils import build_request_payload

    request = Request(
        {
            'type': 'http',
            'method': 'POST',
            'scheme': 'http',
            'http_version': '1.1',
            'path': '/api/v1/files/',
            'raw_path': b'/api/v1/files/',
            'query_string': b'',
            'headers': [],
            'client': ('127.0.0.1', 1),
            'server': ('testserver', 80),
        }
    )
    request._body = body
    assert build_request_payload(request).body == {}


@pytest.mark.parametrize(
    'body, marker',
    [
        ({'data': {'id': 'a1', 'type': 'x.y'}}, 'a1'),
        ({'data': {'id': 7}}, '7'),
        ({'data': [{'id': 'a1'}]}, None),
        ({'data': None}, None),
        ([{'data': {'id': 'a1'}}], None),
    ],
)
def test_partition_marker(body, marker):
    """
    The relationships bodies (`data` is a list or null) failed with AttributeError: 500.
    """
    from bazis.contrib.async_request.middleware import partition_marker

    assert partition_marker(body) == marker
