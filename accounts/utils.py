import uuid


from calendar import timegm
from django.utils import timezone


from django.conf import settings
from django.contrib.auth import get_user_model




User = get_user_model()


def get_username_field():
    try:
        username_field = User.USERNAME_FIELD
    except AttributeError:
        username_field = "username"

    return username_field


def get_username(user):
    try:
        username = user.get_username()
    except AttributeError:
        username = user.username

    return username


def jwt_get_secret_key(payload=None):
    """
    For enhanced security we want to use a secret key based on user.
    This way you have an option to logout only this user if:
        - token is compromised
        - password is changed
        - etc.
    """
    if settings.JWT_AUTH["JWT_GET_USER_SECRET_KEY"]:  # noqa: N806
        user = User.objects.get(pk=payload.get("user_id"))
        key = str(user.get_jwt_key())
        return key
    return settings.JWT_AUTH["JWT_SECRET_KEY"]


def jwt_payload_handler(user):
    """
    warnings.warn(
            'The following fields will be removed in the future: '
            '`email` and `user_id`. ',
            DeprecationWarning
        )
    """
    username_field = get_username_field()
    username = get_username(user)

    payload = {
        "user_id": user.pk,
        "username": username,
        "exp": timezone.now().utcnow() + settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"],
    }
    if hasattr(user, "email"):
        payload["email"] = user.email

    if isinstance(user.pk, uuid.UUID):
        payload["user_id"] = str(user.pk)
    permission = []
    if hasattr(user, "custom_permissions"):
        perm = user.custom_permissions.all()
        for per in perm:
            permission.append(per.name)
        payload["permissions"] = permission
    if settings.SIMPLE_JWT["JWT_ALLOW_REFRESH"]:
        payload["orig_iat"] = timegm(timezone.now().utctimetuple())

    return payload
