from django.core.validators import RegexValidator
from django.db import models

hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Usa un color hexadecimal, ej. #0D9488",
)


def hex_field(default, verbose_name):
    return models.CharField(
        verbose_name,
        max_length=7,
        default=default,
        validators=[hex_color_validator],
    )


class SingletonModel(models.Model):
    """Modelo con una única fila en BD, editable desde el admin."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Theme(models.Model):
    """Un tema visual completo (colores, tipografía, espaciados).

    A diferencia de `SiteTheme` en versiones anteriores, aquí puede haber
    varios temas guardados a la vez: el admin elige cuál está activo desde
    `SiteConfig.active_theme`, y cada usuario puede opcionalmente fijar su
    propio tema en su perfil (`User.theme`). Añadir un tema nuevo (fila) no
    requiere tocar plantillas ni CSS: `theme.css` vuelca sus variables tal cual.
    """

    DEFAULT_SLUG = "cinephile"

    name = models.CharField("nombre", max_length=60, unique=True)
    slug = models.SlugField("identificador", max_length=60, unique=True)
    description = models.CharField("descripción breve", max_length=200, blank=True)

    # Fondo y superficies
    color_bg = hex_field("#0B1416", "fondo principal")
    color_surface = hex_field("#122120", "fondo de tarjetas/paneles")
    color_border = hex_field("#1F2E2D", "color de bordes")

    # Texto
    color_text = hex_field("#E5E7EB", "texto primario")
    color_text_muted = hex_field("#9CA3AF", "texto secundario")

    # Acento principal
    color_accent = hex_field("#2DD4BF", "acento principal (enlaces, titulares destacados)")
    color_accent_hover = hex_field("#5EEAD4", "acento principal — hover")
    color_on_accent = hex_field("#0B1416", "texto sobre el acento principal")

    # Acento secundario
    color_accent_secondary = hex_field("#FFB347", "acento secundario (botones, CTA)")
    color_accent_secondary_hover = hex_field("#FFDFAF", "acento secundario — hover")
    color_on_accent_secondary = hex_field("#241505", "texto sobre el acento secundario")

    # Estados
    color_danger = hex_field("#EF4444", "color de error/baneo")
    color_success = hex_field("#22C55E", "color de éxito")

    # Tipografía
    font_heading = models.CharField(
        "fuente de titulares", max_length=200, default="'Playfair Display', Georgia, serif"
    )
    font_body = models.CharField(
        "fuente de texto", max_length=200,
        default="'Inter', system-ui, -apple-system, sans-serif",
    )

    # Espaciados y forma
    space_unit = models.CharField("unidad de espaciado base", max_length=20, default="0.25rem")
    radius_base = models.CharField("radio de esquinas", max_length=20, default="0.6rem")
    max_content_width = models.CharField("ancho máximo de contenido", max_length=20, default="1200px")

    is_dark = models.BooleanField(
        "esquema oscuro",
        default=True,
        help_text="Afecta al renderizado nativo de formularios/scrollbars del navegador.",
    )

    class Meta:
        verbose_name = "tema visual"
        verbose_name_plural = "temas visuales"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SiteConfig(SingletonModel):
    """Ajustes generales del sitio, editables desde el admin."""

    tagline = models.CharField(
        "eslogan", max_length=200,
        default="Cine, pelis, series y debates. Todo en una misma sala.",
    )
    require_email_verification = models.BooleanField(
        "exigir verificación de email al registrarse",
        default=False,
        help_text="Si está activado, los usuarios nuevos deben confirmar su email antes de iniciar sesión.",
    )
    contact_email = models.EmailField(
        "email de contacto",
        blank=True,
        help_text="Dirección a la que llegan los mensajes del formulario de contacto.",
    )
    bizum_number = models.CharField(
        "número de Bizum",
        max_length=20,
        blank=True,
        default="684 127 181",
        help_text="Se muestra en el cartel de donaciones. Formato libre (espacios incluidos).",
    )
    show_intro_animation = models.BooleanField(
        "mostrar animación de proyector al entrar",
        default=True,
        help_text="Se muestra una vez por sesión de navegador. Desactívala para quitarla de toda la web.",
    )
    active_theme = models.ForeignKey(
        Theme,
        verbose_name="tema activo",
        help_text="Tema que se aplica a toda la web salvo que un usuario elija otro en su perfil.",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "Configuración del sitio"
        verbose_name_plural = "Configuración del sitio"

    def __str__(self):
        return "Configuración de La Sala de Bygui"


class ContactLink(models.Model):
    """Enlace de contacto alternativo (Instagram, WhatsApp, Twitter...),
    editable desde el admin: se puede añadir cualquiera que se quiera, no
    hay una lista cerrada de plataformas ("Otro" cubre cualquier caso no
    listado). Se muestra en /contacto/ como un botón con icono que lleva
    directo a esa red al pulsarlo."""

    class Platform(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        WHATSAPP = "whatsapp", "WhatsApp"
        TWITTER = "twitter", "Twitter/X"
        FACEBOOK = "facebook", "Facebook"
        TIKTOK = "tiktok", "TikTok"
        YOUTUBE = "youtube", "YouTube"
        TELEGRAM = "telegram", "Telegram"
        DISCORD = "discord", "Discord"
        EMAIL = "email", "Email"
        OTRO = "otro", "Otro"

    PLATFORM_ICONS = {
        "instagram": "📷", "whatsapp": "💬", "twitter": "🐦", "facebook": "📘",
        "tiktok": "🎵", "youtube": "▶️", "telegram": "✈️", "discord": "🎮",
        "email": "✉️", "otro": "🔗",
    }

    platform = models.CharField("plataforma", max_length=20, choices=Platform.choices, default=Platform.OTRO)
    label = models.CharField(
        "usuario o nombre a mostrar", max_length=100,
        help_text="Lo que se ve en el botón, ej: @lasaladebygui",
    )
    url = models.URLField(
        "enlace", help_text="A dónde lleva al pulsarlo: perfil, https://wa.me/34..., mailto:..., etc.",
    )
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        verbose_name = "enlace de contacto"
        verbose_name_plural = "Sitio: enlaces de contacto"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.get_platform_display()}: {self.label}"

    @property
    def icon(self):
        return self.PLATFORM_ICONS.get(self.platform, "🔗")


SESSION_THEME_KEY = "theme_slug"


def get_effective_theme(user=None, session=None):
    """Resuelve qué tema debe pintarse:
    1. El guardado en la cuenta del usuario (si ha iniciado sesión y tiene uno).
    2. El elegido desde el selector de la cabecera por un visitante sin
       cuenta, guardado en su sesión de navegador.
    3. El "tema activo" del sitio.
    4. Cinephile por su slug, y como último recurso un Theme() sin guardar
       con los valores por defecto, para que /theme.css nunca falle."""

    if user is not None and getattr(user, "is_authenticated", False) and getattr(user, "theme_id", None):
        return user.theme

    if session is not None:
        slug = session.get(SESSION_THEME_KEY)
        if slug:
            theme = Theme.objects.filter(slug=slug).first()
            if theme:
                return theme

    config = SiteConfig.load()
    if config.active_theme_id:
        return config.active_theme

    theme = Theme.objects.filter(slug=Theme.DEFAULT_SLUG).first()
    if theme:
        return theme

    return Theme.objects.first() or Theme()
