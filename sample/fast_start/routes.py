from django.apps import apps
from django.contrib.auth import get_user_model

from fastapi import Depends, Request

from bazis.contrib.async_request.utils import require_async
from bazis.contrib.author.routes_abstract import AuthorRouteBase
from bazis.contrib.permit.routes_abstract import PermitRouteBase
from bazis.contrib.users.service import get_user_from_token
from bazis.core.routes_abstract.initial import inject_make
from bazis.core.routing import BazisRouter
from bazis.core.schemas import ApiAction, CrudApiAction, SchemaField, SchemaFields

from .schemas import SomeResponseItemSchema


User = get_user_model()

router = BazisRouter()


class OrderRouteSet(PermitRouteBase, AuthorRouteBase):
    """API route for handling Order operations with permission checks."""

    model = apps.get_model("fast_start", "Order")

    fields: dict[ApiAction, SchemaFields] = {
        CrudApiAction.RETRIEVE: SchemaFields(
            exclude={
                'dt_created': None,
                'dt_updated': None,
                'author': None,
                'author_updated': None,
                'shop': None,
            },
        ),
    }

class ShopRouteSet(AuthorRouteBase):
    """API route for handling Shop operations with permission checks."""

    model = apps.get_model("fast_start", "Shop")

    @inject_make(CrudApiAction.UPDATE)
    class InjectRequireAsync:
        _async_request = Depends(require_async)

    fields = {
        None: SchemaFields(
            include={
                "supplied_orders_count": SchemaField(
                    source="supplied_orders_count", required=False
                ),
            },
        ),
    }


class DeliveryCompanyRouteSet(PermitRouteBase, AuthorRouteBase):
    """API route for handling DeliveryCompany operations with permission checks."""

    model = apps.get_model("fast_start", "DeliveryCompany")


@router.get('/some-async-endpoint/', response_model=list[SomeResponseItemSchema])
async def some_async_endpoint(some_str: str, request: Request, user: User = Depends(get_user_from_token)):
    results = [{
        'some_str': some_str,
        'some_int': 1,
        'some_dict': {'some_float': 1.2}
    }]
    return results


@router.get('/some-sync-endpoint/', response_model=list[SomeResponseItemSchema])
def some_sync_endpoint(some_str: str, request: Request, user: User = Depends(get_user_from_token)):
    results = [{
        'some_str': some_str,
        'some_int': 1,
        'some_dict': {'some_float': 1.2}
    }]
    return results
