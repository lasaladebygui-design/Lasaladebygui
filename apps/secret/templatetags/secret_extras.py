from django import template

register = template.Library()


@register.simple_tag
def rating_color(movie, rating_config):
    """Color hex para la nota grande, según los umbrales configurados en
    TopSecretConfig (editable desde el admin, ver apps/secret/models.py)."""
    return rating_config.rating_color(movie.personal_rating)
