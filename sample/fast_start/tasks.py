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
A second lane of background requests: with BAZIS_ASYNC_REQUEST_TOPIC_RESOLVER set to
`fast_start.tasks.request_topic`, the requests of the shops go to their own Kafka topic,
served by `consumer_shops` (the module is listed in KAFKA_TASKS).
"""

from django.conf import settings

from bazis.contrib.async_request.schemas import AsyncRequestPayload
from bazis.contrib.async_request.tasks import consumer_for_topic


SHOPS_TOPIC = f'{settings.KAFKA_TOPIC_ASYNC_BG}_shops'


def request_topic(payload: AsyncRequestPayload) -> str:
    if '/fast_start/shop/' in payload.path:
        return SHOPS_TOPIC
    return settings.KAFKA_TOPIC_ASYNC_BG


consumer_shops = consumer_for_topic(SHOPS_TOPIC)
