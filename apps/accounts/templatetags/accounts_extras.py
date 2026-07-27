from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def username_badge(user, fallback="usuario eliminado"):
    """Nombre de usuario coloreado según su rol (Admin/Gestor/Editor/Lector),
    para que el rango se note de un vistazo donde sea que aparezca un autor."""
    if not user:
        return fallback
    return format_html('<span class="role-badge role-{}">{}</span>', user.role, user.username)
