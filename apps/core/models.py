from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify

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

    # Animación de inicio
    color_intro_light = hex_field(
        "#FFDFAF", "luz del proyector en la animación de inicio",
    )
    color_intro_lamp = hex_field(
        "#B4A9E8", "lámpara en la animación de inicio",
    )
    color_intro_chair = hex_field(
        "#8D7FCB", "sillón en la animación de inicio",
    )

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
    is_published = models.BooleanField(
        "publicado",
        default=True,
        help_text=(
            "Si lo desmarcas, desaparece del selector de temas del sitio (pero sigue "
            "funcionando para quien ya lo tuviera puesto, y se puede seguir usando "
            "como tema activo del sitio desde Configuración del sitio)."
        ),
    )
    order = models.PositiveIntegerField(
        "orden", default=0,
        help_text="Orden en el que aparece en el selector de temas — menor va primero.",
    )

    class Meta:
        verbose_name = "tema visual"
        verbose_name_plural = "temas visuales"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "tema"
            candidate = base
            suffix = 0
            while Theme.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                suffix += 1
                candidate = f"{base}-{suffix}"
            self.slug = candidate
        super().save(*args, **kwargs)


class SiteConfig(SingletonModel):
    """Ajustes generales del sitio, editables desde el admin."""

    tagline = models.CharField(
        "eslogan", max_length=200,
        default="Cine, pelis, series y debates. Todo en una misma sala.",
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
    notifications_bell_enabled = models.BooleanField(
        "activar campanita de avisos",
        default=True,
        help_text="Desactívala para quitar la campanita de avisos de toda la web (mensajes, amistad, artículos, tienda...).",
    )
    recent_activity_enabled = models.BooleanField(
        "mostrar actividad reciente en la portada",
        default=True,
        help_text="Últimos comentarios de Artículos y del Foro, mezclados por fecha, en la sala principal.",
    )
    intro_sound = models.FileField(
        "sonido de la intro",
        upload_to="intro_sound/",
        blank=True,
        help_text=(
            "Opcional — un mp3/ogg/wav corto. Si lo subes, sustituye al sonido de carrete "
            "generado por defecto. Déjalo vacío para volver al de siempre."
        ),
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
        SPOTIFY = "spotify", "Spotify"
        EMAIL = "email", "Email"
        OTRO = "otro", "Otro"

    PLATFORM_ICONS = {
        "instagram": "📷", "whatsapp": "💬", "twitter": "🐦", "facebook": "📘",
        "tiktok": "🎵", "youtube": "▶️", "telegram": "✈️", "discord": "🎮",
        "spotify": "🎧", "email": "✉️", "otro": "🔗",
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
        verbose_name_plural = "enlaces de contacto"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.get_platform_display()}: {self.label}"

    @property
    def icon(self):
        return self.PLATFORM_ICONS.get(self.platform, "🔗")


class Announcement(models.Model):
    """Aviso corto del equipo, visible para todos en la campanita de la
    cabecera hasta que cada usuario lo marca como leído (al abrir el
    desplegable) — pensado para avisos rápidos que no necesitan llegar al
    correo (para eso está "Enviar un email" en el admin de usuarios)."""

    title = models.CharField("título", max_length=120)
    body = models.TextField("mensaje", blank=True)
    url = models.CharField(
        "enlace", max_length=300, blank=True,
        help_text="Opcional — a dónde lleva al pulsarlo. Puede ser una ruta interna (/articulos/) o una URL completa.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="publicado por",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField("publicado", auto_now_add=True)
    read_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name="leído por", blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "aviso"
        verbose_name_plural = "avisos"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class FavoriteQuote(models.Model):
    """Almacén personal de frases de películas o series — solo un sitio
    donde apuntarlas desde el admin cuando una te encanta, no se muestra
    en ninguna parte pública del sitio (para eso está el juego de Frases
    célebres, que es otra cosa)."""

    text = models.TextField("frase")
    source = models.CharField("película o serie", max_length=200, blank=True)
    notes = models.TextField("notas", blank=True, help_text="Contexto, por qué te gustó, quién la dice...")
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "frase favorita"
        verbose_name_plural = "frases favoritas"
        ordering = ["-created_at"]

    def __str__(self):
        return self.text[:60]


class PersonalNote(models.Model):
    """Apuntes personales sueltos desde el admin — un cuaderno rápido sin
    más estructura que un título y texto libre, para ideas o cosas que
    apuntar que no encajan en ningún otro sitio del admin."""

    title = models.CharField("título", max_length=150)
    body = models.TextField("apunte", blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)
    updated_at = models.DateTimeField("última edición", auto_now=True)

    class Meta:
        verbose_name = "apunte personal"
        verbose_name_plural = "apuntes personales"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title


class AdminMenuOrder(SingletonModel):
    """Orden a mano del menú lateral del admin (arrastrado desde Sitio →
    Orden del menú), aplicado en tiempo real por
    apps.core.middleware.AdminMenuOrderMiddleware sobre
    JAZZMIN_SETTINGS["order_with_respect_to"]. Vacío = se usa el orden de
    fábrica (config.settings.DEFAULT_ADMIN_MENU_ORDER)."""

    order = models.JSONField("orden", default=list, blank=True)

    class Meta:
        verbose_name = "orden del menú del admin"
        verbose_name_plural = "orden del menú del admin"


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
