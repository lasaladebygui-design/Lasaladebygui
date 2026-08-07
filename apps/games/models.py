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

    class MediaType(models.TextChoices):
        MOVIE = "movie", "Película"
        TV = "tv", "Serie"

    quote = models.TextField("frase")
    media_type = models.CharField(
        "tipo", max_length=5, choices=MediaType.choices, default=MediaType.MOVIE,
        help_text="Las tres opciones (correcta + 2 incorrectas) deben ser del mismo tipo, para no tener que elegir entre una peli y una serie.",
    )
    correct_title = models.CharField("título correcto", max_length=255)
    wrong_title_1 = models.CharField("opción incorrecta 1", max_length=255)
    wrong_title_2 = models.CharField("opción incorrecta 2", max_length=255)

    class Meta:
        verbose_name = "frase célebre"
        verbose_name_plural = "frases célebres"
        db_table = "secret_moviequote"

    def __str__(self):
        return f"«{self.quote[:40]}…» — {self.correct_title}"


class TriviaQuestion(models.Model):
    """Pregunta de una sola tanda de juegos que comparten el mismo
    mecanismo (enunciado + 3 opciones, una correcta): Trivial (preguntas de
    cine/series clásicas), Emoji (adivina el título a partir de una
    secuencia de emojis), Malas descripciones (adivina el título a partir
    de una sinopsis deliberadamente mala) y Cuál tiene al actor/actriz
    (adivina en cuál de las opciones sale la persona de `image_url`). Están
    en un único modelo, distinguido por `category`, porque las cuatro
    comparten exactamente la misma forma — solo cambia qué se muestra como
    enunciado y si hay imagen."""

    class Category(models.TextChoices):
        TRIVIA = "trivia", "Trivial"
        EMOJI = "emoji", "Emoji"
        BAD_DESCRIPTION = "bad_description", "Malas descripciones"
        ACTOR = "actor", "Cuál tiene al actor/actriz"

    category = models.CharField("categoría", max_length=20, choices=Category.choices)
    media_type = models.CharField(
        "tipo", max_length=5, choices=MovieQuote.MediaType.choices, default=MovieQuote.MediaType.MOVIE,
        help_text="Las tres opciones (correcta + 2 incorrectas) deben ser del mismo tipo, para no tener que elegir entre una peli y una serie.",
    )
    prompt = models.TextField(
        "enunciado",
        help_text=(
            "Según la categoría: la pregunta de trivia, la mala descripción, o el nombre del actor/actriz. "
            "En Emoji, cada emoji separado por un espacio (se revelan de uno en uno, no todos a la vez): «🦁 👑»."
        ),
    )
    image_url = models.URLField(
        "imagen", blank=True,
        help_text="Opcional — se usa sobre todo en 'Cuál tiene al actor/actriz' (foto de la persona).",
    )
    correct_answer = models.CharField("respuesta correcta", max_length=255)
    wrong_answer_1 = models.CharField("respuesta incorrecta 1", max_length=255)
    wrong_answer_2 = models.CharField("respuesta incorrecta 2", max_length=255)

    class Meta:
        verbose_name = "pregunta de trivia"
        verbose_name_plural = "Juegos: preguntas de trivia"

    def __str__(self):
        return f"[{self.get_category_display()}] {self.prompt[:40]}"


class TrueFalseStatement(models.Model):
    """Afirmación del juego 'Verdadero o falso': se muestra el texto y hay
    que decir si es cierto o no."""

    statement = models.TextField("afirmación")
    is_true = models.BooleanField("¿es verdadera?")

    class Meta:
        verbose_name = "afirmación de verdadero o falso"
        verbose_name_plural = "Juegos: verdadero o falso"

    def __str__(self):
        return f"[{'V' if self.is_true else 'F'}] {self.statement[:50]}"


class PersonalityCharacter(models.Model):
    """Uno de los posibles resultados del test 'Qué personaje eres'. No
    tiene por qué ser de cine — Jinx (Arcane) es un resultado a propósito—,
    pero la mayoría son de películas de géneros variados (acción, romance,
    comedia), no solo villanos de acción."""

    name = models.CharField("nombre", max_length=100)
    source = models.CharField("película/serie", max_length=100, blank=True)
    description = models.TextField("descripción del resultado")
    image_url = models.URLField("imagen", blank=True)
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "Qué personaje eres: personaje"
        verbose_name_plural = "Juegos: Qué personaje eres — personajes"

    def __str__(self):
        return self.name


class PersonalityQuestion(models.Model):
    """Pregunta del test — se responde una detrás de otra, en orden fijo,
    sin racha ni fallo: es un test de personalidad, no un juego de acertar."""

    text = models.TextField("pregunta")
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "Qué personaje eres: pregunta"
        verbose_name_plural = "Juegos: Qué personaje eres — preguntas"

    def __str__(self):
        return self.text[:60]


