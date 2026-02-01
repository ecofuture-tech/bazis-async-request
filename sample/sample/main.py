import os


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sample.settings")

from bazis.contrib.async_request.middleware import AsyncRequestMiddleware
from bazis.core.app import app


app.add_middleware(AsyncRequestMiddleware)
