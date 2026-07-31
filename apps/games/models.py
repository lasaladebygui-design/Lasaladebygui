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
    """Duelo de Frases célebres entre dos amigos: los dos ven la MISMA
    pregunta a la vez (`current_index`, compartido) y avanzan juntos ronda
    a ronda — en cuanto uno responde mal, el duelo termina ahí mismo para
    los dos. Empieza como invitación (`PENDING`): el retado tiene que
    aceptarla antes de que arranque la partida."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        ACTIVE = "active", "En curso"
        FINISHED = "finished", "Terminado"

    QUOTE_COUNT = 10

    challenger = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="retador", on_delete=models.CASCADE, related_name="duels_started",
    )
    opponent = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="rival", on_delete=models.CASCADE, related_name="duels_received",
    )
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.PENDING)
    quote_ids = models.JSONField("frases del duelo (orden fijo, compartido)", default=list)
    current_index = models.PositiveIntegerField("ronda actual (compartida)", default=0)
    challenger_streak = models.PositiveIntegerField("racha del retador", default=0)
    opponent_streak = models.PositiveIntegerField("racha del rival", default=0)
    challenger_answered = models.BooleanField("el retador ya respondió esta ronda", default=False)
    opponent_answered = models.BooleanField("el rival ya respondió esta ronda", default=False)
    challenger_lost = models.BooleanField("el retador falló", default=False)
    opponent_lost = models.BooleanField("el rival falló", default=False)
    challenger_wants_rematch = models.BooleanField("el retador quiere revancha", default=False)
    opponent_wants_rematch = models.BooleanField("el rival quiere revancha", default=False)
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

    def answered_for(self, user):
        return self.challenger_answered if self.role_for(user) == "challenger" else self.opponent_answered

    def lost_for(self, user):
        return self.challenger_lost if self.role_for(user) == "challenger" else self.opponent_lost

    def wants_rematch_for(self, user):
        return self.challenger_wants_rematch if self.role_for(user) == "challenger" else self.opponent_wants_rematch

    def opponent_of(self, user):
        return self.opponent if self.role_for(user) == "challenger" else self.challenger

    def reset_for_rematch(self):
        self.quote_ids = list(
            MovieQuote.objects.order_by("?").values_list("pk", flat=True)[: self.QUOTE_COUNT]
        )
        self.current_index = 0
        self.challenger_streak = 0
        self.opponent_streak = 0
        self.challenger_answered = False
        self.opponent_answered = False
        self.challenger_lost = False
        self.opponent_lost = False
        self.challenger_wants_rematch = False
        self.opponent_wants_rematch = False
        self.status = self.Status.ACTIVE
        self.save()

    @property
    def winner(self):
        if self.status != self.Status.FINISHED:
            return None
        if self.challenger_lost and not self.opponent_lost:
            return self.opponent
        if self.opponent_lost and not self.challenger_lost:
            return self.challenger
        return None  # empate: ninguno falló (completaron la tanda juntos) o fallaron los dos a la vez
