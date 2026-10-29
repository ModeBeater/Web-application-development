"""
Who may do what with lectures and questions.

    anyone          read lectures and questions
    signed-in user  ask a question in an open lecture, upvote
    question author edit / delete their own question
    lecture owner   create lectures (lecturers), open/close, mark answered, delete questions and the lecture
    admin           everything

DRF calls `has_permission` for every request and `has_object_permission`
once the object is loaded (detail routes and actions).
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.permissions import is_admin, is_lecturer

from .models import Lecture, Question


def can_manage_lecture(user, lecture: Lecture) -> bool:
    return bool(user and user.is_authenticated and (lecture.owner_id == user.id or is_admin(user)))


def can_edit_question(user, question: Question) -> bool:
    return bool(
        user and user.is_authenticated
        and (question.author_id == user.id or can_manage_lecture(user, question.lecture))
    )


class LecturePermission(BasePermission):
    """Read for everyone; create for lecturers/admins; change/delete for the owner or an admin."""

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        if not request.user.is_authenticated:
            return False
        if view.action == "create":
            self.message = "Only lecturers can create lectures."
            return is_lecturer(request.user)
        if view.action == "questions":  # POST a question: any signed-in user
            return True
        return True  # object-level check follows

    def has_object_permission(self, request, view, lecture: Lecture) -> bool:
        if request.method in SAFE_METHODS or view.action == "questions":
            return True
        self.message = "Only the lecture owner or an admin can do this."
        return can_manage_lecture(request.user, lecture)


class QuestionPermission(BasePermission):
    """Read for everyone; upvote for signed-in users; edit/delete for the author, the lecture owner or an admin;
    marking as answered for the lecture owner or an admin."""

    def has_permission(self, request, view) -> bool:
        return request.method in SAFE_METHODS or request.user.is_authenticated

    def has_object_permission(self, request, view, question: Question) -> bool:
        if request.method in SAFE_METHODS or view.action == "upvote":
            return True
        if view.action == "answered":
            self.message = "Only the lecture owner or an admin can mark questions as answered."
            return can_manage_lecture(request.user, question.lecture)
        self.message = "Only the author, the lecture owner or an admin can change this question."
        return can_edit_question(request.user, question)
