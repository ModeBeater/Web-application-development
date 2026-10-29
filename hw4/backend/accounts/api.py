"""
Authentication and user endpoints.

    POST /api/auth/register/   create an account, returns the user + a token pair (auto-login)
    POST /api/auth/login/      username + password -> {"access", "refresh", "user"}
    POST /api/auth/refresh/    refresh -> new {"access", "refresh"}; the used refresh token is revoked
    POST /api/auth/logout/     revoke a refresh token (the access token simply expires)
    GET  /api/auth/me/         profile of the caller (with stats)       PATCH: edit name / email
    POST /api/auth/me/password/   change the password

    /api/users/   admin only: list / retrieve / update role & active flag / delete
"""

from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .permissions import IsAdmin
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    PasswordChangeSerializer,
    RefreshRequestSerializer,
    RegisterSerializer,
    TokenPairSerializer,
    UserAdminSerializer,
    UserSerializer,
)

User = get_user_model()


def token_pair_for(user) -> dict:
    """A fresh refresh/access pair with the role claim (same claims as login)."""
    refresh = LoginSerializer.get_token(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


# ---------------------------------------------------------------------------
# Register / login / refresh / logout
# ---------------------------------------------------------------------------


@extend_schema(
    tags=["auth"],
    summary="Register",
    description="Creates a student or lecturer account and signs it in: the response carries a token pair.",
    request=RegisterSerializer,
    responses={201: TokenPairSerializer, 400: OpenApiResponse(description="Validation errors per field")},
    auth=[],
)
@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    data = {**token_pair_for(user), "user": UserSerializer(user, context={"request": request}).data}
    return Response(data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    post=extend_schema(
        tags=["auth"],
        summary="Login",
        description="Username + password → `access` (15 min) and `refresh` (7 days) tokens plus the user profile. "
        "Send `Authorization: Bearer <access>` with every request.",
        responses={200: TokenPairSerializer, 401: OpenApiResponse(description="Wrong username or password")},
        auth=[],
    )
)
class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer


@extend_schema_view(
    post=extend_schema(
        tags=["auth"],
        summary="Refresh tokens",
        description="Exchanges a refresh token for a new access **and** refresh token. The old refresh token is "
        "blacklisted (rotation), so each refresh token can be used once.",
        request=RefreshRequestSerializer,
        responses={200: TokenPairSerializer, 401: OpenApiResponse(description="Token is invalid, expired or revoked")},
        auth=[],
    )
)
class RefreshView(TokenRefreshView):
    pass


@extend_schema(
    tags=["auth"],
    summary="Logout",
    description="Revokes the given refresh token (adds it to the blacklist). The access token stays valid until "
    "it expires, which is why access tokens are short-lived.",
    request=LogoutSerializer,
    responses={205: OpenApiResponse(description="Refresh token revoked"), 400: OpenApiResponse(description="Invalid token")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    serializer = LogoutSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        RefreshToken(serializer.validated_data["refresh"]).blacklist()
    except TokenError as exc:
        raise ValidationError({"refresh": [str(exc)]}) from exc
    return Response(status=status.HTTP_205_RESET_CONTENT)


# ---------------------------------------------------------------------------
# Profile ("personal cabinet")
# ---------------------------------------------------------------------------


@extend_schema(methods=["GET"], tags=["auth"], summary="My profile", description="The signed-in user with activity counters.", responses=UserSerializer)
@extend_schema(methods=["PATCH"], tags=["auth"], summary="Edit my profile", description="Change first/last name or email.", request=UserSerializer, responses=UserSerializer)
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    if request.method == "GET":
        return Response(UserSerializer(request.user, context={"request": request}).data)
    serializer = UserSerializer(request.user, data=request.data, partial=True, context={"request": request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@extend_schema(
    tags=["auth"],
    summary="Change my password",
    request=PasswordChangeSerializer,
    responses={200: TokenPairSerializer},
    description="Checks the current password, applies the validators to the new one and returns a fresh token pair.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    request.user.set_password(serializer.validated_data["new_password"])
    request.user.save(update_fields=["password"])
    data = {**token_pair_for(request.user), "user": UserSerializer(request.user, context={"request": request}).data}
    return Response(data)


# ---------------------------------------------------------------------------
# User management (admin)
# ---------------------------------------------------------------------------


@extend_schema_view(
    list=extend_schema(tags=["users"], summary="List users", description="Admin only. `?role=`, `?is_active=`, `?search=`, `?ordering=`."),
    retrieve=extend_schema(tags=["users"], summary="Get a user"),
    partial_update=extend_schema(tags=["users"], summary="Change a user's role, active flag or name"),
    destroy=extend_schema(tags=["users"], summary="Delete a user", description="Their lectures, questions and upvotes go with them."),
)
class UserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.all()
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdmin]
    http_method_names = ["get", "patch", "delete", "head", "options"]
    filterset_fields = ["role", "is_active"]
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering_fields = ["id", "username", "date_joined", "role"]
    ordering = ["id"]

    def perform_update(self, serializer):
        target = serializer.instance
        me_ = self.request.user
        if target == me_ and serializer.validated_data.get("role", me_.role) != User.Role.ADMIN:
            raise ValidationError({"role": ["You cannot remove your own admin role."]})
        if target == me_ and serializer.validated_data.get("is_active", True) is False:
            raise ValidationError({"is_active": ["You cannot deactivate yourself."]})
        serializer.save()

    def perform_destroy(self, user):
        if user == self.request.user:
            raise ValidationError({"detail": "You cannot delete yourself."})
        user.delete()
