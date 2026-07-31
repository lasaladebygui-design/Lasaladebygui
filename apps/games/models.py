from django.conf import settings
from django.db import models


class MovieQuote(models.Model):
    """Frase de una película para el juego 'Frases célebres': la web la
    muestra junto a tres opciones (la correcta + estas dos) y hay que
    acertar la película.

    Vivía antes en `apps.secret` (Top Secret); se movió aquí para que el
    panel de administración agrupe "Frases célebres" bajo Juegos en vez de
    bajo Top Secret, ya que en la propia web el juego es de acceso libre
    (`/juegos/frases/`) desde hace tiempo. `db_table` apunta a la tabla
    original para no mover datos."""

    quote = models.TextField("frase")
    correct_title = models.CharField("película correcta", max_length=255)
    wrong_title_1 = models.CharField("opción incorrecta 1", max_length=255)
    wrong_title_2 = models.CharField("opción incorrecta 2", max_length=255)

    class Meta:
        verbose_name = "frase célebre"
        verbose_name_plural = "frases célebres"
        db_table = "secret_moviequote"

    def __str__(self):
        return f"«{self.quote[:40]}…» — {self.correct_title}"


class Duel(models.Model):
    """Duelo de Frases célebres entre dos amigos: ambos juegan la misma
    tanda de frases (mismo orden) por separado, y al terminar los dos se
    compara quién llegó más lejos sin fallar."""

    class Status(models.TextChoices):
        ACTIVE = "active", "En curso"
        FINISHED = "finished", "Terminado"

    QUOTE_COUNT = 10

    challenger = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="retador", on_delete=models.CASCADE, related_name="duels_started",
    )
    opponent = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="rival", on_delete=models.CASCADE, related_name="duels_received",
    )
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    quote_ids = models.JSONField("frases del duelo (orden fijo)", default=list)
    challenger_streak = models.PositiveIntegerField("racha del retador", default=0)
    opponent_streak = models.PositiveIntegerField("racha del rival", default=0)
    challenger_finished = models.BooleanField("el retador ha terminado", default=False)
    opponent_finished = models.BooleanField("el rival ha terminado", default=False)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "duelo"
        verbose_name_plural = "duelos"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.challenger} vs {self.opponent} ({self.get_status_display()})"

    def role_for(self, user):
        if user.pk == self.challenger_id:
            return "challenger"
        if user.pk == self.opponent_id:
            return "opponent"
        return None

    def streak_for(self, user):
        return self.challenger_streak if self.role_for(user) == "challenger" else self.opponent_streak

    def has_finished(self, user):
        return self.challenger_finished if self.role_for(user) == "challenger" else self.opponent_finished

    def opponent_of(self, user):
        return self.opponent if self.role_for(user) == "challenger" else self.challenger

    @property
    def both_finished(self):
        return self.challenger_finished and self.opponent_finished

    @property
    def winner(self):
        if not self.both_finished:
            return None
        if self.challenger_streak > self.opponent_streak:
            return self.challenger
        if self.opponent_streak > self.challenger_streak:
            return self.opponent
        return None  # empate
