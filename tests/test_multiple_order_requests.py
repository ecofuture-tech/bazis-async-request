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
Verification of multiple patch requests.
On the one hand, it is checked that Kafka preserves the correct sequence when processing patches,
that is, that despite the parallel work of several consumers, the final value of the object in the DB
will correspond to the chronologically last patch of the corresponding document,
since due to the use of a partition marker, tasks for the same document will be placed into the same
partition, to which, accordingly, only one consumer is usually subscribed, processing tasks
from its partition queue in chronological order.
On the other hand, this performs a general check of the mechanism itself in conditions as close to reality as possible,
that is, that starting several consumers in several processes and their parallel processing of tasks from the Kafka
topic is performed successfully without causing any errors.
"""

import json
import time

import pytest
from bazis_test_utils.utils import get_api_client
from fast_start.models import Order, OrderStatus

from bazis.contrib.ws.models_abstract import redis


@pytest.mark.run_with_consumer
@pytest.mark.django_db(transaction=True)
def test_manager_patch_order_async(create_test_data, sample_app):
    shop, manager, _, buyer_2, order = create_test_data

    # Create a topic with 15 partitions
    # Create 15 shops
    orders = {}
    tasks = {}
    for order_i in range(0, 15):
        orders[order_i] = Order.objects.create(
            description=f"Description {order_i} initial",
            shop=shop,
            author=buyer_2,
            status=OrderStatus.IN_PROGRESS,
        )

    # Make 10 sequential patches of the description attribute value for each of the 15 orders
    for order_i in range(0, 15):
        order_id = orders[order_i].id
        for patch_i in range(0, 10):
            response = get_api_client(sample_app, manager.jwt_build()).patch(
                f"/api/v1/fast_start/order/{order_id}/",
                json_data={
                    "data": {
                        "id": str(order_id),
                        "type": "fast_start.order",
                        "bs:action": "change",
                        "attributes": {"description": f"Description {order_i}/{patch_i}"},
                    },
                },
                headers={"X-Async-Background": "true"},
            )
            assert response.status_code == 202
        tasks[order_i] = response.json()["meta"]["async_request_id"]

    # Check the statuses of the last (10th) background patch for each order.
    # Check that the current value for each order corresponds to the last (10th) patch.

    # Check the result written by the consumer to Redis
    for _ in range(180):
        processed = 0
        for order_i in range(0, 15):
            if redis_data := redis.get(tasks[order_i]):
                data_dict = json.loads(redis_data.decode("utf-8"))
                if data_dict["status"] == "completed":
                    processed += 1
        if processed == 15:
            break
        else:
            time.sleep(1)
    else:
        pytest.fail(f"Message processing incomplete: only {processed} of 15 messages processed")

    # Retrieve the results of background tasks by id_task via the endpoint
    for order_i in range(0, 15):
        response = get_api_client(sample_app, manager.jwt_build()).get(
            f"/api/v1/async_background_response/{tasks[order_i]}/"
        )
        assert response.status_code == 200
        response_data = response.json()
        assert (
            response_data["response"]["data"]["attributes"]["description"] == f"Description {order_i}/{patch_i}"
        )
