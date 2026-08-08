from django import template

from ..permissions import can_delete_article

register = template.Library()


@register.filter
def can_delete(article, user):
    return can_delete_article(user, article)
