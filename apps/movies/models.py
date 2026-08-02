from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from . import services


class Movie(models.Model):
    """Ficha de película o serie cacheada localmente a partir de TMDb
    (título, portada, sinopsis) y OMDb (nota IMDb). Se resuelve una sola vez
    por (tmdb_id, media_type) y se reutiliza después — ni la ruleta ni las
    votaciones necesitan volver a golpear las APIs externas para la misma
    ficha. Películas y series comparten el mismo modelo porque TMDb/OMDb
    devuelven prácticamente la misma forma de datos para ambas; lo único que
    cambia es qué endpoint de TMDb se consulta (`/movie/...` o `/tv/...`)."""

    class MediaType(models.TextChoices):
        MOVIE = "movie", "Película"
        TV = "tv", "Serie"

    media_type = models.CharField("tipo", max_length=5, choices=MediaType.choices, default=MediaType.MOVIE)
    tmdb_id = models.PositiveIntegerField("id de TMDb")
    imdb_id = models.CharField("id de IMDb", max_length=20, blank=True)
    title = models.CharField("título", max_length=255)
    year = models.CharField("año", max_length=4, blank=True)
    poster_path = models.CharField("ruta de portada (TMDb)", max_length=300, blank=True)
    overview = models.TextField("sinopsis", blank=True)
    imdb_rating = models.DecimalField(
        "nota IMDb", max_digits=3, decimal_places=1, null=True, blank=True,
        help_text="Obtenida de OMDb (omdbapi.com). Vacía si OMDb no tiene nota para este título.",
    )
    created_at = models.DateTimeField("añadida", auto_now_add=True)

    class Meta:
        verbose_name = "película"
        verbose_name_plural = "películas"
        ordering = ["title"]
        constraints = [
            # Los ids de TMDb son independientes entre películas y series:
            # una película y una serie pueden compartir el mismo tmdb_id
            # sin ser la misma ficha, así que la unicidad va por la pareja.
            models.UniqueConstraint(fields=["tmdb_id", "media_type"], name="unico_tmdb_id_por_tipo"),
        ]

    def __str__(self):
        return f"{self.title} ({self.year})" if self.year else self.title

    @property
    def poster_url(self):
        return services.poster_url(self.poster_path)

    @property
    def is_tv(self):
        return self.media_type == self.MediaType.TV

    @classmethod
    def get_or_create_from_tmdb(cls, tmdb_id, media_type=MediaType.MOVIE):
        existing = cls.objects.filter(tmdb_id=tmdb_id, media_type=media_type).first()
        if existing:
            return existing

        details = services.tmdb_get_details(tmdb_id, media_type=media_type)
        imdb_id = (details.get("external_ids") or {}).get("imdb_id") or ""
        imdb_rating = services.omdb_get_imdb_rating(imdb_id) if imdb_id else None

        if media_type == cls.MediaType.TV:
            title = details.get("name") or details.get("original_name") or "(sin título)"
            date = details.get("first_air_date") or ""
        else:
            title = details.get("title") or details.get("original_title") or "(sin título)"
            date = details.get("release_date") or ""

        return cls.objects.create(
            tmdb_id=tmdb_id,
            media_type=media_type,
            imdb_id=imdb_id,
            title=title,
            year=date[:4],
            poster_path=details.get("poster_path") or "",
            overview=details.get("overview") or "",
            imdb_rating=imdb_rating,
        )

    @property
    def average_score(self):
        return self.votes.aggregate(models.Avg("score"))["score__avg"]

    @property
    def votes_count(self):
        return self.votes.count()


class Vote(models.Model):
    """Voto de un usuario a una película (1-10). Un voto por usuario y
    película: repetir la votación sobreescribe la anterior."""

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="movie_votes")
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "voto"
        verbose_name_plural = "votos"
        constraints = [models.UniqueConstraint(fields=["movie", "user"], name="un_voto_por_usuario_y_pelicula")]

    def __str__(self):
        return f"{self.user} vota {self.score} a {self.movie}"


