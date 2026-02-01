from bazis.contrib.author.models_abstract import AuthorMixin
from bazis.contrib.permit.models_abstract import (
    AnonymousUserPermitMixin,
    PermitSelectorMixin,
    UserPermitMixin,
)
from bazis.contrib.users.models_abstract import AnonymousUserAbstract, UserAbstract
from bazis.contrib.ws.models_abstract import UserWsMixin
from bazis.core.models_abstract import DtMixin, JsonApiMixin, UuidMixin


class User(
    UserWsMixin,
    UserPermitMixin,
    PermitSelectorMixin,
    AuthorMixin,
    DtMixin,
    UuidMixin,
    UserAbstract,
    JsonApiMixin,
):
    """Represents a user in the system, incorporating permissions, UUID, and user-specific attributes."""

    pass


class AnonymousUser(AnonymousUserPermitMixin, AnonymousUserAbstract):
    """Represents an anonymous user in the system, incorporating permissions and anonymous user-specific attributes."""

    pass
