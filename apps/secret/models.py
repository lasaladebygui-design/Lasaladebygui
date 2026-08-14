from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.files.storage import storages
from django.db import models
from django.utils.text import slugify

from apps.core.models import SingletonModel, hex_field
from apps.movies.models import Movie


def _default_code_hash():
    return make_password("8888")


class TopSecretConfig(SingletonModel):
    """Código de acceso al maletín Tarantino (se guarda hasheado, nunca en
    texto plano) y punto de entrada a los tramos de color de la nota de la
    lista completa (ver RatingColorBand) — cuántos tramos haya y de qué
    nota a qué nota va cada uno se decide entero desde el admin."""

    access_code_hash = models.CharField(
        "código de acceso (hash)", max_length=128, default=_default_code_hash
    )

    class Meta:
        verbose_name = "código de acceso y colores"
        verbose_name_plural = "código de acceso y colores"

    def __str__(self):
        return "Código de acceso al maletín Tarantino"

    def check_code(self, code):
        return check_password(code, self.access_code_hash)

    def set_code(self, code):
        self.access_code_hash = make_password(code)

    def rating_color(self, personal_rating):
        band = (
            self.rating_bands.filter(min_rating__lte=personal_rating, max_rating__gte=personal_rating)
            .order_by("order").first()
        )
        return band.color if band else "#9CA3AF"


class RatingColorBand(models.Model):
    """Un tramo de nota con su propio color (p. ej. "de 1 a 4: rojo") — se
    pueden definir tantos como se quiera, no solo un "bueno/medio/malo"
    fijo. El primer tramo cuyo rango incluya la nota es el que manda; si
    dos se solapan, gana el de menor `order`."""

    config = models.ForeignKey(TopSecretConfig, on_delete=models.CASCADE, related_name="rating_bands")
    min_rating = models.DecimalField("nota mínima", max_digits=3, decimal_places=1)
    max_rating = models.DecimalField("nota máxima", max_digits=3, decimal_places=1)
    color = hex_field("#9CA3AF", "color")
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        verbose_name = "tramo de color"
        verbose_name_plural = "tramos de color"
        ordering = ["order", "min_rating"]

    def __str__(self):
        return f"{self.min_rating}–{self.max_rating}: {self.color}"


class Genre(models.Model):
    """Lista temática de una película secreta (terror, slasher, años 80...),
    lo que antes se llamaba género/subgénero. Igual que las listas de
    Artículos o de Guardadas: texto libre, se crea sobre la marcha al
    escribirla en el admin — no es una lista cerrada."""

    name = models.CharField("nombre", max_length=50, unique=True)
    slug = models.SlugField("slug", max_length=60, unique=True, blank=True)
    admin_only = models.BooleanField(
        "solo para admins", default=False,
        help_text="Ni esta lista ni ninguna película marcada con ella las ve nadie más, aunque tenga el código.",
    )
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        verbose_name = "lista"
        verbose_name_plural = "listas"
        ordering = ["order", "name"]

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
    genres = models.ManyToManyField(Genre, verbose_name="listas", blank=True, related_name="secret_movies")
    movie = models.ForeignKey(
        Movie, verbose_name="película del catálogo (opcional, para la portada)",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        # Solo el singular cambia (Django arma "Añadir {verbose_name}",
        # "¿Eliminar la {verbose_name} X?", etc. con esto) — el plural se
        # deja igual a propósito, así el menú lateral sigue diciendo
        # "Películas secretas", que es donde sí tiene sentido ese nombre.
        verbose_name = "entrada a la lista completa"
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
    """Un nivel/columna del tier list (S, A, B... o el nombre que se quiera)
    — personal de cada usuario, igual que el calendario: nadie más ve tus
    niveles ni tus entradas, ni siquiera otro con el mismo código de acceso
    al maletín. Nombre, color y orden se gestionan enteros desde la propia
    página del Tier List — no hace falta pasar por el admin para nada de
    esto."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.CASCADE, related_name="tier_levels",
    )
    name = models.CharField("nombre", max_length=30)
    color = models.CharField("color", max_length=7, default="#2DD4BF")
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        verbose_name = "tier list: nivel"
        verbose_name_plural = "tier list: niveles"
        ordering = ["user_id", "order", "pk"]

    def __str__(self):
        return f"{self.name} ({self.user})"


class TierListEntry(models.Model):
    """Tier list personal: películas agrupadas en niveles (ver `TierLevel`),
    ordenables dentro de cada nivel, editable tanto desde la propia web
    (buscar y añadir, arrastrar entre niveles) como desde el admin.
    `tier=None` es "Sin clasificar": donde caen las que se acaban de añadir
    hasta que se arrastran a un nivel real — así nunca se cuela una entrada
    nueva directamente en un nivel sin que nadie la haya puesto ahí. Al
    borrar un `TierLevel` (on_delete=SET_NULL), sus entradas vuelven aquí
    en vez de perderse."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.CASCADE, related_name="tier_entries",
    )
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
        verbose_name = "tier list: entrada"
        verbose_name_plural = "tier list: entradas"
        ordering = ["user_id", "tier__order", "order", "title"]

    def __str__(self):
        return f"[{self.tier}] {self.title} ({self.user})"

    @property
    def poster_url(self):
        return self.movie.poster_url if self.movie else ""