class PersonalityAnswer(models.Model):
    """Una opción de respuesta, que suma un punto para `character` si se
    elige. Al final del test gana el personaje con más puntos acumulados."""

    question = models.ForeignKey(PersonalityQuestion, verbose_name="pregunta", on_delete=models.CASCADE, related_name="answers")
    text = models.CharField("texto", max_length=255)
    character = models.ForeignKey(PersonalityCharacter, verbose_name="personaje", on_delete=models.CASCADE, related_name="+")
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "Qué personaje eres: respuesta"
        verbose_name_plural = "Juegos: Qué personaje eres — respuestas"

    def __str__(self):
        return f"{self.text} → {self.character}"


class Duel(models.Model):
    """Duelo entre dos amigos, a elegir de entre varios juegos de trivia
    (`game`): los dos ven la MISMA pregunta a la vez (`current_index`,
    compartido) y avanzan juntos ronda a ronda — en cuanto uno responde mal,
    el duelo termina ahí mismo para los dos. No hay una tanda de tamaño
    fijo: se juega hasta fallar, igual que el modo en solitario, así que
    `round_ids` crece sobre la marcha en vez de generarse entero de golpe al
    crear el duelo. Empieza como invitación (`PENDING`): el retado tiene que
    aceptarla antes de que arranque la partida."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        ACTIVE = "active", "En curso"
        FINISHED = "finished", "Terminado"

    class Game(models.TextChoices):
        QUOTES = "quotes", "Frases célebres"
        TRIVIA = "trivia", "Trivial"
        BAD_DESCRIPTION = "bad_description", "Malas descripciones"
        ACTOR = "actor", "Cuál tiene al actor/actriz"

    challenger = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="retador", on_delete=models.CASCADE, related_name="duels_started",
    )
    opponent = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="rival", on_delete=models.CASCADE, related_name="duels_received",
    )
    game = models.CharField("juego", max_length=20, choices=Game.choices, default=Game.QUOTES)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.PENDING)
    round_ids = models.JSONField("preguntas jugadas hasta ahora (compartidas)", default=list)
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

    def reset_for_rematch(self, first_round_id):
        self.round_ids = [first_round_id]
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


class DuelRecord(models.Model):
    """Marcador histórico de duelos entre dos usuarios: cuántas veces ha
    ganado cada uno contra el otro. El `Duel` en sí se borra al terminar
    (para no acumular partidas viejas en "Tus duelos"), pero este marcador
    se queda — se actualiza en el momento exacto en que un duelo termina,
    no cuando se borra la fila. `player_low`/`player_high` son solo un
    orden interno (por pk) para que cada pareja de usuarios tenga una
    única fila, sin que importe quién retó a quién esta vez."""

    player_low = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    player_high = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    player_low_wins = models.PositiveIntegerField("victorias de player_low", default=0)
    player_high_wins = models.PositiveIntegerField("victorias de player_high", default=0)
    draws = models.PositiveIntegerField("empates", default=0)

    class Meta:
        verbose_name = "marcador de duelos"
        verbose_name_plural = "Juegos: marcadores de duelos"
        constraints = [
            models.UniqueConstraint(fields=["player_low", "player_high"], name="un_marcador_por_pareja"),
        ]

    def __str__(self):
        return f"{self.player_low} {self.player_low_wins}-{self.player_high_wins} {self.player_high}"

    @staticmethod
    def _ordered_pair(user_a, user_b):
        return (user_a, user_b) if user_a.pk < user_b.pk else (user_b, user_a)

    @classmethod
    def record_result(cls, user_a, user_b, winner):
        low, high = cls._ordered_pair(user_a, user_b)
        record, _ = cls.objects.get_or_create(player_low=low, player_high=high)
        if winner is None:
            record.draws += 1
        elif winner.pk == low.pk:
            record.player_low_wins += 1
        else:
            record.player_high_wins += 1
        record.save()
        return record

    @classmethod
    def get_for(cls, user_a, user_b):
        low, high = cls._ordered_pair(user_a, user_b)
        return cls.objects.filter(player_low=low, player_high=high).first()

    def wins_for(self, user):
        return self.player_low_wins if user.pk == self.player_low_id else self.player_high_wins

    def losses_for(self, user):
        return self.player_high_wins if user.pk == self.player_low_id else self.player_low_wins


class OscarCategory(models.Model):
    """Categoría de 'Candidatos al Oscar' (p. ej. 'Mejor película', 'Mejor
    actor'): los usuarios proponen candidatas y votan por su favorita, una
    vez por categoría. A diferencia de los juegos de racha, esto es una
    herramienta permanente/compartida, no algo personal.

    `candidate_type` decide qué se propone: una película del catálogo
    (categorías como Mejor película o Mejor banda sonora) o una persona
    (Mejor actor, Mejor actriz, Mejor director...) — buscada por nombre vía
    TMDb, con su foto, sin que haga falta un modelo de "Persona" aparte."""

    class CandidateType(models.TextChoices):
        MOVIE = "movie", "Película"
        PERSON = "person", "Persona (actor/actriz, director/a...)"

    name = models.CharField("categoría", max_length=100)
    candidate_type = models.CharField(
        "tipo de candidata", max_length=10, choices=CandidateType.choices, default=CandidateType.MOVIE,
    )
    is_open = models.BooleanField("abierta a candidaturas y votos", default=True)
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "Candidatos al Oscar: categoría"
        verbose_name_plural = "Juegos: Candidatos al Oscar — categorías"

    def __str__(self):
        return self.name


class OscarCandidate(models.Model):
    """Una candidata dentro de una categoría — o una película (`movie`) o
    una persona (`person_name`/`person_photo_url`/`person_tmdb_id`), según
    `category.candidate_type`. Nunca se rellenan los dos a la vez."""

    category = models.ForeignKey(OscarCategory, verbose_name="categoría", on_delete=models.CASCADE, related_name="candidates")
    movie = models.ForeignKey(
        "movies.Movie", verbose_name="película", on_delete=models.CASCADE, related_name="+", null=True, blank=True,
    )
    person_name = models.CharField("nombre", max_length=150, blank=True)
    person_photo_url = models.URLField("foto", blank=True)
    person_tmdb_id = models.PositiveIntegerField("id de TMDb", null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="propuesta por", on_delete=models.CASCADE, related_name="+",
    )
    created_at = models.DateTimeField("propuesta", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Candidatos al Oscar: candidata"
        verbose_name_plural = "Juegos: Candidatos al Oscar — candidatas"
        constraints = [
            models.UniqueConstraint(fields=["category", "movie"], name="una_pelicula_candidata_por_categoria"),
            models.UniqueConstraint(fields=["category", "person_tmdb_id"], name="una_persona_candidata_por_categoria"),
        ]

    def __str__(self):
        return f"{self.display_title} — {self.category}"

    @property
    def display_title(self):
        return self.movie.title if self.movie else self.person_name

    @property
    def display_photo(self):
        return self.movie.poster_url if self.movie else self.person_photo_url


class OscarVote(models.Model):
    """Un voto por usuario y categoría — votar por una candidata distinta
    en la misma categoría reemplaza el voto anterior, no lo suma."""

    category = models.ForeignKey(OscarCategory, verbose_name="categoría", on_delete=models.CASCADE, related_name="votes")
    candidate = models.ForeignKey(OscarCandidate, verbose_name="candidata", on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.CASCADE, related_name="+")

    class Meta:
        verbose_name = "Candidatos al Oscar: voto"
        verbose_name_plural = "Juegos: Candidatos al Oscar — votos"
        constraints = [
            models.UniqueConstraint(fields=["category", "user"], name="un_voto_por_categoria_y_usuario"),
        ]

    def __str__(self):
        return f"{self.user} → {self.candidate} ({self.category})"


class GameTierLevel(models.Model):
    """Nivel/columna del tier list personal de un usuario en Juegos. Igual
    de editable (nombre, color, orden, todo desde la propia página) que los
    niveles del tier list de Top Secret — la diferencia es que aquí cada
    usuario tiene los suyos propios, sin compartir ni mostrar nada a nadie
    más."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.CASCADE, related_name="game_tier_levels",
    )
    name = models.CharField("nombre", max_length=30)
    color = models.CharField("color", max_length=7, default="#2DD4BF")
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        verbose_name = "tier list de Juegos: nivel"
        verbose_name_plural = "tier list de Juegos: niveles"
        ordering = ["user_id", "order", "pk"]

    def __str__(self):
        return f"{self.user} — {self.name}"