class SavedMovie(models.Model):
    """Película guardada por un usuario en 'Mis películas' (independiente de
    si la ha votado o de si es candidata en la ruleta Modo 2). `order` es el
    orden de importancia que el propio usuario le da (0 = más importante),
    editable con los botones ▲▼ en la página de Guardadas."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_movies")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="+")
    order = models.PositiveIntegerField("orden de importancia", default=0)
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "película guardada"
        verbose_name_plural = "películas guardadas"
        constraints = [models.UniqueConstraint(fields=["user", "movie"], name="una_guardada_por_usuario")]
        ordering = ["order", "-saved_at"]

    def __str__(self):
        return f"{self.movie} guardada por {self.user}"


class RouletteRatingSeen(models.Model):
    """Modo 1 de la ruleta: qué películas del catálogo ya se le han mostrado
    a este usuario, para no repetir hasta agotar el rango de nota elegido."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="+")
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "película vista en ruleta (modo nota)"
        verbose_name_plural = "películas vistas en ruleta (modo nota)"
        constraints = [models.UniqueConstraint(fields=["user", "movie"], name="una_vista_por_usuario_modo_nota")]


class RouletteSavedSeen(models.Model):
    """Modo 2 de la ruleta: qué películas guardadas ya se le han mostrado a
    este usuario. La ruleta gira directamente sobre `SavedMovie` (no hay una
    lista de candidatas aparte); esto solo evita repetir hasta reiniciar."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="+")
    seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "película vista en ruleta (modo lista)"
        verbose_name_plural = "películas vistas en ruleta (modo lista)"
        constraints = [models.UniqueConstraint(fields=["user", "movie"], name="una_vista_por_usuario_modo_lista")]


class ReleaseEvent(models.Model):
    """Fecha en la que una película o serie "toca" (estreno, capítulo
    nuevo...) — el calendario de Top Secret → Otros (privado, no en el
    catálogo público). Se añade desde la propia web buscando el título; cada
    evento se puede descargar como .ics (funciona con Google Calendar, Apple
    Calendar, Outlook...) y, para quien tenga conectado de verdad su Google
    Calendar (`apps.accounts.models.GoogleCalendarConnection`), se crea solo
    ahí también — ver `ReleaseEventGoogleLink`."""

    movie = models.ForeignKey(Movie, verbose_name="película/serie", on_delete=models.CASCADE, related_name="release_events")
    date = models.DateField("fecha")
    note = models.CharField("nota", max_length=200, blank=True, help_text="Ej: 'Estreno', 'Temporada 2', 'Capítulo final'...")

    class Meta:
        verbose_name = "estreno en el calendario"
        verbose_name_plural = "calendario: estrenos"
        ordering = ["date"]

    def __str__(self):
        return f"{self.movie} — {self.date:%d/%m/%Y}"


class ReleaseEventGoogleLink(models.Model):
    """Un evento del calendario, ya creado en el Google Calendar real de un
    usuario conectado — un enlace por (evento, usuario), porque cada uno
    tiene su propia copia en su propio calendario. Guarda el id que Google
    le asigna para poder borrarlo ahí también si el evento se quita del
    sitio o si el usuario desconecta su cuenta."""

    release_event = models.ForeignKey(ReleaseEvent, on_delete=models.CASCADE, related_name="google_links")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    google_event_id = models.CharField("id del evento en Google", max_length=255)

    class Meta:
        verbose_name = "estreno enlazado a Google Calendar"
        verbose_name_plural = "calendario: enlaces a Google Calendar"
        constraints = [
            models.UniqueConstraint(fields=["release_event", "user"], name="un_evento_de_google_por_usuario"),
        ]

    def __str__(self):
        return f"{self.release_event} → Google Calendar de {self.user}"
