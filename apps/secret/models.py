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

    # No se elige a mano: se recalcula solo en cada guardado/borrado según la
    # nota (ver `_renumber_all`), así que no es editable desde el
    # formulario/admin — lo único editable para influir en el número es la
    # nota misma, o `tie_break` cuando dos tienen la misma nota.
    number = models.PositiveIntegerField("número", unique=True, editable=False, default=0)
    title = models.CharField("título", max_length=255)
    personal_rating = models.DecimalField("nota personal", max_digits=3, decimal_places=1)
    tie_break = models.PositiveIntegerField(
        "orden de desempate", default=0, blank=True,
        help_text="Solo importa entre dos películas con la misma nota: la de menor valor aquí sale antes en el número.",
    )
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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        type(self)._renumber_all()
        # `_renumber_all` opera sobre copias propias leídas de la base de
        # datos, así que no toca este `self` — sin este refresco, quien
        # acaba de guardar vería `number` desactualizado (p. ej. 0 para una
        # recién creada) hasta la próxima vez que se recargara desde la BD.
        self.refresh_from_db(fields=["number"])

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        type(self)._renumber_all()

    @classmethod
    def _renumber_all(cls):
        """El número de cada película es su posición al ordenar todas por
        nota (de mayor a menor); `tie_break` solo decide el orden entre dos
        con la misma nota. Se recalcula entero cada vez porque añadir/borrar
        o cambiar una nota puede desplazar a todas las demás.

        Se hace en dos pasadas (primero a valores temporales muy por encima
        de cualquier posición real, luego a su posición definitiva) para no
        chocar con el UniqueConstraint de `number` a media actualización —
        por ejemplo, si dos entradas intercambian su posición, escribirlas
        directamente en su sitio final una a una podría dejar un instante
        con dos filas repitiendo el mismo número. `number` es un
        PositiveIntegerField, así que el valor temporal tiene que ser
        positivo (no vale usar negativos)."""
        ordered = list(cls.objects.order_by("-personal_rating", "tie_break", "pk"))
        targets = [
            (movie, position) for position, movie in enumerate(ordered, start=1)
            if movie.number != position
        ]
        if not targets:
            return

        temp_base = len(ordered) + 1
        for offset, (movie, _) in enumerate(targets, start=1):
            movie.number = temp_base + offset
        cls.objects.bulk_update([movie for movie, _ in targets], ["number"])

        for movie, final_number in targets:
            movie.number = final_number
        cls.objects.bulk_update([movie for movie, _ in targets], ["number"])

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
