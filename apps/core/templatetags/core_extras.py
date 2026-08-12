from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

NBSP = " "


@register.filter
def wrap_after_period(text):
    """Cambia los espacios por espacios duros (NBSP) salvo el que va
    justo despues del primer punto -- asi, si la frase no cabe en una
    linea, el unico sitio por el que el navegador puede partirla es ahi
    (se usa en el eslogan del sitio, para no cortarlo a mitad de frase)."""
    escaped = escape(text)
    head, sep, tail = escaped.partition(". ")
    if not sep:
        return mark_safe(escaped.replace(" ", NBSP))
    head = head.replace(" ", NBSP)
    tail = tail.replace(" ", NBSP)
    return mark_safe(f"{head}. {tail}")
