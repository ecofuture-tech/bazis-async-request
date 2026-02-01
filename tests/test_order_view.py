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
Checking GET requests.
"""

import json
import threading
import time

import pytest
from bazis_test_utils.utils import get_api_client

from bazis.contrib.ws.models_abstract import redis


response_paragon = {'endpoint': '/api/v1/fast_start/order/',
                    'headers': [['content-length', '399'],
                                ['content-type', 'application/vnd.api+json']],
                    'response': {'data': [{'attributes': {'description': 'Order',
                                                          'status': 'in_progress'},
                                           'bs:action': 'view',
                                           'id': 'bb0cd4cf-ac7a-47ca-8507-950ec732fdfb',
                                           'relationships': {'delivery_company': {'data': None}},
                                           'type': 'fast_start.order'}],
                                 'links': {'first': 'http://testserver/api/v1/fast_start/order/',
                                           'last': 'http://testserver/api/v1/fast_start/order/?page%5Blimit%5D=20&page%5Boffset%5D=0',
                                           'next': None,
                                           'prev': None},
                                 'meta': {}},
                    'status': 200,
                    'task_id': '2d0b2879-48aa-4f98-893c-cfb19215c1b8'}

response_paragon_empty = {'endpoint': '/api/v1/fast_start/order/',
                          'headers': [['content-length', '200'],
                                      ['content-type', 'application/vnd.api+json']],
                          'response': {'data': [],
                                       'links': {'first': 'http://testserver/api/v1/fast_start/order/',
                                                 'last': 'http://testserver/api/v1/fast_start/order/?page%5Blimit%5D=20&page%5Boffset%5D=-20',
                                                 'next': None,
                                                 'prev': None},
                                       'meta': {}},
                          'status': 200,
                          'task_id': 'f4ec100e-38d4-4770-bfdd-4ad26563df03'}


@pytest.mark.django_db(transaction=True)
def test_manager_see_order_not_other_buyer(create_test_data, sample_app):
    _, manager, _, buyer_2, order = create_test_data

    ### the manager receives the list of orders with buyer 1's order, and sees only their own 3 fields there
    response = get_api_client(sample_app, manager.jwt_build()).get("/api/v1/fast_start/order/")
    assert response.status_code == 200
    response_data = response.json()
    response_paragon["response"]["data"][0]["id"] = str(order.id)
    assert response_data == response_paragon["response"]

    ### buyer 2 receives the list of orders without buyer 1's order
    response = get_api_client(sample_app, buyer_2.jwt_build()).get("/api/v1/fast_start/order/")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data == response_paragon_empty["response"]


@pytest.mark.run_with_consumer
@pytest.mark.django_db(transaction=True)
def test_manager_see_order_not_other_buyer_async(
        create_test_data, sample_app, process_async_response
):
    _, manager, _, buyer_2, order = create_test_data

    channel_name = manager.user_channel
    # Collect messages from Redis into a list
    received_messages = []

    # Start the subscriber in a separate thread
    def redis_subscriber():
        pubsub = redis.pubsub()
        pubsub.subscribe(channel_name)
        for message in pubsub.listen():
            if (
                    message["type"] == "message"
                    and json.loads(message["data"].decode("utf-8"))["status"] == "completed"
            ):
                received_messages.append(json.loads(message["data"].decode("utf-8")))
                # Unsubscribe after the first message
                pubsub.unsubscribe(channel_name)
                break

    # Start the subscriber BEFORE executing the request
    subscriber_thread = threading.Thread(target=redis_subscriber)
    subscriber_thread.daemon = True
    subscriber_thread.start()
    # Give the subscriber time to connect
    time.sleep(0.5)

    ### the manager receives the list of orders with buyer 1's order
    # create a background task
    response = get_api_client(sample_app, manager.jwt_build()).get(
        "/api/v1/fast_start/order/", headers={"X-Async-Background": "true"}
    )
    assert response.status_code == 202
    response_data = response.json()
    task_id = response.json()["meta"]["async_request_id"]
    assert response_data == {"data": None, "meta": {"async_request_id": task_id}}

    response_paragon["response"]["data"][0]["id"] = str(order.id)
    response_paragon["task_id"] = task_id

    # check the result written by the consumer into Redis
    result_in_redis = process_async_response(task_id)
    response_data = json.loads(result_in_redis.decode("utf-8"))["response"]
    assert response_data == response_paragon

    # Wait for the Redis subscriber to finish
    subscriber_thread.join(timeout=2)
    # Check the received publish messages
    assert len(received_messages) > 0, "No messages received on Redis channel"
    published_message = received_messages[0]
    assert published_message == {
        "action": "async_bg",
        "status": "completed",
        "task_id": task_id,
    }

    # retrieve background task results by task_id via the endpoint
    response = get_api_client(sample_app, manager.jwt_build()).get(
        f"/api/v1/async_background_response/{task_id}/"
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data == response_paragon

    ### buyer 2 receives the list of orders without buyer 1's order
    # create a background task
    response = get_api_client(sample_app, buyer_2.jwt_build()).get(
        "/api/v1/fast_start/order/", headers={"X-Async-Background": "true"}
    )
    assert response.status_code == 202
    response_data = response.json()
    task_id = response.json()["meta"]["async_request_id"]
    assert response_data == {"data": None, "meta": {"async_request_id": task_id}}

    # check the result written by the consumer into Redis
    result_in_redis = process_async_response(task_id)
    response_data = json.loads(result_in_redis.decode("utf-8"))["response"]
    assert len(response_data["response"]["data"]) == 0

    # retrieve background task results by task_id via the endpoint
    response = get_api_client(sample_app, buyer_2.jwt_build()).get(
        f"/api/v1/async_background_response/{task_id}/"
    )
    assert response.status_code == 200
    response_data = response.json()
    response_paragon_empty["task_id"] = task_id
    assert response_data == response_paragon_empty
