"""Serializers for registration, login (JWT), profile and user management."""

from django.contrib.auth import password_validation
from django.db.models import Count
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


class UserPublicSerializer(serializers.ModelSerializer):
    """How a user appears inside other objects (lecture owner, question author)."""

    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "display_name", "role"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    """Full profile: what /api/auth/me/ and the admin user list return."""

    display_name = serializers.CharField(read_only=True)
    stats = serializers.SerializerMethodField(help_text="Counts of the user's lectures, questions and upvotes")

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name", "display_name", "role",
            "is_active", "date_joined", "last_login", "stats",
        ]
        read_only_fields = ["id", "username", "role", "is_active", "date_joined", "last_login"]

    def get_stats(self, user: User) -> dict:
        upvotes_received = (
            user.questions.aggregate(total=Count("upvotes"))["total"] or 0
        )
        return {
            "lectures": user.lectures.count(),
            "questions": user.questions.count(),
            "upvotes_given": user.upvotes.count(),
            "upvotes_received": upvotes_received,
        }


class UserAdminSerializer(UserSerializer):
    """Admins may also change the role and (de)activate accounts."""

    class Meta(UserSerializer.Meta):
        read_only_fields = ["id", "username", "date_joined", "last_login"]


class RegisterSerializer(serializers.ModelSerializer):
    """POST /api/auth/register/. Students and lecturers can self-register; admins are created by the seed."""

    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})
    role = serializers.ChoiceField(choices=[User.Role.STUDENT, User.Role.LECTURER], default=User.Role.STUDENT)

    class Meta:
        model = User
        fields = ["username", "email", "password", "first_name", "last_name", "role"]
        extra_kwargs = {"username": {"min_length": 3}}

    def validate_password(self, value: str) -> str:
        password_validation.validate_password(value)  # the AUTH_PASSWORD_VALIDATORS from settings
        return value

    def create(self, validated_data: dict) -> User:
        return User.objects.create_user(**validated_data)  # create_user hashes the password


class LoginSerializer(TokenObtainPairSerializer):
    """
    POST /api/auth/login/: username + password -> access + refresh tokens.

    SimpleJWT's serializer does the password check; this subclass adds the role
    and username as claims inside the token and the user profile to the response.
    """

    @classmethod
    def get_token(cls, user: User) -> RefreshToken:
        token = super().get_token(user)
        token["username"] = user.username
        token["role"] = user.role
        return token

    def validate(self, attrs: dict) -> dict:
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user, context=self.context).data
        return data


class TokenPairSerializer(serializers.Serializer):
    """Response shape of login / register / refresh (documentation only)."""

    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer(read_only=True)


class RefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text="The refresh token to revoke")


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})

    def validate_current_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value: str) -> str:
        password_validation.validate_password(value, self.context["request"].user)
        return value
