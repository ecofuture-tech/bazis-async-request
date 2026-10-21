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
The Kafka topic of a background request chosen by BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER, and
the consumers of more topics (`consumer_for_topic`).
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from bazis_test_utils.utils import get_api_client

# imported before a test changes the settings: the topic of the shops is the one of the
# consumer process
from fast_start.tasks import SHOPS_TOPIC

from bazis.contrib.async_background.testing import wait_for_task
from bazis.contrib.async_request import checks, middleware, tasks
from bazis.contrib.async_request.checks import check_topic_resolver
from bazis.contrib.async_request.consumers import consumer_for_topic
from bazis.contrib.async_request.schemas import AsyncRequestPayload


RESOLVER = 'fast_start.tasks.request_topic'
ANONYMOUS_TOKEN = 'anonymous-token-0123456789'


@pytest.fixture
def enqueued(settings, monkeypatch):
    """
    The arguments of the queued tasks: the middleware queues them without Kafka.
    """
    settings.KAFKA_ENABLED = True
    if not settings.KAFKA_TOPIC_ASYNC_BG:
        settings.KAFKA_TOPIC_ASYNC_BG = 'sample_async_request'
    calls = []

    async def enqueue_task_async(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(task_id='task-1')

    monkeypatch.setattr(middleware, 'enqueue_task_async', enqueue_task_async)
    return calls


@pytest.fixture
def resolved(settings, monkeypatch):
    """
    Sets the resolver of the sample and returns the payloads it was called with.
    """
    from fast_start import tasks

    settings.BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER = RESOLVER
    calls = []
    request_topic = tasks.request_topic

    def spy(payload):
        calls.append(payload)
        return request_topic(payload)

    monkeypatch.setattr(tasks, 'request_topic', spy)
    return calls


def set_resolver(settings, monkeypatch, resolver):
    settings.BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER = RESOLVER
    monkeypatch.setattr('fast_start.tasks.request_topic', resolver)


def queue(sample_app, path, token=ANONYMOUS_TOKEN):
    return get_api_client(sample_app, token).patch(
        path,
        json_data={'data': {'id': 'item-1', 'type': 'x.y', 'attributes': {}}},
        headers={'X-Async-Background': 'true'},
    )


@pytest.mark.parametrize('unset', ['none', 'missing'])
def test_without_resolver_the_topic_is_kafka_topic_async_bg(
    sample_app, settings, enqueued, unset
):
    """
    Without the setting (or without the settings of the package, when BS_BAZIS_CONFIG_APPS
    does not list it) the requests go to KAFKA_TOPIC_ASYNC_BG, as before.
    """
    if unset == 'none':
        settings.BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER = None
    else:
        del settings.BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER

    response = queue(sample_app, '/api/v1/fast_start/shop/item-1/')

    assert response.status_code == 202
    assert response.json() == {'data': None, 'meta': {'async_request_id': 'task-1'}}
    assert [it['topic_name'] for it in enqueued] == [settings.KAFKA_TOPIC_ASYNC_BG]


def test_resolver_chooses_the_topic(sample_app, settings, enqueued, resolved):
    assert queue(sample_app, '/api/v1/fast_start/shop/item-1/').status_code == 202
    assert queue(sample_app, '/api/v1/fast_start/order/item-1/').status_code == 202

    # called once per request, with the payload that is queued
    assert [it['topic_name'] for it in enqueued] == [SHOPS_TOPIC, settings.KAFKA_TOPIC_ASYNC_BG]
    assert [it['payload'] for it in enqueued] == resolved
    assert all(isinstance(it, AsyncRequestPayload) for it in resolved)
    assert [it['partition_marker'] for it in enqueued] == ['item-1', 'item-1']


@pytest.mark.parametrize('topic', [None, '', b'topic'])
def test_a_resolver_result_that_is_not_a_topic_is_not_queued(
    sample_app, settings, monkeypatch, enqueued, topic
):
    set_resolver(settings, monkeypatch, lambda payload: topic)

    with pytest.raises(ValueError, match='instead of a Kafka topic'):
        queue(sample_app, '/api/v1/fast_start/shop/item-1/')
    assert enqueued == []


def test_an_error_of_the_resolver_is_not_queued(sample_app, settings, monkeypatch, enqueued):
    """
    The error is not hidden behind the default topic: the request fails and no task is
    registered.
    """

    def resolver(payload):
        raise RuntimeError('no lane')

    set_resolver(settings, monkeypatch, resolver)

    with pytest.raises(RuntimeError, match='no lane'):
        queue(sample_app, '/api/v1/fast_start/shop/item-1/')
    assert enqueued == []


@pytest.mark.parametrize('token', [None, 'not.a.jwt'])
def test_the_resolver_is_called_after_the_authentication(sample_app, enqueued, resolved, token):
    """
    A request without a token or with an invalid JWT is answered 401 before its topic is
    chosen.
    """
    response = queue(sample_app, '/api/v1/fast_start/shop/item-1/', token=token)

    assert response.status_code == 401
    assert resolved == []
    assert enqueued == []


@pytest.mark.django_db(transaction=True)
def test_an_inactive_user_is_refused_before_the_resolver(
    create_test_data, sample_app, enqueued, resolved
):
    _, manager, *_ = create_test_data
    token = manager.jwt_build()
    manager.is_active = False
    manager.save(update_fields=['is_active'])

    response = queue(sample_app, '/api/v1/fast_start/shop/item-1/', token=token)

    assert response.status_code == 401
    assert resolved == []
    assert enqueued == []


def test_a_resolver_that_does_not_import_fails_the_request(sample_app, settings, enqueued):
    settings.BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER = 'fast_start.tasks.missing'

    with pytest.raises(ImportError):
        queue(sample_app, '/api/v1/fast_start/shop/item-1/')
    assert enqueued == []


@pytest.mark.parametrize('topic', ['', None])
def test_consumer_for_topic_needs_a_topic(topic):
    """
    FastStream would subscribe to the topic "" (or "None") without an error.
    """
    with pytest.raises(ValueError, match='A Kafka topic is required'):
        consumer_for_topic(topic)


@pytest.mark.parametrize(
    'path, errors',
    [
        (None, []),
        (RESOLVER, []),
        ('fast_start.tasks.missing', ['async_request.E002']),
        ('no_such_module.request_topic', ['async_request.E002']),
        # not callable
        ('fast_start.tasks.SHOPS_TOPIC', ['async_request.E002']),
    ],
)
def test_topic_resolver_check(settings, path, errors):
    settings.BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER = path
    assert [it.id for it in check_topic_resolver(None)] == errors


def test_topic_resolver_check_of_a_module_that_fails(settings, monkeypatch):
    """
    The module of the resolver fails with any error when imported: the check reports it.
    """

    def import_string(path):
        raise RuntimeError('broken module')

    monkeypatch.setattr(checks, 'import_string', import_string)
    settings.BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER = RESOLVER

    errors = check_topic_resolver(None)

    assert [it.id for it in errors] == ['async_request.E002']
    assert 'broken module' in errors[0].msg


def test_tasks_keeps_the_names_of_the_consumer():
    assert tasks.consumer_for_topic is consumer_for_topic
    assert callable(tasks.execute_internal_request)


#: what kafka_consumer_single does before it starts the broker, then the topics of the
#: subscribers before and after importing bazis.contrib.async_request.tasks
CONSUMER_TOPICS_SCRIPT = """
import json

import django

django.setup()

from django.conf import settings

from bazis.contrib.async_background.broker import get_broker_for_consumer
from bazis.core.app import app  # noqa: F401
from bazis.core.router import router  # noqa: F401


def topics():
    return sorted(topic for it in get_broker_for_consumer().subscribers for topic in it.topics)


for task_path in settings.KAFKA_TASKS:
    __import__(task_path)
listed = topics()
__import__('bazis.contrib.async_request.tasks')
print(json.dumps([listed, topics()]))
"""


def test_a_consumer_of_the_project_lane_only():
    """
    A consumer process whose KAFKA_TASKS lists only the module of a lane serves only its
    topic: the module of the consumer (`consumers`) registers no subscriber when imported,
    unlike `tasks`.
    """
    import fast_start

    env = {
        **os.environ,
        'DJANGO_SETTINGS_MODULE': 'sample.settings',
        'BS_KAFKA_TASKS': '["fast_start.tasks"]',
        'BS_KAFKA_TOPIC_ASYNC_BG': 'lane_test',
    }
    result = subprocess.run(
        [sys.executable, '-c', CONSUMER_TOPICS_SCRIPT],
        cwd=Path(fast_start.__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    listed, with_tasks = json.loads(result.stdout.strip().splitlines()[-1])
    assert listed == ['lane_test_shops']
    assert with_tasks == ['lane_test', 'lane_test_shops']


@pytest.mark.run_with_consumer
@pytest.mark.django_db(transaction=True)
def test_two_topics_are_served(create_test_data, sample_app, settings, monkeypatch):
    """
    The consumer of the sample serves KAFKA_TOPIC_ASYNC_BG and the topic of the shops
    (`fast_start.tasks`): the update of a shop, allowed only to the requests replayed by a
    consumer, is executed from its own topic.
    """
    shop, manager, buyer_1, _, order = create_test_data
    settings.BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER = RESOLVER
    topics = []
    enqueue_task_async = middleware.enqueue_task_async

    async def spy(**kwargs):
        topics.append(kwargs['topic_name'])
        return await enqueue_task_async(**kwargs)

    monkeypatch.setattr(middleware, 'enqueue_task_async', spy)

    shop_response = get_api_client(sample_app, manager.jwt_build()).patch(
        f'/api/v1/fast_start/shop/{shop.id}/',
        json_data={
            'data': {
                'id': str(shop.id),
                'type': 'fast_start.shop',
                'bs:action': 'change',
                'attributes': {'name': 'Shop of the second topic'},
            }
        },
        headers={'X-Async-Background': 'true'},
    )
    order_response = get_api_client(sample_app, buyer_1.jwt_build()).get(
        f'/api/v1/fast_start/order/{order.id}/', headers={'X-Async-Background': 'true'}
    )

    assert shop_response.status_code == 202
    assert order_response.status_code == 202
    assert topics == [SHOPS_TOPIC, settings.KAFKA_TOPIC_ASYNC_BG]

    shop_result = wait_for_task(shop_response.json()['meta']['async_request_id'])['response']
    assert shop_result['status'] == 200, shop_result
    assert shop_result['response']['data']['attributes']['name'] == 'Shop of the second topic'
    order_result = wait_for_task(order_response.json()['meta']['async_request_id'])['response']
    assert order_result['status'] == 200, order_result
    assert order_result['response']['data']['id'] == str(order.id)
    shop.refresh_from_db()
    assert shop.name == 'Shop of the second topic'
