from apps.accounts.models import User

MANAGER_ROLES = (User.Role.ADMIN, User.Role.GESTOR)
AUTHOR_ROLES = (User.Role.ADMIN, User.Role.GESTOR, User.Role.EDITOR)


def can_create_articles(user):
    return user.is_authenticated and user.role in AUTHOR_ROLES


def can_edit_article(user, article):
    if not user.is_authenticated:
        return False
    if user.role in MANAGER_ROLES:
        return True
    return user.role == User.Role.EDITOR and article.author_id == user.pk


def can_delete_article(user, article):
    return can_edit_article(user, article)
