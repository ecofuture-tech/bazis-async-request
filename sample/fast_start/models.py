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

from collections.abc import Iterable
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from bazis.contrib.author.models_abstract import AuthorMixin
from bazis.contrib.permit.models_abstract import PermitModelMixin, PermitSelectorMixin
from bazis.contrib.users import get_user_model
from bazis.core.models_abstract import DtMixin, JsonApiMixin, UuidMixin
from bazis.core.utils.orm import DependsCalc, FieldDynamic, calc_property


User = get_user_model()


class OrderStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    IN_PROGRESS = "in_progress", _("In Progress")
    SUPPLIED = "supplied", _("Supplied")


class Shop(PermitSelectorMixin, AuthorMixin, DtMixin, UuidMixin, JsonApiMixin):
    """Represents a shop in the marketplace, with linked managers."""

    name = models.CharField(_("Name"), max_length=255)
    manager = models.ManyToManyField(User, related_name="managed_shops")

    @classmethod
    def get_selector_for_user(cls, user: User) -> Iterable[int]:
        """Returns a list of shop IDs the user manages."""
        return list(user.managed_shops.values_list("id", flat=True))

    @calc_property(
        [
            FieldDynamic(
                source="orders",
                func="Count",
                alias="supplied_orders_count",
                query=Q(status=OrderStatus.SUPPLIED),
            ),
        ],
        as_filter=True,
    )
    def supplied_orders_count(self, dc: DependsCalc) -> Decimal | None:
        return dc.data.supplied_orders_count

    class Meta:
        verbose_name = _("Shop")
        verbose_name_plural = _("Shops")


class DeliveryCompany(PermitSelectorMixin, AuthorMixin, DtMixin, UuidMixin, JsonApiMixin):
    """Represents a delivery company in the marketplace, with linked managers."""

    name: str = models.CharField(_("Name"), max_length=255)
    manager: models.ManyToManyField = models.ManyToManyField(
        User, related_name="managed_delivery_companies"
    )

    @classmethod
    def get_selector_for_user(cls, user: User) -> Iterable[int]:
        """Returns a list of delivery company IDs the user manages."""
        return list(user.managed_delivery_companies.values_list("id", flat=True))

    class Meta:
        verbose_name = _("Delivery company")
        verbose_name_plural = _("Delivery companies")


class Order(PermitModelMixin, AuthorMixin, DtMixin, UuidMixin, JsonApiMixin):
    """Represents an order placed by a client, linked to a shop and a delivery company."""

    description: str = models.TextField()
    shop: Shop = models.ForeignKey(
        "Shop",
        verbose_name="Shop",
        null=False,
        blank=False,
        db_index=True,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    delivery_company: DeliveryCompany | None = models.ForeignKey(
        "DeliveryCompany",
        verbose_name="Delivery Company",
        blank=True,
        null=True,
        db_index=True,
        on_delete=models.SET_NULL,
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.DRAFT,
    )

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
