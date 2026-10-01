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

from fastapi import FastAPI

from bazis.contrib.async_request.checks import check_kafka_enabled, check_response_route
from bazis.core.introspect import validate_manifest


def test_manifest_is_valid():
    assert validate_manifest('bazis.contrib.async_request') == []


def test_kafka_enabled_check(settings):
    settings.KAFKA_ENABLED = False
    assert [it.id for it in check_kafka_enabled(None)] == ['async_request.W001']
    settings.KAFKA_ENABLED = True
    assert check_kafka_enabled(None) == []


def test_response_route_check(sample_app, monkeypatch):
    # the sample project registers bazis.contrib.async_background.router
    assert check_response_route(None) == []
    monkeypatch.setattr('bazis.core.introspect.loaded_app', lambda: FastAPI())
    assert [it.id for it in check_response_route(None)] == ['async_request.E001']
