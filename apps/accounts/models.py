import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

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
    theme = models.ForeignKey(
        Theme,
        verbose_name="tema personal",
        help_text="Si lo dejas vacío, se usa el tema activo del sitio.",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.username or self.email

    def save(self, *args, **kwargs):
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
