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

import pytest
from bazis_test_utils.utils import get_api_client


@pytest.mark.run_with_consumer
@pytest.mark.django_db(transaction=True)
def test_async_patch_shop_name_only(create_test_data, sample_app, process_async_response):
    shop, manager, *_ = create_test_data

    # Asynchronous PATCH: change the name
    # the headers={"X-Async-Background": "true"} are needed
    response = get_api_client(sample_app, manager.jwt_build()).patch(
        f"/api/v1/fast_start/shop/{shop.id}/",
        json_data={
            "data": {
                "id": str(shop.id),
                "type": "fast_start.shop",
                "bs:action": "change",
                "attributes": {"name": "Shop 1 Updated"},
            }
        },
        headers={"X-Async-Background": "true"},
    )
    assert response.status_code == 202
    task_id = response.json()["meta"]["async_request_id"]
    assert response.json() == {"data": None, "meta": {"async_request_id": task_id}}

    # Processing by the consumer
    redis_result = process_async_response(task_id)
    response_data = json.loads(redis_result.decode("utf-8"))["response"]
    assert response_data["response"]["data"]["id"] == str(shop.id)
    assert response_data["response"]["data"]["attributes"]["name"] == "Shop 1 Updated"

    # Checking retrieval via the API
    response = get_api_client(sample_app, manager.jwt_build()).get(f"/api/v1/fast_start/shop/{shop.id}/")
    assert response.status_code == 200
    assert response.json()["data"]["attributes"]["name"] == "Shop 1 Updated"
