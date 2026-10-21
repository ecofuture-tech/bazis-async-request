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
Django system checks of bazis-async-request (see `manage.py bazis_doctor`).
"""

from django.conf import settings
from django.core.checks import Error, Warning, register
from django.utils.module_loading import import_string


@register()
def check_kafka_enabled(app_configs, **kwargs):
    """
    Without Kafka the middleware executes the requests sent with `X-Async-Background`
    synchronously, and only logs a warning.
    """
    # the settings of bazis-async-background are missing if BS_BAZIS_APPS does not list it
    if not getattr(settings, 'KAFKA_ENABLED', False):
        return [
            Warning(
                'Kafka is not configured: the requests sent with X-Async-Background are '
                'executed synchronously.',
                hint=(
                    'Set BS_KAFKA_BOOTSTRAP_SERVERS and BS_KAFKA_TOPIC_ASYNC_BG (and list '
                    'bazis.contrib.async_background in BS_BAZIS_APPS if it is set).'
                ),
                id='async_request.W001',
            )
        ]
    return []


@register()
def check_response_route(app_configs, **kwargs):
    """
    The middleware looks up the route of the results to let its requests through: without
    it every HTTP request through the middleware fails. Runs when the application is
    loaded (`manage.py bazis_doctor`).
    """
    from bazis.core.introspect import loaded_app

    if (app := loaded_app()) is None:
        return []

    from starlette.routing import NoMatchFound

    from .utils import results_route_prefix

    try:
        results_route_prefix(app)
    except NoMatchFound:
        return [
            Error(
                'The route of the background results is not registered: '
                'AsyncRequestMiddleware fails on every HTTP request.',
                hint="Register it: router.register('bazis.contrib.async_background.router').",
                id='async_request.E001',
            )
        ]
    return []


@register()
def check_topic_resolver(app_configs, **kwargs):
    """
    The middleware calls the callable of BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER for every
    background request: if it cannot be imported, every such request fails.
    """
    resolver_path = getattr(settings, 'BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER', None)
    if not resolver_path:
        return []

    try:
        resolver = import_string(resolver_path)
    # importing the module of the project can fail with any error
    except Exception as err:
        problem = f'cannot be imported ({err})'
    else:
        if callable(resolver):
            return []
        problem = 'is not callable'
    return [
        Error(
            f'BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER {resolver_path!r} {problem}: '
            'every request sent with X-Async-Background fails.',
            hint='Set the dotted path of a callable(payload: AsyncRequestPayload) -> str.',
            id='async_request.E002',
        )
    ]
