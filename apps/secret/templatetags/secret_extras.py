from django import template

from ..models import TopSecretTab

register = template.Library()


@register.simple_tag
def rating_color(movie, rating_config):
    """Color hex para la nota grande, según los umbrales configurados en
    TopSecretConfig (editable desde el admin, ver apps/secret/models.py)."""
    return rating_config.rating_color(movie.personal_rating)


@register.simple_tag
def topsecret_tab_order():
    """Orden configurado de las pestañas de arriba del maletín (ver
    TopSecretTab, reordenable arrastrando desde el admin) — una lista de
    claves ("lista", "calendario"...) que _shell.html recorre para
    decidir en qué orden pintar cada pestaña."""
    return TopSecretTab.ordered_keys()
