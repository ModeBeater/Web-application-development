"""
Users and roles.

The project uses a custom user model from the start (Django recommends it even
when the only addition is a `role` column). Three roles:

    student   asks questions and upvotes; edits and deletes their own questions
    lecturer  everything a student can, plus creates lectures and manages their own
              (open/close, mark answered, delete questions, delete the lecture)
    admin     everything, including other users' lectures and user management

Authorization is enforced in qa/permissions.py and accounts/permissions.py;
the role is also put into the JWT so clients can adapt their UI.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        LECTURER = "lecturer", "Lecturer"
        ADMIN = "admin", "Admin"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"

    @property
    def display_name(self) -> str:
        """What other users see: full name when given, otherwise the username."""
        return self.get_full_name() or self.username

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_lecturer(self) -> bool:
        return self.role == self.Role.LECTURER or self.is_admin
