from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from . import services


class Movie(models.Model):
    """Ficha de película cacheada localmente a partir de TMDb (título,
    portada, sinopsis) y OMDb (nota IMDb). Se resuelve una sola vez por
    tmdb_id y se reutiliza después: ni la ruleta ni las votaciones necesitan
    volver a golpear las APIs externas para una misma película."""

    tmdb_id = models.PositiveIntegerField("id de TMDb", unique=True)
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

    def __str__(self):
        return f"{self.title} ({self.year})" if self.year else self.title

    @property
    def poster_url(self):
        return services.poster_url(self.poster_path)

    @classmethod
    def get_or_create_from_tmdb(cls, tmdb_id):
        existing = cls.objects.filter(tmdb_id=tmdb_id).first()
        if existing:
            return existing

        details = services.tmdb_get_details(tmdb_id)
        imdb_id = (details.get("external_ids") or {}).get("imdb_id") or ""
        imdb_rating = services.omdb_get_imdb_rating(imdb_id) if imdb_id else None

        return cls.objects.create(
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            title=details.get("title") or details.get("original_title") or "(sin título)",
            year=(details.get("release_date") or "")[:4],
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


class RouletteCandidate(models.Model):
    """Modo 2 de la ruleta: lista personalizada de candidatas de un usuario."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="roulette_candidates")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="+")
    is_seen = models.BooleanField("ya salió en la ruleta", default=False)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "candidata de ruleta (lista personal)"
        verbose_name_plural = "candidatas de ruleta (lista personal)"
        constraints = [models.UniqueConstraint(fields=["user", "movie"], name="una_candidata_por_usuario")]
        ordering = ["-added_at"]

    def __str__(self):
        return f"{self.movie} en la lista de {self.user}"


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
