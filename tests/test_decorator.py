"""
Decorator check.
"""

import json
import logging
import threading
import time

import pytest
from bazis_test_utils.utils import get_api_client

from bazis.contrib.ws.models_abstract import redis


logger = logging.getLogger(__name__)


response_paragon = {'endpoint': '/api/v1/some-async-endpoint/',
                    'headers': [['content-length', '65'], ['content-type', 'application/json']],
                    'response': [{'some_dict': {'some_float': 1.2}, 'some_int': 1, 'some_str': 'asdf'}],
                    'status': 200,
                    'task_id': '2526046e-5d7a-41fb-a058-935b602726a9'}


@pytest.mark.django_db(transaction=True)
def test_wo_header(create_test_data, sample_app):
    _, manager, _, _, _ = create_test_data

    response = get_api_client(sample_app, manager.jwt_build()).get("/api/v1/some-async-endpoint/?some_str=asdf")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data == response_paragon["response"]

    response = get_api_client(sample_app, manager.jwt_build()).get("/api/v1/some-sync-endpoint/?some_str=asdf")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data == response_paragon["response"]

@pytest.mark.django_db(transaction=True)
def test_wo_token(sample_app):
    response = get_api_client(sample_app).get(
        "/api/v1/some-sync-endpoint/?some_str=asdf", headers={"X-Async-Background": "true"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == (
        "No valid token found in request for channel name resolution."
    )

@pytest.mark.run_with_consumer
@pytest.mark.django_db(transaction=True)
def test_async_decorator(create_test_data, sample_app, process_async_response):
    _, manager, _, _, _ = create_test_data

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

    # Create a background task
    response = get_api_client(sample_app, manager.jwt_build()).get(
        "/api/v1/some-async-endpoint/?some_str=asdf", headers={"X-Async-Background": "true"}
    )
    assert response.status_code == 202
    response_data = response.json()
    task_id = response.json()["meta"]["async_request_id"]
    assert response_data == {"data": None, "meta": {"async_request_id": task_id}}

    response_paragon["task_id"] = task_id

    # Check the result written to Redis by the consumer
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

    # Retrieve background task results by id_task via the endpoint
    response = get_api_client(sample_app, manager.jwt_build()).get(
        f"/api/v1/async_background_response/{task_id}/"
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data == response_paragon


@pytest.mark.run_with_consumer
@pytest.mark.django_db(transaction=True)
def test_sync_decorator(create_test_data, sample_app, process_async_response):


    _, manager, _, _, _ = create_test_data

    channel_name = manager.user_channel
    logger.info("test_sync_decorator: channel_name=%s", channel_name)
    # Collect messages from Redis into a list
    received_messages = []

    # Start the subscriber in a separate thread
    def redis_subscriber():
        pubsub = redis.pubsub()
        pubsub.subscribe(channel_name)
        logger.info("test_sync_decorator: redis subscriber started")
        for message in pubsub.listen():
            logger.info("test_sync_decorator: message=%s", message)
            if (
                    message["type"] == "message"
                    and json.loads(message["data"].decode("utf-8"))["status"] == "completed"
            ):
                logger.info("test_sync_decorator: redis completed message=%s", message)
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

    # Create a background task
    logger.info("test_sync_decorator: sending async request to sync endpoint")
    response = get_api_client(sample_app, manager.jwt_build()).get(
        "/api/v1/some-sync-endpoint/?some_str=asdf", headers={"X-Async-Background": "true"}
    )
    logger.info(
        "test_sync_decorator: response status=%s body=%s",
        response.status_code,
        response.json(),
    )
    assert response.status_code == 202
    response_data = response.json()
    task_id = response.json()["meta"]["async_request_id"]
    logger.info("test_sync_decorator: task_id=%s", task_id)
    assert response_data == {"data": None, "meta": {"async_request_id": task_id}}

    response_paragon["task_id"] = task_id

    # Check the result written to Redis by the consumer
    logger.info("test_sync_decorator: waiting for process_async_response")
    result_in_redis = process_async_response(task_id)
    response_data = json.loads(result_in_redis.decode("utf-8"))["response"]
    response_paragon["endpoint"] = '/api/v1/some-sync-endpoint/'
    assert response_data == response_paragon

    # Wait for the Redis subscriber to finish
    logger.info("test_sync_decorator: joining subscriber thread")
    subscriber_thread.join(timeout=2)
    # Check the received publish messages
    assert len(received_messages) > 0, "No messages received on Redis channel"
    published_message = received_messages[0]
    assert published_message == {
        "action": "async_bg",
        "status": "completed",
        "task_id": task_id,
    }

    # retrieving background task results via the endpoint by id_task
    logger.info("test_sync_decorator: fetching async_background_response")
    response = get_api_client(sample_app, manager.jwt_build()).get(
        f"/api/v1/async_background_response/{task_id}/"
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data == response_paragon
