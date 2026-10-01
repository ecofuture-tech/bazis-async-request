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

import json
import time

from django.contrib.auth import get_user_model
from django.core.management import call_command

import pytest
from translated_fields import to_attribute


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker) -> None:
    with django_db_blocker.unblock():
        call_command("pgtrigger", "install")


@pytest.fixture(scope="function")
def sample_app():
    """
    Fixture to provide an instance of the sample app for each test function.
    """
    from sample.main import app
    return app


def setup_groups_and_roles(groups_def, roles_def):
    """
    Helper to set up groups and roles.
    """
    from bazis.contrib.permit.models import GroupPermission, Permission, Role

    groups = {}
    for group_name, permissions in groups_def.items():
        group, _ = GroupPermission.objects.get_or_create(
            slug=group_name,
            **{to_attribute("name"): group_name},
        )
        for perm_slug in permissions:
            perm, _ = Permission.objects.get_or_create(slug=perm_slug)
            group.permissions.add(perm)
        groups[group_name] = group

    roles = {}
    for role_name, group_names in roles_def.items():
        role, _ = Role.objects.get_or_create(
            slug=role_name,
            **{to_attribute("name"): role_name},
        )
        for group_name in group_names:
            role.groups_permission.add(groups[group_name])
        roles[role_name] = role

    return roles


@pytest.fixture
def fast_start_setup_groups_and_roles(db):
    """
    Set up groups and roles for the Fast Start module.
    Returns:
        dict[str, Role]: dictionary of created Role instances.
    """
    from fast_start.models import OrderStatus

    fast_start_groups = {
        "order_add": ["fast_start.order.item.add.all"],
        "order_delete_all": ["fast_start.order.item.delete.all"],
        # view
        "order_view_author": ["fast_start.order.item.view.author=__selector__"],
        "order_view_shop": ["fast_start.order.item.view.shop=__selector__"],
        "order_view_delivery": ["fast_start.order.item.view.delivery_company=__selector__"],
        "order_view_all": ["fast_start.order.item.view.all"],
        # view only the description field, only for non-draft orders
        "order_view_shop_not_draft": [
            f"fast_start.order.item.view.shop=__selector__&~status={OrderStatus.DRAFT}"
        ],
        "order_view_shop_not_draft_disable_all": [
            f"fast_start.order.field.view.shop=__selector__&~status={OrderStatus.DRAFT}.__all__.disable"
        ],
        "order_view_shop_not_draft_enable_fields": [
            f"fast_start.order.field.view.shop=__selector__&~status={OrderStatus.DRAFT}.description.enable",
            f"fast_start.order.field.view.shop=__selector__&~status={OrderStatus.DRAFT}.status.enable",
            f"fast_start.order.field.view.shop=__selector__&~status={OrderStatus.DRAFT}.delivery_company.enable",
        ],
        # edit only the status and delivery_company fields, only for in_progress orders
        "order_edit_shop_in_progress": [
            f"fast_start.order.item.change.shop=__selector__&status={OrderStatus.IN_PROGRESS}"
        ],
        "order_edit_shop_in_progress_disable_all": [
            f"fast_start.order.field.change.shop=__selector__&status={OrderStatus.IN_PROGRESS}.__all__.disable"
        ],
        "order_edit_shop_in_progress_enable_fields": [
            f"fast_start.order.field.change.shop=__selector__&status={OrderStatus.IN_PROGRESS}.status.enable",
            f"fast_start.order.field.change.shop=__selector__&status={OrderStatus.IN_PROGRESS}.delivery_company.enable",
        ],
        # edit only the status field, only for in_progress orders
        "order_edit_shop_supplied": [
            f"fast_start.order.item.change.shop=__selector__&status={OrderStatus.SUPPLIED}"
        ],
        "order_edit_shop_supplied_disable_all": [
            f"fast_start.order.field.change.shop=__selector__&status={OrderStatus.SUPPLIED}.__all__.disable"
        ],
        "order_edit_shop_supplied_enable_fields": [
            f"fast_start.order.field.change.shop=__selector__&status={OrderStatus.SUPPLIED}.status.enable",
        ],
        # editing
        "order_edit_author": [
            f"fast_start.order.item.change.author=__selector__&status={OrderStatus.DRAFT}"
        ],
        "order_edit_shop": [
            f"fast_start.order.item.change.shop=__selector__&~status={OrderStatus.DRAFT}"
        ],
        "order_edit_delivery": [
            f"fast_start.order.item.change.delivery_company=__selector__&~status={OrderStatus.DRAFT}"
        ],
        "order_edit_all": ["fast_start.order.item.change.all"],
    }

    fast_start_roles = {
        "buyer": ["order_add", "order_view_author", "order_edit_author"],
        "shop_manager": [
            "order_view_shop_not_draft",
            "order_view_shop_not_draft_disable_all",
            "order_view_shop_not_draft_enable_fields",
            "order_edit_shop_in_progress",
            "order_edit_shop_in_progress_disable_all",
            "order_edit_shop_in_progress_enable_fields",
            "order_edit_shop_supplied",
            "order_edit_shop_supplied_disable_all",
            "order_edit_shop_supplied_enable_fields",
        ],
        "shop_finance": ["order_view_shop"],
        "delivery_manager": ["order_view_delivery", "order_edit_delivery"],
        "delivery_finance": ["order_view_delivery"],
        "support_1_line": ["order_view_all", "order_edit_all"],
        "tech_support": ["order_view_all", "order_edit_all", "order_delete_all"],
        "platform_finance": ["order_view_all"],
    }

    return setup_groups_and_roles(fast_start_groups, fast_start_roles)


