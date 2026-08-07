import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.core.models import Theme


class User(AbstractUser):
    """Usuario de La Sala de Bygui.

    El rol determina el acceso al admin y, a partir de la Fase 2, los
    permisos sobre artículos y foro. `Baneado` es un rol más (no un flag
    aparte): is_active se deriva siempre de él, así que cambiar el rol
    ES la acción de banear/desbanear.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        GESTOR = "gestor", "Gestor"
        EDITOR = "editor", "Editor"
        LECTOR = "lector", "Lector"
        BANEADO = "baneado", "Baneado"

    # Usamos el email como identificador de acceso; el username se
    # autogenera y solo sirve como handle público (perfil, autoría...).
    username = models.CharField("nombre de usuario", max_length=150, unique=True, blank=True)
    email = models.EmailField("correo electrónico", unique=True)
    role = models.CharField("rol", max_length=20, choices=Role.choices, default=Role.LECTOR)
    email_verified = models.BooleanField("email verificado", default=False)
    bio = models.TextField("biografía", blank=True)
    avatar = models.ImageField("foto de perfil", upload_to="avatars/", blank=True, null=True)
    quote_streak_best = models.PositiveIntegerField(
        "mejor racha en Frases célebres", default=0,
        help_text="Récord del juego de Top Secret. Se actualiza solo al jugar.",
    )
    rating_duel_streak_best_movie = models.PositiveIntegerField(
        "mejor racha en Cuál está mejor valorada (películas)", default=0,
        help_text="Récord del juego de Juegos. Se actualiza solo al jugar.",
    )
    rating_duel_streak_best_tv = models.PositiveIntegerField(
        "mejor racha en Cuál está mejor valorada (series)", default=0,
        help_text="Récord del juego de Juegos. Se actualiza solo al jugar.",
    )
    trivia_streak_best = models.PositiveIntegerField(
        "mejor racha en Trivial", default=0, help_text="Récord del juego de Juegos. Se actualiza solo al jugar.",
    )
    emoji_streak_best = models.PositiveIntegerField(
        "mejor racha en Emoji", default=0, help_text="Récord del juego de Juegos. Se actualiza solo al jugar.",
    )
    bad_description_streak_best = models.PositiveIntegerField(
        "mejor racha en Malas descripciones", default=0, help_text="Récord del juego de Juegos. Se actualiza solo al jugar.",
    )
    actor_streak_best = models.PositiveIntegerField(
        "mejor racha en Cuál tiene al actor/actriz", default=0, help_text="Récord del juego de Juegos. Se actualiza solo al jugar.",
    )
    true_false_streak_best = models.PositiveIntegerField(
        "mejor racha en Verdadero o falso", default=0, help_text="Récord del juego de Juegos. Se actualiza solo al jugar.",
    )
    revenue_duel_streak_best = models.PositiveIntegerField(
        "mejor racha en Cuál recaudó más", default=0, help_text="Récord del juego de Juegos. Se actualiza solo al jugar.",
    )
    theme = models.ForeignKey(
        Theme,
        verbose_name="tema personal",
        help_text="Si lo dejas vacío, se usa el tema activo del sitio.",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    show_intro_animation = models.BooleanField(
        "animación de intro", null=True, blank=True, default=None,
        help_text="Vacío = usa el ajuste del sitio. Marcado/desmarcado = lo fuerza para ti, ajustable en Ajustes.",
    )
    hide_pwa_install_prompt = models.BooleanField(
        "ocultar sugerencia de instalar la app", default=False,
    )
    essential_note = models.TextField(
        "por qué son imprescindibles", blank=True,
        help_text="Un único texto para todo el apartado (no por película). Visible para cualquiera que vea tu perfil.",
    )
    suggested_note = models.TextField(
        "por qué las recomiendas", blank=True,
        help_text="Un único texto para todo el apartado (no por película). Visible para cualquiera que vea tu perfil.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.username or self.email

    def save(self, *args, **kwargs):
        previous_role = None
        if self.pk:
            previous_role = type(self).objects.filter(pk=self.pk).values_list("role", flat=True).first()

        # El email es el identificador de acceso (USERNAME_FIELD): normalizar
        # a minúsculas aquí, al guardar, evita que "User@x.com" y
        # "user@x.com" acaben siendo dos cuentas distintas — el login ya es
        # insensible a mayúsculas (ver EmailBackend), pero esto lo es desde
        # la raíz para cualquier email nuevo.
        if self.email:
            self.email = self.email.lower()

        if not self.username:
            self.username = self._generate_username()

        if self.role == self.Role.ADMIN:
            self.is_staff = True
            self.is_superuser = True
        else:
            self.is_superuser = False
            self.is_staff = self.role in (self.Role.GESTOR, self.Role.EDITOR)

        # is_active se deriva por completo del rol: "baneado" == inactivo.
        self.is_active = self.role != self.Role.BANEADO

        super().save(*args, **kwargs)
        self._sync_gestor_group()

        # El baneo no solo bloquea futuros inicios de sesión (is_active):
        # si ya había una sesión abierta, se corta al instante borrando sus
        # sesiones activas — en su siguiente petición, Django ya no lo
        # reconoce como logueado.
        if self.role == self.Role.BANEADO and previous_role != self.Role.BANEADO:
            self._kick_active_sessions()

    def _kick_active_sessions(self):
        from django.contrib.sessions.models import Session

        for session in Session.objects.filter(expire_date__gte=timezone.now()):
            if str(session.get_decoded().get("_auth_user_id")) == str(self.pk):
                session.delete()

    def _sync_gestor_group(self):
        """El rol Gestor da además acceso de gestión del foro (Thread y
        ThreadComment) dentro del panel /admin/, aparte de la moderación que
        ya tiene en la web pública. Se sincroniza en cada guardado: si deja
        de ser Gestor, se le quita del grupo (pero el grupo y sus permisos
        se conservan para el resto de Gestores)."""
        from django.contrib.auth.models import Group, Permission
        from django.contrib.contenttypes.models import ContentType

        from apps.forum.models import Thread, ThreadComment

        group, _ = Group.objects.get_or_create(name="Gestor")
        forum_perms = Permission.objects.filter(
            content_type__in=[
                ContentType.objects.get_for_model(Thread),
                ContentType.objects.get_for_model(ThreadComment),
            ]
        )
        group.permissions.set(forum_perms)

        if self.role == self.Role.GESTOR:
            self.groups.add(group)
        else:
            self.groups.remove(group)

    def _generate_username(self):
        base = (self.email.split("@")[0] or "usuario").lower()
        base = "".join(ch for ch in base if ch.isalnum() or ch in "._-") or "usuario"
        candidate = base
        Model = type(self)
        suffix = 0
        while Model.objects.filter(username=candidate).exclude(pk=self.pk).exists():
            suffix += 1
            candidate = f"{base}{suffix}"
        return candidate

    @property
    def is_baneado(self):
        return self.role == self.Role.BANEADO


class FavoriteMovie(models.Model):
    """Película o serie destacada en el perfil de un usuario: "Mis
    imprescindibles" o "Sugeridas" (recomendaciones), sin límite de
    cuántas. Reutiliza el catálogo de `apps.movies` (misma búsqueda en vivo
    contra TMDb que ya se usa en la tier list de Top Secret) para tener
    título y portada sin duplicar datos."""

    class Category(models.TextChoices):
        ESSENTIAL = "essential", "Imprescindible"
        SUGGESTED = "suggested", "Sugerida"

    user = models.ForeignKey(
        "accounts.User", verbose_name="usuario", on_delete=models.CASCADE, related_name="favorite_movies",
    )
    category = models.CharField("categoría", max_length=10, choices=Category.choices)
    movie = models.ForeignKey(
        "movies.Movie", verbose_name="película", on_delete=models.CASCADE, related_name="+",
    )
    order = models.PositiveIntegerField("orden", default=0)
    created_at = models.DateTimeField("añadida", auto_now_add=True)

    class Meta:
        verbose_name = "película destacada del perfil"
        verbose_name_plural = "perfiles: películas destacadas"
        ordering = ["category", "order", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "category", "movie"], name="una_vez_por_usuario_y_categoria"),
        ]

    def __str__(self):
        return f"{self.user} — {self.get_category_display()}: {self.movie}"


class EmailVerificationToken(models.Model):
    """Token de un solo uso para confirmar el email de un usuario."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="verification_tokens")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Token de verificación de {self.user}"

    @property
    def is_used(self):
        return self.used_at is not None


