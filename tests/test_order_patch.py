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

"""
Checking patch requests.
"""

import json

import pytest
from bazis_test_utils.utils import get_api_client
from fast_start.models import OrderStatus


response_paragon = {'endpoint': '/api/v1/fast_start/order/e7cc4c8c-3ed1-4576-96ad-b3fd7c0b2a5a/',
                    'headers': [['content-length', '217'],
                                ['content-type', 'application/vnd.api+json']],
                    'response': {'data': {'attributes': {'description': 'Order',
                                                         'status': 'supplied'},
                                          'bs:action': 'view',
                                          'id': 'e7cc4c8c-3ed1-4576-96ad-b3fd7c0b2a5a',
                                          'relationships': {'delivery_company': {'data': None}},
                                          'type': 'fast_start.order'},
                                 'meta': {}},
                    'status': 200,
                    'task_id': 'ff50adf0-8f1b-4ccb-85ef-7ad9ce69e0ff'}


@pytest.mark.django_db(transaction=True)
def test_manager_patch_order(create_test_data, sample_app):
    _, manager, _, buyer_2, order = create_test_data

    # The delivery manager cannot edit an order that is in draft status
    order.status = OrderStatus.DRAFT
    order.save()
    response = get_api_client(sample_app, manager.jwt_build()).patch(
        f"/api/v1/fast_start/order/{order.id}/",
        json_data={
            "data": {
                "id": str(order.id),
                "type": "fast_start.order",
                "bs:action": "change",
                "attributes": {"description": "Shop Updated"},
            }
        },
    )
    assert response.status_code == 403
    response_data = response.json()
    del response_data["errors"][0]["traceback"]
    assert response_data == {
        "errors": [
            {
                "detail": "Permission denied: check access",
                "status": 403,
            }
        ]
    }

    # The delivery manager can edit an order that is in in_progress status
    order.status = OrderStatus.IN_PROGRESS
    order.save()
    response = get_api_client(sample_app, manager.jwt_build()).patch(
        f"/api/v1/fast_start/order/{order.id}/",
        json_data={
            "data": {
                "id": str(order.id),
                "type": "fast_start.order",
                "bs:action": "change",
                "attributes": {"status": OrderStatus.SUPPLIED},
            },
        },
    )
    assert response.status_code == 200
    response_data = response.json()
    response_paragon["response"]["data"]["id"] = str(order.id)
    assert response_data == response_paragon["response"]


@pytest.mark.run_with_consumer
@pytest.mark.django_db(transaction=True)
def test_manager_patch_order_async(create_test_data, sample_app, process_async_response):
    _, manager, _, buyer_2, order = create_test_data

    # The delivery manager cannot edit an order that is in draft status
    order.status = OrderStatus.DRAFT
    order.save()
    response = get_api_client(sample_app, manager.jwt_build()).patch(
        f"/api/v1/fast_start/order/{order.id}/",
        json_data={
            "data": {
                "id": str(order.id),
                "type": "fast_start.order",
                "bs:action": "change",
                "attributes": {"description": "Shop Updated"},
            }
        },
        headers={"X-Async-Background": "true"},
    )
    assert response.status_code == 202
    response_data = response.json()
    task_id = response.json()["meta"]["async_request_id"]
    assert response_data == {"data": None, "meta": {"async_request_id": task_id}}

    response_paragon["response"]["data"]["id"] = str(order.id)
    response_paragon["task_id"] = task_id

    # checking the result written by the consumer to Redis
    paragon_403 = {
        "endpoint": f"/api/v1/fast_start/order/{order.id}/",
        "headers": [
            ["content-length", "4741"],
            ["content-type", "application/json"]
        ],
        "response": {
            "errors": [
                {
                    "detail": "Permission denied: check access",
                    "status": 403
                }
            ]
        },
        "status": 403,
        "task_id": task_id
    }

    result_in_redis = process_async_response(task_id)
    response_data = json.loads(result_in_redis.decode("utf-8"))["response"]
    del response_data["response"]["errors"][0]["traceback"]
    assert response_data == paragon_403

    # retrieving background task results via the endpoint by id_task
    response = get_api_client(sample_app, manager.jwt_build()).get(
        f"/api/v1/async_background_response/{task_id}/"
    )
    assert response.status_code == 200
    response_data = response.json()
    del response_data["response"]["errors"][0]["traceback"]
    assert response_data == paragon_403

    # The delivery manager can edit an order that is in in_progress status
    order.status = OrderStatus.IN_PROGRESS
    order.save()
    response = get_api_client(sample_app, manager.jwt_build()).patch(
        f"/api/v1/fast_start/order/{order.id}/",
        json_data={
            "data": {
                "id": str(order.id),
                "type": "fast_start.order",
                "bs:action": "change",
                "attributes": {"status": OrderStatus.SUPPLIED},
            },
        },
        headers={"X-Async-Background": "true"},
    )

    assert response.status_code == 202
    response_data = response.json()
    task_id = response.json()["meta"]["async_request_id"]
    assert response_data == {"data": None, "meta": {"async_request_id": task_id}}

    response_paragon["response"]["data"]["id"] = str(order.id)
    response_paragon["task_id"] = task_id
    response_paragon["endpoint"] = f"/api/v1/fast_start/order/{order.id}/"

    # checking the result written by the consumer to Redis
    result_in_redis = process_async_response(task_id)
    response_data = json.loads(result_in_redis.decode("utf-8"))["response"]
    assert response_data == response_paragon

    # retrieving background task results via the endpoint by id_task
    response = get_api_client(sample_app, manager.jwt_build()).get(
        f"/api/v1/async_background_response/{task_id}/"
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data == response_paragon
