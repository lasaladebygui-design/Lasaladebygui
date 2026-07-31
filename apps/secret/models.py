from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils.text import slugify

from apps.core.models import SingletonModel
from apps.movies.models import Movie


def _default_code_hash():
    return make_password("8888")


class TopSecretConfig(SingletonModel):
    """Código de acceso al maletín Tarantino. Se guarda hasheado (igual que
    una contraseña de usuario), nunca en texto plano — ni siquiera el admin
    puede ver el código actual, solo fijar uno nuevo."""

    access_code_hash = models.CharField(
        "código de acceso (hash)", max_length=128, default=_default_code_hash
    )

    class Meta:
        verbose_name = "Top Secret: código de acceso"
        verbose_name_plural = "Top Secret: código de acceso"

    def __str__(self):
        return "Código de acceso al maletín Tarantino"

    def check_code(self, code):
        return check_password(code, self.access_code_hash)

    def set_code(self, code):
        self.access_code_hash = make_password(code)


class Genre(models.Model):
    """Género o subgénero de una película secreta (terror, slasher, años
    80...). Igual que los tags de Artículos: texto libre, se crea sobre la
    marcha al escribirlo en el admin — no es una lista cerrada."""

    name = models.CharField("nombre", max_length=50, unique=True)
    slug = models.SlugField("slug", max_length=60, unique=True, blank=True)

    class Meta:
        verbose_name = "género/subgénero"
        verbose_name_plural = "géneros/subgéneros"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class SecretMovie(models.Model):
    """Entrada de la lista personal de Quentin: un número (para el selector),
    su propia nota (distinta de la media de votos o de IMDb) y un comentario.
    Puede enlazar opcionalmente a una película del catálogo (apps.movies)
    para reutilizar su portada."""

    number = models.PositiveIntegerField("número", unique=True)
    title = models.CharField("título", max_length=255)
    personal_rating = models.DecimalField("nota personal", max_digits=3, decimal_places=1)
    comment = models.TextField("comentario", blank=True)
    genres = models.ManyToManyField(Genre, verbose_name="géneros/subgéneros", blank=True, related_name="secret_movies")
    movie = models.ForeignKey(
        Movie, verbose_name="película del catálogo (opcional, para la portada)",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "película secreta"
        verbose_name_plural = "películas secretas"
        ordering = ["number"]

    def __str__(self):
        return f"#{self.number} — {self.title}"

    @property
    def poster_url(self):
        return self.movie.poster_url if self.movie else ""


class TierLevel(models.Model):
    """Un nivel/columna del tier list (S, A, B... o el nombre que se quiera).
    Nombre, color y orden se gestionan enteros desde la propia página del
    Tier List — no hace falta pasar por el admin para nada de esto."""

    name = models.CharField("nombre", max_length=30)
    color = models.CharField("color", max_length=7, default="#2DD4BF")
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        verbose_name = "nivel de tier list"
        verbose_name_plural = "Top Secret: niveles de tier list"
        ordering = ["order", "pk"]

    def __str__(self):
        return self.name


class TierListEntry(models.Model):
    """Tier list personal: películas agrupadas en niveles (ver `TierLevel`),
    ordenables dentro de cada nivel, editable tanto desde la propia web
    (buscar y añadir, arrastrar entre niveles) como desde el admin.
    `tier=None` es "Sin clasificar": donde caen las que se acaban de añadir
    hasta que se arrastran a un nivel real — así nunca se cuela una entrada
    nueva directamente en un nivel sin que nadie la haya puesto ahí. Al
    borrar un `TierLevel` (on_delete=SET_NULL), sus entradas vuelven aquí
    en vez de perderse."""

    tier = models.ForeignKey(
        TierLevel, verbose_name="nivel", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="entries",
    )
    title = models.CharField("título", max_length=255)
    order = models.PositiveIntegerField("orden dentro del nivel", default=0)
    movie = models.ForeignKey(
        Movie, verbose_name="película del catálogo (opcional, para la portada)",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "entrada de tier list"
        verbose_name_plural = "Top Secret: tier list"
        ordering = ["tier__order", "order", "title"]

    def __str__(self):
        return f"[{self.tier}] {self.title}"

    @property
    def poster_url(self):
        return self.movie.poster_url if self.movie else ""


class SecretPhoto(models.Model):
    """Tablón de fotos de Top Secret: cualquiera que haya entrado con el
    código puede subir una foto con una pequeña descripción (no hace falta
    tener cuenta; si el visitante ha iniciado sesión, se guarda quién la
    subió, pero eso no es un requisito para publicar)."""

    image = models.ImageField("foto", upload_to="secret_photos/")
    description = models.CharField("descripción", max_length=280, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="subida por",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField("subida", auto_now_add=True)

    class Meta:
        verbose_name = "foto del tablón"
        verbose_name_plural = "Top Secret: tablón de fotos"
        ordering = ["-created_at"]

    def __str__(self):
        return self.description or f"Foto #{self.pk}"