class GameTierEntry(models.Model):
    """Tier list personal de cada usuario, como juego en `/juegos/` — no
    tiene nada que ver con la de Top Secret (esa es la de Quentin/el dueño
    del sitio, una sola); esta es de cualquiera con cuenta, un juego más,
    con niveles (`GameTierLevel`) igual de editables que los de Top Secret
    pero sin compartir ninguno entre usuarios. `tier=None` es "Sin
    clasificar", igual que en la tier list de Top Secret."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.CASCADE, related_name="game_tier_entries",
    )
    movie = models.ForeignKey(
        "movies.Movie", verbose_name="película", on_delete=models.CASCADE, related_name="+",
    )
    tier = models.ForeignKey(
        GameTierLevel, verbose_name="nivel", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="entries",
    )
    order = models.PositiveIntegerField("orden dentro del nivel", default=0)

    class Meta:
        verbose_name = "tier list de Juegos: entrada"
        verbose_name_plural = "tier list de Juegos: entradas"
        ordering = ["tier__order", "order", "movie__title"]
        constraints = [
            models.UniqueConstraint(fields=["user", "movie"], name="una_vez_por_usuario_en_tier_de_juegos"),
        ]

    def __str__(self):
        return f"{self.user} — [{self.tier}] {self.movie}"
