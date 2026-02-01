from django.utils.translation import gettext_lazy as _

from bazis.core.utils.apps import BaseConfig


class AsyncRequestConfig(BaseConfig):
    """Django AppConfig for the asynchronous background processing package (async_request)."""

    name = "bazis.contrib.async_request"
    verbose_name = _("AsyncRequest")
    default = True