class PushSubscription(models.Model):
    """Suscripción de un dispositivo/navegador a las notificaciones push
    (Web Push estándar — funciona en Android/escritorio directamente, y en
    iPhone si la web está instalada como app en la pantalla de inicio). Un
    mismo usuario puede tener varias, una por dispositivo/navegador."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField("endpoint", max_length=500, unique=True)
    p256dh = models.CharField("clave p256dh", max_length=255)
    auth = models.CharField("clave auth", max_length=255)
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "suscripción push"
        verbose_name_plural = "suscripciones push"

    def __str__(self):
        return f"Suscripción de {self.user}"


class GoogleCalendarConnection(models.Model):
    """Conexión OAuth de un usuario con su Google Calendar (integración
    real, no el .ics manual): guarda el refresh_token que Google entrega al
    conceder el permiso, que no caduca salvo que el usuario lo revoque desde
    su cuenta de Google. El access_token sí caduca (normalmente en 1h) y se
    renueva solo con el refresh_token cuando hace falta."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="google_calendar_connection")
    refresh_token = models.CharField("refresh token", max_length=255)
    access_token = models.CharField("access token", max_length=255, blank=True)
    access_token_expires_at = models.DateTimeField("caduca", null=True, blank=True)
    connected_at = models.DateTimeField("conectado", auto_now_add=True)

    class Meta:
        verbose_name = "conexión con Google Calendar"
        verbose_name_plural = "conexiones con Google Calendar"

    def __str__(self):
        return f"Google Calendar de {self.user}"
