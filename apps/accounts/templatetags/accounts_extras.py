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


@register.simple_tag
def rotating_quotes():
    """Pool de frases para el widget de 'frase de perfil' dinámica: se
    reutilizan las de Top Secret → Frases célebres (apps.secret) en vez de
    mantener un segundo listado, así el pool crece solo al añadir frases
    al juego."""
    from apps.secret.models import MovieQuote

    return list(MovieQuote.objects.values_list("quote", flat=True))
