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
