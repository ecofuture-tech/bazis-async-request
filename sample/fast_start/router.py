
from bazis.core.routing import BazisRouter

from .routes import DeliveryCompanyRouteSet, OrderRouteSet, ShopRouteSet
from .routes import router as some_router


router = BazisRouter(tags=["Fast_Start"])

router.register(ShopRouteSet.as_router())
router.register(DeliveryCompanyRouteSet.as_router())
router.register(OrderRouteSet.as_router())
router.register(some_router)
