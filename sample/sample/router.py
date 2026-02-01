from bazis.core.routing import BazisRouter


router = BazisRouter(prefix="/api/v1")

router.register("fast_start.router")
router.register("bazis.contrib.permit.router")
router.register("bazis.contrib.users.router")
router.register("bazis.contrib.async_background.router")
