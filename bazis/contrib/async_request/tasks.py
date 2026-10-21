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
The consumer of KAFKA_TOPIC_ASYNC_BG: importing the module registers it, list the module in
KAFKA_TASKS. A consumer process that serves only the topics of the project lists only the
project module that calls `consumers.consumer_for_topic`.
"""

from django.conf import settings

from bazis.contrib.async_background.broker import get_broker_for_consumer, subscriber_kwargs

from .consumers import (
    SKIPPED_HEADERS,
    consumer_for_topic,
    execute_internal_request,
    process_async_request,
)


# the names of the module before 2.6 and consumer_for_topic stay importable from here
__all__ = [
    'SKIPPED_HEADERS',
    'consumer_async_requests',
    'consumer_for_topic',
    'execute_internal_request',
    'process_async_request',
]


consumer_async_requests = get_broker_for_consumer().subscriber(
    settings.KAFKA_TOPIC_ASYNC_BG, **subscriber_kwargs()
)(process_async_request)
