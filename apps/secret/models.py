from django.contrib.auth.hashers import check_password, make_password
from django.db import models

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


class SecretMovie(models.Model):
    """Entrada de la lista personal de Quentin: un número (para el selector),
    su propia nota (distinta de la media de votos o de IMDb) y un comentario.
    Puede enlazar opcionalmente a una película del catálogo (apps.movies)
    para reutilizar su portada."""

    number = models.PositiveIntegerField("número", unique=True)
    title = models.CharField("título", max_length=255)
    personal_rating = models.DecimalField("nota personal", max_digits=3, decimal_places=1)
    comment = models.TextField("comentario", blank=True)
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