class PhotoBoardMember(models.Model):
    """Acceso compartido al tablón de fotos de otro usuario: el dueño del
    tablón invita a amigos concretos (no hace falta pasar por el admin, se
    hace desde la propia página) para que puedan ver y subir fotos a SU
    tablón — antes era un único tablón compartido por cualquiera con el
    código; ahora cada uno tiene el suyo, privado por defecto, y decide con
    quién compartirlo. El dueño puede expulsar a cualquier invitado cuando
    quiera (borrar esta fila) sin que eso afecte a las fotos ya subidas."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="dueño del tablón",
        on_delete=models.CASCADE, related_name="photo_board_members",
    )
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="invitado",
        on_delete=models.CASCADE, related_name="shared_photo_boards",
    )
    invited_at = models.DateTimeField("invitado", auto_now_add=True)

    class Meta:
        verbose_name = "permiso al tablón de fotos"
        verbose_name_plural = "permisos al tablón de fotos"
        constraints = [
            models.UniqueConstraint(fields=["owner", "member"], name="un_acceso_por_dueno_y_miembro"),
        ]

    def __str__(self):
        return f"{self.member} en el tablón de {self.owner}"


class SecretPhoto(models.Model):
    """Foto de un tablón personal de Top Secret: cada usuario tiene el
    suyo (`board_owner`) y decide con quién compartirlo (`PhotoBoardMember`)
    — el dueño y sus invitados pueden ver y subir fotos ahí, con una
    pequeña descripción. `uploaded_by` guarda quién subió cada foto en
    concreto (puede ser el propio dueño o alguien invitado)."""

    board_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="tablón de",
        on_delete=models.CASCADE, related_name="photo_board_photos",
    )
    # Storage aparte ("secret_photos" en STORAGES, config/settings.py): a
    # diferencia del resto de imágenes del sitio, estas no deben tener una
    # URL pública permanente — solo se sirven a través de la vista
    # `photo_serve` (protegida por el código y por _can_access_photo_board).
    image = models.ImageField("foto", upload_to="secret_photos/", storage=storages["secret_photos"])
    description = models.CharField("descripción", max_length=280, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="subida por",
        on_delete=models.CASCADE, related_name="+",
    )
    created_at = models.DateTimeField("subida", auto_now_add=True)

    class Meta:
        verbose_name = "foto del tablón"
        verbose_name_plural = "tablón de fotos"
        ordering = ["-created_at"]

    def __str__(self):
        return self.description or f"Foto #{self.pk}"


class ReleaseEvent(models.Model):
    """Fecha en la que una película o serie "toca" (estreno, capítulo
    nuevo...) — calendario personal de cada usuario dentro de Top Secret →
    Otros (nadie más lo ve, ni siquiera otro usuario con el mismo código de
    acceso al maletín). Se añade desde la propia web buscando el título; si
    el usuario tiene conectado de verdad su Google Calendar
    (`apps.accounts.models.GoogleCalendarConnection`), el evento se crea
    solo ahí también (`google_event_id` guarda el id que le asigna Google,
    para poder borrarlo o moverlo ahí también)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.CASCADE, related_name="release_events",
    )
    movie = models.ForeignKey(Movie, verbose_name="película/serie", on_delete=models.CASCADE, related_name="+")
    date = models.DateField("fecha")
    note = models.CharField("nota", max_length=200, blank=True, help_text="Ej: 'Estreno', 'Temporada 2', 'Capítulo final'...")
    google_event_id = models.CharField("id del evento en Google Calendar", max_length=255, blank=True)

    class Meta:
        verbose_name = "estreno en el calendario"
        verbose_name_plural = "estrenos en el calendario"
        ordering = ["date"]
        db_table = "movies_releaseevent"

    def __str__(self):
        return f"{self.movie} — {self.date:%d/%m/%Y} ({self.user})"


class CalendarDayNote(models.Model):
    """Comentario libre en un día del calendario personal de un usuario, sin
    ligarlo a ninguna película/serie concreta (para eso ya está
    `ReleaseEvent`) — por ejemplo, una nota tipo "vacaciones" o "maratón con
    amigos"."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.CASCADE, related_name="calendar_day_notes")
    date = models.DateField("fecha")
    note = models.TextField("comentario")

    class Meta:
        verbose_name = "comentario del calendario"
        verbose_name_plural = "comentarios del calendario"
        ordering = ["date"]
        db_table = "movies_calendardaynote"
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="un_comentario_por_usuario_y_fecha"),
        ]

    def __str__(self):
        return f"{self.date:%d/%m/%Y} — {self.note} ({self.user})"
