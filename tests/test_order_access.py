"""
Checking access to the results of background tasks.
"""

import json

import pytest
from bazis_test_utils.utils import get_api_client


response_paragon = {'endpoint': '/api/v1/fast_start/order/',
                    'headers': [['content-length', '399'],
                                ['content-type', 'application/vnd.api+json']],
                    'response': {'data': [{'attributes': {'description': 'Order',
                                                          'status': 'in_progress'},
                                           'bs:action': 'view',
                                           'id': '0030451c-7f5c-4b94-944d-d8428d559415',
                                           'relationships': {'delivery_company': {'data': None}},
                                           'type': 'fast_start.order'}],
                                 'links': {'first': 'http://testserver/api/v1/fast_start/order/',
                                           'last': 'http://testserver/api/v1/fast_start/order/?page%5Blimit%5D=20&page%5Boffset%5D=0',
                                           'next': None,
                                           'prev': None},
                                 'meta': {}},
                    'status': 200,
                    'task_id': '8601c196-d0b0-4d69-8064-870e7abbb15f'}

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
def test_access_segregation(create_test_data, sample_app, process_async_response):
    _, manager, _, buyer_2, order = create_test_data

    ### the manager receives the list of orders with the order of buyer 1
    # creating a background task
    response = get_api_client(sample_app, manager.jwt_build()).get(
        "/api/v1/fast_start/order/", headers={"X-Async-Background": "true"}
    )
    assert response.status_code == 202
    response_data = response.json()
    task_id = response.json()["meta"]["async_request_id"]
    assert response_data == {"data": None, "meta": {"async_request_id": task_id}}

    response_paragon["response"]["data"][0]["id"] = str(order.id)
    response_paragon["task_id"] = task_id

    # checking the result written by the consumer to Redis
    result_in_redis = process_async_response(task_id)
    response_data = json.loads(result_in_redis.decode("utf-8"))["response"]
    assert response_data == response_paragon

    # getting the results of background tasks by id_task via the endpoint
    response = get_api_client(sample_app, manager.jwt_build()).get(
        f"/api/v1/async_background_response/{task_id}/"
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data == response_paragon

    # users cannot get each other's background task results
    response = get_api_client(sample_app, buyer_2.jwt_build()).get(
        f"/api/v1/async_background_response/{task_id}/"
    )
    assert response.status_code == 403
    response_data = response.json()
    del response_data["errors"][0]["traceback"]
    assert response_data == {
        "errors": [{"detail": "Permission denied: check access", "status": 403}]
    }
