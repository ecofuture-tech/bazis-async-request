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
Checking calculated fields and query parameters.
"""

from urllib.parse import urlencode

import pytest
from bazis_test_utils.utils import get_api_client
from fast_start.models import Order, OrderStatus, Shop


response_paragon = {
    "data": [
        {
            "attributes": {"supplied_orders_count": "0", "name": "Shop 1"},
            "bs:action": "view",
            "id": "e94e2f00-35f1-4a17-ab17-12b44e730c88",
            "relationships": {
                "author": {"data": None},
                "author_updated": {"data": None},
                "manager": {
                    "data": [{"id": "8b8358ae-3a89-4fe0-881d-f845d3c4e4cd", "type": "users.user"}]
                },
            },
            "type": "fast_start.shop",
        }
    ],
    "links": {
        "first": "http://testserver/api/v1/fast_start/shop/",
        "last": "http://testserver/api/v1/fast_start/shop/?page%5Blimit%5D=20&page%5Boffset%5D=0",
        "next": None,
        "prev": None,
    },
    "meta": {},
}


response_paragon_empty = {
    "data": [],
    "links": {
        "first": "http://testserver/api/v1/fast_start/order/",
        "last": "http://testserver/api/v1/fast_start/order/?page%5Blimit%5D=20&page%5Boffset%5D=-20",
        "next": None,
        "prev": None,
    },
    "meta": {},
}


@pytest.mark.run_with_consumer
@pytest.mark.django_db(transaction=True)
def test_calc_and_params(create_test_data, sample_app, process_async_response):
    shop, manager, _, buyer_2, order = create_test_data

    # the manager gets the list of shops without restrictions because PermitRouteBase is not selected and no roles are checked
    response = get_api_client(sample_app, manager.jwt_build()).get("/api/v1/fast_start/shop/")
    assert response.status_code == 200
    response_data = response.json()
    response_paragon["data"][0]["id"] = str(shop.id)
    response_paragon["data"][0]["relationships"]["manager"]["data"][0]["id"] = str(manager.id)
    del response_data["data"][0]["attributes"]["dt_created"]
    del response_data["data"][0]["attributes"]["dt_updated"]
    assert response_data == response_paragon

    # buyer 2 also gets the list of shops without restrictions
    response = get_api_client(sample_app, buyer_2.jwt_build()).get("/api/v1/fast_start/shop/")
    assert response.status_code == 200
    response_data = response.json()
    response_paragon["data"][0]["id"] = str(shop.id)
    response_paragon["data"][0]["relationships"]["manager"]["data"][0]["id"] = str(manager.id)
    del response_data["data"][0]["attributes"]["dt_created"]
    del response_data["data"][0]["attributes"]["dt_updated"]
    assert response_data == response_paragon

    # change the status to supplied and now the manager's calculated field supplied_orders_count returns 1
    order.status = OrderStatus.SUPPLIED
    order.save()
    response = get_api_client(sample_app, manager.jwt_build()).get("/api/v1/fast_start/shop/")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["data"][0]["attributes"]["supplied_orders_count"] == "1"

    # for buyer 2, supplied_orders_count also returns 1, taking into account the order fulfilled by the shop for buyer 1
    response = get_api_client(sample_app, buyer_2.jwt_build()).get("/api/v1/fast_start/shop/")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["data"][0]["attributes"]["supplied_orders_count"] == "1"

    # now create one more order for this shop from the second buyer
    # and check that for the manager and buyer 2 the shop is returned with 2 orders
    Order.objects.create(
        description="Order 2", shop=shop, author=buyer_2, status=OrderStatus.SUPPLIED
    )

    response = get_api_client(sample_app, manager.jwt_build()).get("/api/v1/fast_start/shop/")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["data"][0]["attributes"]["supplied_orders_count"] == "2"

    response = get_api_client(sample_app, buyer_2.jwt_build()).get("/api/v1/fast_start/shop/")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["data"][0]["attributes"]["supplied_orders_count"] == "2"

    # now create one more shop with 1 order and check that 2 shops are returned
    shop_2 = Shop.objects.create(name="Shop 2")
    Order.objects.create(
        description="Order 3", shop=shop_2, author=buyer_2, status=OrderStatus.SUPPLIED
    )

    response = get_api_client(sample_app, manager.jwt_build()).get("/api/v1/fast_start/shop/")
    assert response.status_code == 200
    response_data = response.json()

    shop_ids = {item["id"] for item in response_data["data"]}
    assert shop_ids == {str(shop.id), str(shop_2.id)}

    supplied_counts = {
        item["id"]: item["attributes"]["supplied_orders_count"] for item in response_data["data"]
    }
    assert supplied_counts[str(shop.id)] == "2"
    assert supplied_counts[str(shop_2.id)] == "1"

    ### now create a request with a filter in the query parameters,
    # so that thanks to the query filter only shop 1 is returned and that it is returned with the calculated field
    query_param = urlencode({"filter": "name=Shop 1"})
    response = get_api_client(sample_app, manager.jwt_build()).get(
        f"/api/v1/fast_start/shop/?{query_param}"
    )
    assert response.status_code == 200
    response_data = response.json()

    assert len(response_data["data"]) == 1
    assert response_data["data"][0]["id"] == str(shop.id)
    assert response_data["data"][0]["attributes"]["supplied_orders_count"] == "2"

    # now asynchronously check getting the same result
    # creating a background task
    response = get_api_client(sample_app, manager.jwt_build()).get(
        f"/api/v1/fast_start/shop/?{query_param}", headers={"X-Async-Background": "true"}
    )
    assert response.status_code == 202
    response_data = response.json()
    task_id = response.json()["meta"]["async_request_id"]
    assert response_data == {"data": None, "meta": {"async_request_id": task_id}}

    # executing the task by the consumer
    process_async_response(task_id)

    # getting the results of background tasks by id_task via the endpoint
    response = get_api_client(sample_app, manager.jwt_build()).get(
        f"/api/v1/async_background_response/{task_id}/"
    )
    assert response.status_code == 200
    response_data = response.json()

    assert len(response_data["response"]["data"]) == 1
    assert response_data["response"]["data"][0]["id"] == str(shop.id)
    assert response_data["response"]["data"][0]["attributes"]["supplied_orders_count"] == "2"
