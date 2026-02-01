from django.contrib import admin

from bazis.core.admin_abstract import DtAdminMixin

from .models import Order


@admin.register(Order)
class OrderAdmin(DtAdminMixin, admin.ModelAdmin):
    list_display = ("id", "dt_created")
