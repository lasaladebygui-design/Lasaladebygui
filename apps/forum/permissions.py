from apps.accounts.models import User

MODERATOR_ROLES = (User.Role.ADMIN, User.Role.GESTOR)


def is_moderator(user):
    return user.is_authenticated and user.role in MODERATOR_ROLES


def can_post(user):
    return user.is_authenticated and user.is_active


def can_delete_comment(user, comment):
    if not user.is_authenticated:
        return False
    return is_moderator(user) or comment.author_id == user.pk


def can_moderate_thread(user):
    return is_moderator(user)
