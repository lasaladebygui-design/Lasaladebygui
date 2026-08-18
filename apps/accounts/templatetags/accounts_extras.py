from django import template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def username_badge(user, fallback="usuario eliminado"):
    """Nombre de usuario coloreado según su rol (Admin/Gestor/Editor/Lector),
    para que el rango se note de un vistazo donde sea que aparezca un autor.
    Usa el nombre completo si lo tiene (p. ej. el Buzón de contacto), que
    para el resto de cuentas normales está vacío y no cambia nada."""
    if not user:
        return fallback
    display_name = user.get_full_name() or user.username
    return format_html('<span class="role-badge role-{}">{}</span>', user.role, display_name)


@register.simple_tag
def rotating_quotes():
    """Pool de frases para el widget de 'frase de perfil' dinámica: se
    reutilizan las de Juegos → Frases célebres (apps.games) en vez de
    mantener un segundo listado, así el pool crece solo al añadir frases
    al juego."""
    from apps.games.models import MovieQuote

    return list(MovieQuote.objects.values_list("quote", flat=True))
