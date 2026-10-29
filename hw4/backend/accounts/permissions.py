"""Role-based permission classes shared by the apps."""

from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_admin(user) -> bool:
    return bool(user and user.is_authenticated and user.is_admin)


def is_lecturer(user) -> bool:
    return bool(user and user.is_authenticated and user.is_lecturer)


class IsAdmin(BasePermission):
    """Only admins (user management)."""

    message = "Admin role required."

    def has_permission(self, request, view) -> bool:
        return is_admin(request.user)


class ReadOnly(BasePermission):
    """GET / HEAD / OPTIONS for everyone."""

    def has_permission(self, request, view) -> bool:
        return request.method in SAFE_METHODS
