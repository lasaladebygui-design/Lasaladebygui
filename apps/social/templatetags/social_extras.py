import hashlib

from django import template
from django.utils.html import format_html

register = template.Library()

# Mismo espíritu que el avatar generado del Buzón de contacto (sobre sobre
# fondo de color, apps.social.models._generate_contact_bot_avatar) pero para
# cada remitente anónimo dentro de ese buzón: sin cuenta no hay foto de
# perfil real, así que un círculo con sus iniciales sobre un color estable
# (el mismo nombre siempre sale con el mismo color) ayuda a distinguir de un
# vistazo quién escribió qué, en vez de que todos se vean igual.
_PALETTE = ["#8C2F39", "#2D6A4F", "#1D4E89", "#7B3F61", "#B5651D", "#3D348B", "#4C7A88", "#9E2A2B"]


@register.simple_tag
def contact_avatar(name):
    label = (name or "Anónimo").strip() or "Anónimo"
    parts = label.split()
    initials = ((parts[0][0] if parts else "") + (parts[1][0] if len(parts) > 1 else "")).upper() or "?"
    color = _PALETTE[int(hashlib.md5(label.encode()).hexdigest(), 16) % len(_PALETTE)]
    return format_html('<span class="contact-avatar" style="background:{}">{}</span>', color, initials)