@pytest.fixture
def process_async_response():
    from bazis.contrib.async_background.utils import redis, task_key

    def _run(task_id: str, timeout: int = 45) -> bytes:
        # Wait for status "completed" (processed by external consumer)
        for _ in range(timeout):
            if redis_data := redis.get(task_key(task_id)):
                data_dict = json.loads(redis_data.decode("utf-8"))
                if data_dict.get("status") == "completed":
                    return redis_data
            time.sleep(1)
        pytest.fail(f"Timeout waiting for async_background_response for task_id={task_id}")

    return _run


@pytest.fixture
def create_test_data(fast_start_setup_groups_and_roles):
    user = get_user_model()
    from fast_start.models import Order, OrderStatus, Shop

    shop = Shop.objects.create(name="Shop 1")
    roles = fast_start_setup_groups_and_roles

    try:
        manager = user.objects.create_user("manager", email="m@site.com", password="pass")
    except Exception:
        manager = user.objects.get(username="manager")
    manager.roles.add(roles["shop_manager"])
    manager.managed_shops.add(shop)

    try:
        buyer_1 = user.objects.create_user("buyer1", email="b1@site.com", password="pass")
    except Exception:
        buyer_1 = user.objects.get(username="buyer1")
    buyer_1.roles.add(roles["buyer"])

    try:
        buyer_2 = user.objects.create_user("buyer2", email="b2@site.com", password="pass")
    except Exception:
        buyer_2 = user.objects.get(username="buyer2")
    buyer_2.roles.add(roles["buyer"])

    order = Order.objects.get_or_create(
        description="Order", shop=shop, author=buyer_1, status=OrderStatus.IN_PROGRESS
    )[0]

    return shop, manager, buyer_1, buyer_2, order


@pytest.fixture(autouse=True)
def wait_for_background_tasks(request):
    """
    The consumer works with the test database: a test must not end (and flush the database)
    while the consumer still executes one of its tasks.
    """
    yield
    if "run_with_consumer" not in request.keywords:
        return
    from bazis.contrib.async_background.utils import TASK_KEY_PREFIX, redis

    for _ in range(60):
        statuses = {
            json.loads(value)["status"]
            for key in redis.scan_iter(f"{TASK_KEY_PREFIX}*")
            if (value := redis.get(key))
        }
        if not statuses - {"completed", "failed"}:
            break
        time.sleep(0.5)
    for key in redis.scan_iter(f"{TASK_KEY_PREFIX}*"):
        redis.delete(key)


def pytest_collection_modifyitems(config, items):
    """
    The tests marked `run_with_consumer` need Kafka and a running consumer
    (`python manage.py kafka_consumer_single` in `sample`, see CLAUDE.md).
    """
    from django.conf import settings

    if settings.KAFKA_ENABLED:
        return
    skip = pytest.mark.skip(reason="Kafka is not configured (BS_KAFKA_BOOTSTRAP_SERVERS)")
    for item in items:
        if "run_with_consumer" in item.keywords:
            item.add_marker(skip)
