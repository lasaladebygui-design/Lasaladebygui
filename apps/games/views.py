import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.accounts.models import User
from apps.movies.models import Movie
from apps.movies.services import MovieAPIError, tmdb_search, tmdb_search_person
from apps.social.models import Message, are_friends, friends_of

from .forms import GameTierLevelForm
from .models import (
    Duel, DuelRecord, GameTierEntry, GameTierLevel, MovieQuote, OscarCandidate, OscarCategory, OscarVote,
    PersonalityAnswer, PersonalityCharacter, PersonalityQuestion, TriviaQuestion, TrueFalseStatement,
)

DEFAULT_TIER_LEVELS = [
    ("S", "#FFD700"),
    ("A", "#FFA94D"),
    ("B", "#A9E34B"),
    ("C", "#74C0FC"),
    ("D", "#D98C8C"),
]

QUOTE_STREAK_KEY = "quote_streak"
QUOTE_BEST_ANON_KEY = "quote_streak_best_anon"

RATING_DUEL_MEDIA_TYPES = ("movie", "tv")


def games_hub(request):
    duels = []
    friends = []
    if request.user.is_authenticated:
        duels = Duel.objects.filter(
            Q(challenger=request.user) | Q(opponent=request.user)
        ).select_related("challenger", "opponent")
        friends = friends_of(request.user)
    return render(request, "games/games.html", {
        "duels": duels, "friends": friends, "duel_games": Duel.Game.choices,
    })


def _register_best_streak(request, streak):
    if request.user.is_authenticated:
        if streak > request.user.quote_streak_best:
            request.user.quote_streak_best = streak
            request.user.save(update_fields=["quote_streak_best"])
    elif streak > request.session.get(QUOTE_BEST_ANON_KEY, 0):
        request.session[QUOTE_BEST_ANON_KEY] = streak


def quote_game(request):
    streak = request.session.get(QUOTE_STREAK_KEY, 0)
    game_over = False
    is_new_record = False
    final_streak = None
    wrong_answer_title = None

    if request.method == "POST":
        quote = get_object_or_404(MovieQuote, pk=request.POST.get("quote_id"))
        if request.POST.get("answer") == quote.correct_title:
            streak += 1
            request.session[QUOTE_STREAK_KEY] = streak
        else:
            previous_best = (
                request.user.quote_streak_best if request.user.is_authenticated
                else request.session.get(QUOTE_BEST_ANON_KEY, 0)
            )
            final_streak = streak
            is_new_record = streak > previous_best
            wrong_answer_title = quote.correct_title
            _register_best_streak(request, streak)
            request.session[QUOTE_STREAK_KEY] = 0
            streak = 0
            game_over = True

    next_quote = None
    options = []
    if not game_over:
        next_quote = MovieQuote.objects.order_by("?").first()
        if next_quote:
            options = [next_quote.correct_title, next_quote.wrong_title_1, next_quote.wrong_title_2]
            random.shuffle(options)

    best = (
        request.user.quote_streak_best if request.user.is_authenticated
        else request.session.get(QUOTE_BEST_ANON_KEY, 0)
    )

    return render(request, "games/quote_game.html", {
        "quote": next_quote, "options": options, "streak": streak, "best": best,
        "game_over": game_over, "is_new_record": is_new_record,
        "final_streak": final_streak, "wrong_answer_title": wrong_answer_title,
    })


# --- Cuál está mejor valorada ---------------------------------------------
# "Higher/lower" con las notas IMDb del catálogo: dos portadas, una con la
# nota ya revelada (la "campeona", ganadora de la ronda anterior) y otra
# nueva sin revelar; hay que adivinar si la nueva tiene más o menos nota que
# la campeona. Acertar la mantiene en pie (o la releva la nueva si ganaba
# ella) y sale otra retadora; fallar termina la racha, igual que Frases
# célebres. Películas y series van cada una por su lado (`media_type`): cada
# una con su propia racha, tanto en sesión como en el récord guardado.
#
# Cada ronda se juega en dos pasos (elegir -> ver el resultado en color ->
# "Siguiente") en vez de saltar directo a la ronda siguiente: sin ese
# segundo paso no hay manera de que el acierto se vea de verdad en verde.

RATING_DUEL_MAX_REPEATS_CHOICES = (1, 2, 3)


def _rating_duel_streak_key(media_type):
    return f"rating_duel_streak_{media_type}"


def _rating_duel_max_repeats_key(media_type):
    return f"rating_duel_max_repeats_{media_type}"


def _rating_duel_max_repeats(request, media_type):
    """El tope de repeticiones por partida se sortea (1, 2 o 3) en vez de
    ser siempre el mismo número — así, aunque sepas que una película tiene
    un 9, no puedes contar con poder abusar de ella un número fijo de veces:
    unas partidas te deja repetirla tres veces, otras solo una. Se sortea
    una vez por partida (hasta el siguiente fallo) y no en cada ronda."""
    key = _rating_duel_max_repeats_key(media_type)
    value = request.session.get(key)
    if value is None:
        value = random.choice(RATING_DUEL_MAX_REPEATS_CHOICES)
        request.session[key] = value
    return value


def _rating_duel_champion_key(media_type):
    return f"rating_duel_champion_id_{media_type}"


RATING_DUEL_MAX_CHAMPION_STREAK = 2


def _rating_duel_champion_streak_key(media_type):
    return f"rating_duel_champion_streak_{media_type}"


def _rating_duel_best_anon_key(media_type):
    return f"rating_duel_streak_best_anon_{media_type}"


def _rating_duel_best_field(media_type):
    return "rating_duel_streak_best_movie" if media_type == "movie" else "rating_duel_streak_best_tv"


def _rating_duel_anon_key(media_type):
    return f"rating_duel_anon_{media_type}"


def _rating_duel_seen_key(media_type):
    return f"rating_duel_seen_{media_type}"


def _rating_duel_round_key(media_type):
    return f"rating_duel_round_{media_type}"


def _register_rating_duel_best(request, media_type, streak):
    if request.user.is_authenticated:
        field = _rating_duel_best_field(media_type)
        if streak > getattr(request.user, field):
            setattr(request.user, field, streak)
            request.user.save(update_fields=[field])
    else:
        key = _rating_duel_best_anon_key(media_type)
        if streak > request.session.get(key, 0):
            request.session[key] = streak


def _rating_duel_register_seen(request, media_type, movie_id):
    key = _rating_duel_seen_key(media_type)
    counts = request.session.get(key, {})
    counts[str(movie_id)] = counts.get(str(movie_id), 0) + 1
    request.session[key] = counts


def _rating_duel_overused_ids(request, media_type):
    max_repeats = _rating_duel_max_repeats(request, media_type)
    counts = request.session.get(_rating_duel_seen_key(media_type), {})
    return [int(mid) for mid, n in counts.items() if n >= max_repeats]


def _pick_rated_movie(request, media_type, exclude_id=None):
    """Evita repetir la misma película más veces que el tope sorteado para
    esta partida (si no, en cuanto sabes que una tiene un 9, la fuerzas a
    salir una y otra vez). Si ya no queda ninguna sin topar (catálogo
    pequeño), se libera el tope para no bloquear la partida."""
    exclude_ids = set(_rating_duel_overused_ids(request, media_type))
    if exclude_id:
        exclude_ids.add(exclude_id)
    qs = Movie.objects.filter(imdb_rating__isnull=False, media_type=media_type).exclude(pk__in=exclude_ids)
    movie = qs.order_by("?").first()
    if movie is None:
        qs = Movie.objects.filter(imdb_rating__isnull=False, media_type=media_type)
        if exclude_id:
            qs = qs.exclude(pk=exclude_id)
        movie = qs.order_by("?").first()
    return movie


def rating_duel_game(request):
    media_type = request.GET.get("type") or request.POST.get("type")

    # Pantalla de inicio: hasta que no se elige tipo (y, de paso, si se
    # quiere ver la nota o jugar en modo anónimo) no arranca la partida.
    if media_type not in RATING_DUEL_MEDIA_TYPES:
        return render(request, "games/rating_duel_start.html")

    streak_key = _rating_duel_streak_key(media_type)
    champion_key = _rating_duel_champion_key(media_type)
    anon_key = _rating_duel_anon_key(media_type)
    round_key = _rating_duel_round_key(media_type)

    if request.method == "GET" and "anon" in request.GET:
        request.session[anon_key] = request.GET.get("anon") == "1"
    anon_mode = request.session.get(anon_key, False)

    streak = request.session.get(streak_key, 0)
    round_result = request.session.get(round_key)

    if request.method == "POST":
        if request.POST.get("advance"):
            request.session.pop(round_key, None)
            round_result = None
        else:
            anon_mode = request.POST.get("anon") == "1"
            request.session[anon_key] = anon_mode
            left = get_object_or_404(Movie, pk=request.POST.get("left_id"))
            right = get_object_or_404(Movie, pk=request.POST.get("right_id"))
            choice = request.POST.get("choice")
            left_wins = left.imdb_rating >= right.imdb_rating
            correct = (choice == "left") == left_wins

            _rating_duel_register_seen(request, media_type, left.pk)
            _rating_duel_register_seen(request, media_type, right.pk)

            game_over = False
            final_streak = None
            is_new_record = False
            if correct:
                streak += 1
                request.session[streak_key] = streak
                winner = left if left_wins else right
                champion_streak_key = _rating_duel_champion_streak_key(media_type)
                if left_wins:
                    # La campeona revalida el puesto: no se deja que se
                    # repita más de RATING_DUEL_MAX_CHAMPION_STREAK rondas
                    # seguidas — si no, en cuanto sabes que tiene la nota
                    # más alta, la votas hasta el infinito. Al tope, se
                    # jubila (campeona Y retadora nuevas), sin tocar la
                    # racha: el juego sigue igual.
                    champion_streak = request.session.get(champion_streak_key, 1)
                    if champion_streak >= RATING_DUEL_MAX_CHAMPION_STREAK:
                        request.session.pop(champion_key, None)
                        request.session.pop(champion_streak_key, None)
                    else:
                        request.session[champion_key] = winner.pk
                        request.session[champion_streak_key] = champion_streak + 1
                else:
                    request.session[champion_key] = winner.pk
                    request.session[champion_streak_key] = 1
            else:
                previous_best = (
                    getattr(request.user, _rating_duel_best_field(media_type)) if request.user.is_authenticated
                    else request.session.get(_rating_duel_best_anon_key(media_type), 0)
                )
                final_streak = streak
                is_new_record = streak > previous_best
                _register_rating_duel_best(request, media_type, streak)
                request.session[streak_key] = 0
                request.session.pop(champion_key, None)
                request.session.pop(_rating_duel_champion_streak_key(media_type), None)
                request.session.pop(_rating_duel_max_repeats_key(media_type), None)
                streak = 0
                game_over = True

            round_result = {
                "left_id": left.pk, "right_id": right.pk,
                "left_title": left.title, "right_title": right.title,
                "left_poster": left.poster_url, "right_poster": right.poster_url,
                "left_rating": str(left.imdb_rating), "right_rating": str(right.imdb_rating),
                "choice": choice, "winner_side": "left" if left_wins else "right", "correct": correct,
                "game_over": game_over, "final_streak": final_streak, "is_new_record": is_new_record,
            }
            request.session[round_key] = round_result

    champion = challenger = None
    if not round_result:
        champion_id = request.session.get(champion_key)
        champion = Movie.objects.filter(pk=champion_id, imdb_rating__isnull=False, media_type=media_type).first() if champion_id else None
        if champion is None:
            champion = _pick_rated_movie(request, media_type)
            if champion:
                request.session[champion_key] = champion.pk
                request.session[_rating_duel_champion_streak_key(media_type)] = 1
        challenger = _pick_rated_movie(request, media_type, exclude_id=champion.pk) if champion else None

    best = (
        getattr(request.user, _rating_duel_best_field(media_type)) if request.user.is_authenticated
        else request.session.get(_rating_duel_best_anon_key(media_type), 0)
    )

    return render(request, "games/rating_duel.html", {
        "left": champion, "right": challenger, "streak": streak, "best": best,
        "media_type": media_type, "anon_mode": anon_mode, "round_result": round_result,
    })


# --- Cuál recaudó más -----------------------------------------------------
# Mismo "higher/lower" que Cuál está mejor valorada, pero con la
# recaudación de taquilla (TMDb) en vez de la nota IMDb — y solo películas,
# porque TMDb no tiene ese dato para series. Reutiliza el mismo patrón de
# sesión (campeona con tope de rondas seguidas, tope de repeticiones
# sorteado, ronda en dos pasos) que ya usa Cuál está mejor valorada.

REVENUE_DUEL_MAX_REPEATS_CHOICES = (1, 2, 3)
REVENUE_DUEL_MAX_CHAMPION_STREAK = 2

REVENUE_DUEL_STREAK_KEY = "revenue_duel_streak"
REVENUE_DUEL_CHAMPION_KEY = "revenue_duel_champion_id"
REVENUE_DUEL_CHAMPION_STREAK_KEY = "revenue_duel_champion_streak"
REVENUE_DUEL_MAX_REPEATS_KEY = "revenue_duel_max_repeats"
REVENUE_DUEL_SEEN_KEY = "revenue_duel_seen"
REVENUE_DUEL_ROUND_KEY = "revenue_duel_round"
REVENUE_DUEL_BEST_ANON_KEY = "revenue_duel_streak_best_anon"


def _revenue_duel_max_repeats(request):
    value = request.session.get(REVENUE_DUEL_MAX_REPEATS_KEY)
    if value is None:
        value = random.choice(REVENUE_DUEL_MAX_REPEATS_CHOICES)
        request.session[REVENUE_DUEL_MAX_REPEATS_KEY] = value
    return value


def _register_revenue_duel_best(request, streak):
    if request.user.is_authenticated:
        if streak > request.user.revenue_duel_streak_best:
            request.user.revenue_duel_streak_best = streak
            request.user.save(update_fields=["revenue_duel_streak_best"])
    elif streak > request.session.get(REVENUE_DUEL_BEST_ANON_KEY, 0):
        request.session[REVENUE_DUEL_BEST_ANON_KEY] = streak


def _revenue_duel_register_seen(request, movie_id):
    counts = request.session.get(REVENUE_DUEL_SEEN_KEY, {})
    counts[str(movie_id)] = counts.get(str(movie_id), 0) + 1
    request.session[REVENUE_DUEL_SEEN_KEY] = counts


def _revenue_duel_overused_ids(request):
    max_repeats = _revenue_duel_max_repeats(request)
    counts = request.session.get(REVENUE_DUEL_SEEN_KEY, {})
    return [int(mid) for mid, n in counts.items() if n >= max_repeats]


def _pick_grossing_movie(request, exclude_id=None):
    exclude_ids = set(_revenue_duel_overused_ids(request))
    if exclude_id:
        exclude_ids.add(exclude_id)
    qs = Movie.objects.filter(revenue__isnull=False, media_type="movie").exclude(pk__in=exclude_ids)
    movie = qs.order_by("?").first()
    if movie is None:
        qs = Movie.objects.filter(revenue__isnull=False, media_type="movie")
        if exclude_id:
            qs = qs.exclude(pk=exclude_id)
        movie = qs.order_by("?").first()
    return movie


def revenue_duel_game(request):
    streak = request.session.get(REVENUE_DUEL_STREAK_KEY, 0)
    round_result = request.session.get(REVENUE_DUEL_ROUND_KEY)

    if request.method == "POST":
        if request.POST.get("advance"):
            request.session.pop(REVENUE_DUEL_ROUND_KEY, None)
            round_result = None
        else:
            left = get_object_or_404(Movie, pk=request.POST.get("left_id"))
            right = get_object_or_404(Movie, pk=request.POST.get("right_id"))
            choice = request.POST.get("choice")
            left_wins = left.revenue >= right.revenue
            correct = (choice == "left") == left_wins

            _revenue_duel_register_seen(request, left.pk)
            _revenue_duel_register_seen(request, right.pk)

            game_over = False
            final_streak = None
            is_new_record = False
            if correct:
                streak += 1
                request.session[REVENUE_DUEL_STREAK_KEY] = streak
                winner = left if left_wins else right
                if left_wins:
                    champion_streak = request.session.get(REVENUE_DUEL_CHAMPION_STREAK_KEY, 1)
                    if champion_streak >= REVENUE_DUEL_MAX_CHAMPION_STREAK:
                        request.session.pop(REVENUE_DUEL_CHAMPION_KEY, None)
                        request.session.pop(REVENUE_DUEL_CHAMPION_STREAK_KEY, None)
                    else:
                        request.session[REVENUE_DUEL_CHAMPION_KEY] = winner.pk
                        request.session[REVENUE_DUEL_CHAMPION_STREAK_KEY] = champion_streak + 1
                else:
                    request.session[REVENUE_DUEL_CHAMPION_KEY] = winner.pk
                    request.session[REVENUE_DUEL_CHAMPION_STREAK_KEY] = 1
            else:
                previous_best = (
                    request.user.revenue_duel_streak_best if request.user.is_authenticated
                    else request.session.get(REVENUE_DUEL_BEST_ANON_KEY, 0)
                )
                final_streak = streak
                is_new_record = streak > previous_best
                _register_revenue_duel_best(request, streak)
                request.session[REVENUE_DUEL_STREAK_KEY] = 0
                request.session.pop(REVENUE_DUEL_CHAMPION_KEY, None)
                request.session.pop(REVENUE_DUEL_CHAMPION_STREAK_KEY, None)
                request.session.pop(REVENUE_DUEL_MAX_REPEATS_KEY, None)
                streak = 0
                game_over = True

            round_result = {
                "left_id": left.pk, "right_id": right.pk,
                "left_title": left.title, "right_title": right.title,
                "left_poster": left.poster_url, "right_poster": right.poster_url,
                "left_revenue": left.revenue_display, "right_revenue": right.revenue_display,
                "choice": choice, "winner_side": "left" if left_wins else "right", "correct": correct,
                "game_over": game_over, "final_streak": final_streak, "is_new_record": is_new_record,
            }
            request.session[REVENUE_DUEL_ROUND_KEY] = round_result

    champion = challenger = None
    if not round_result:
        champion_id = request.session.get(REVENUE_DUEL_CHAMPION_KEY)
        champion = Movie.objects.filter(pk=champion_id, revenue__isnull=False, media_type="movie").first() if champion_id else None
        if champion is None:
            champion = _pick_grossing_movie(request)
            if champion:
                request.session[REVENUE_DUEL_CHAMPION_KEY] = champion.pk
                request.session[REVENUE_DUEL_CHAMPION_STREAK_KEY] = 1
        challenger = _pick_grossing_movie(request, exclude_id=champion.pk) if champion else None

    best = (
        request.user.revenue_duel_streak_best if request.user.is_authenticated
        else request.session.get(REVENUE_DUEL_BEST_ANON_KEY, 0)
    )

    return render(request, "games/revenue_duel.html", {
        "left": champion, "right": challenger, "streak": streak, "best": best, "round_result": round_result,
    })


# --- Trivial / Emoji / Malas descripciones / Cuál tiene al actor ---------
# Las cuatro comparten la misma mecánica (enunciado + 3 opciones, racha
# hasta fallar) que ya usa Frases célebres, así que reutilizan un único
# motor genérico (`_trivia_game`) parametrizado por categoría — solo cambia
# qué enunciado se muestra y en qué plantilla, cada una con su propio campo
# de mejor racha en el usuario.

TRIVIA_BEST_FIELDS = {
    TriviaQuestion.Category.TRIVIA: "trivia_streak_best",
    TriviaQuestion.Category.EMOJI: "emoji_streak_best",
    TriviaQuestion.Category.BAD_DESCRIPTION: "bad_description_streak_best",
    TriviaQuestion.Category.ACTOR: "actor_streak_best",
}


def _trivia_streak_key(category):
    return f"trivia_streak_{category}"


def _trivia_best_anon_key(category):
    return f"trivia_streak_best_anon_{category}"


def _trivia_seen_key(category):
    return f"trivia_seen_{category}"


def _register_trivia_best(request, category, streak):
    field = TRIVIA_BEST_FIELDS[category]
    if request.user.is_authenticated:
        if streak > getattr(request.user, field):
            setattr(request.user, field, streak)
            request.user.save(update_fields=[field])
    else:
        key = _trivia_best_anon_key(category)
        if streak > request.session.get(key, 0):
            request.session[key] = streak


def _trivia_game(request, category, template, prompt=None):
    """El pool de cada categoría es lo bastante grande para que agotarlo
    sea difícil — pero por si acaso: dentro de una misma partida no se
    repite ninguna pregunta ya vista (`seen_key`, se resetea al fallar o al
    ganar), y si se acaban de verdad sin haber fallado ninguna, se corta la
    partida con pantalla de victoria en vez de reciclar preguntas.

    `prompt` es un transform opcional sobre `question.prompt` para la
    plantilla (ver `emoji_game`, que solo enseña el primer emoji)."""
    streak_key = _trivia_streak_key(category)
    seen_key = _trivia_seen_key(category)
    streak = request.session.get(streak_key, 0)
    seen_ids = request.session.get(seen_key, [])
    game_over = False
    game_won = False
    is_new_record = False
    final_streak = None
    wrong_answer = None

    if request.method == "POST":
        question = get_object_or_404(TriviaQuestion, pk=request.POST.get("question_id"), category=category)
        seen_ids.append(question.pk)
        request.session[seen_key] = seen_ids
        if request.POST.get("answer") == question.correct_answer:
            streak += 1
            request.session[streak_key] = streak
        else:
            field = TRIVIA_BEST_FIELDS[category]
            previous_best = (
                getattr(request.user, field) if request.user.is_authenticated
                else request.session.get(_trivia_best_anon_key(category), 0)
            )
            final_streak = streak
            is_new_record = streak > previous_best
            wrong_answer = question.correct_answer
            _register_trivia_best(request, category, streak)
            request.session[streak_key] = 0
            request.session.pop(seen_key, None)
            streak = 0
            game_over = True

    next_question = None
    options = []
    if not game_over:
        next_question = TriviaQuestion.objects.filter(category=category).exclude(pk__in=seen_ids).order_by("?").first()
        if next_question is None and seen_ids:
            field = TRIVIA_BEST_FIELDS[category]
            previous_best = (
                getattr(request.user, field) if request.user.is_authenticated
                else request.session.get(_trivia_best_anon_key(category), 0)
            )
            final_streak = streak
            is_new_record = streak > previous_best
            _register_trivia_best(request, category, streak)
            request.session[streak_key] = 0
            request.session.pop(seen_key, None)
            streak = 0
            game_won = True
        elif next_question:
            options = [next_question.correct_answer, next_question.wrong_answer_1, next_question.wrong_answer_2]
            random.shuffle(options)

    field = TRIVIA_BEST_FIELDS[category]
    best = (
        getattr(request.user, field) if request.user.is_authenticated
        else request.session.get(_trivia_best_anon_key(category), 0)
    )

    return render(request, template, {
        "question": next_question, "options": options, "streak": streak, "best": best,
        "game_over": game_over, "game_won": game_won, "is_new_record": is_new_record,
        "final_streak": final_streak, "wrong_answer": wrong_answer,
        "prompt": prompt(next_question.prompt) if prompt and next_question else (next_question.prompt if next_question else ""),
    })


def trivia_game(request):
    return _trivia_game(request, TriviaQuestion.Category.TRIVIA, "games/trivia_game.html")


def emoji_game(request):
    # Un único emoji, una única respuesta: como cualquier otra categoría de
    # _trivia_game, fallar rompe la racha directamente (antes se revelaban
    # los emojis del prompt de uno en uno con varios intentos por pregunta;
    # ahora solo se enseña el primero, sea cual sea la longitud del prompt).
    return _trivia_game(
        request, TriviaQuestion.Category.EMOJI, "games/emoji_game.html",
        prompt=lambda p: p.split()[0] if p.split() else p,
    )


def bad_description_game(request):
    return _trivia_game(request, TriviaQuestion.Category.BAD_DESCRIPTION, "games/bad_description_game.html")


def actor_game(request):
    return _trivia_game(request, TriviaQuestion.Category.ACTOR, "games/actor_game.html")


# --- Verdadero o falso -----------------------------------------------------

TRUE_FALSE_STREAK_KEY = "true_false_streak"
TRUE_FALSE_BEST_ANON_KEY = "true_false_streak_best_anon"
TRUE_FALSE_SEEN_KEY = "true_false_seen"


def _register_true_false_best(request, streak):
    if request.user.is_authenticated:
        if streak > request.user.true_false_streak_best:
            request.user.true_false_streak_best = streak
            request.user.save(update_fields=["true_false_streak_best"])
    elif streak > request.session.get(TRUE_FALSE_BEST_ANON_KEY, 0):
        request.session[TRUE_FALSE_BEST_ANON_KEY] = streak


def true_false_game(request):
    streak = request.session.get(TRUE_FALSE_STREAK_KEY, 0)
    seen_ids = request.session.get(TRUE_FALSE_SEEN_KEY, [])
    game_over = False
    game_won = False
    is_new_record = False
    final_streak = None
    correct_answer = None

    if request.method == "POST":
        statement = get_object_or_404(TrueFalseStatement, pk=request.POST.get("statement_id"))
        seen_ids.append(statement.pk)
        request.session[TRUE_FALSE_SEEN_KEY] = seen_ids
        answer = request.POST.get("answer") == "true"
        if answer == statement.is_true:
            streak += 1
            request.session[TRUE_FALSE_STREAK_KEY] = streak
        else:
            previous_best = (
                request.user.true_false_streak_best if request.user.is_authenticated
                else request.session.get(TRUE_FALSE_BEST_ANON_KEY, 0)
            )
            final_streak = streak
            is_new_record = streak > previous_best
            correct_answer = statement.is_true
            _register_true_false_best(request, streak)
            request.session[TRUE_FALSE_STREAK_KEY] = 0
            request.session.pop(TRUE_FALSE_SEEN_KEY, None)
            streak = 0
            game_over = True

    next_statement = None
    if not game_over:
        next_statement = TrueFalseStatement.objects.exclude(pk__in=seen_ids).order_by("?").first()
        if next_statement is None and seen_ids:
            previous_best = (
                request.user.true_false_streak_best if request.user.is_authenticated
                else request.session.get(TRUE_FALSE_BEST_ANON_KEY, 0)
            )
            final_streak = streak
            is_new_record = streak > previous_best
            _register_true_false_best(request, streak)
            request.session[TRUE_FALSE_STREAK_KEY] = 0
            request.session.pop(TRUE_FALSE_SEEN_KEY, None)
            streak = 0
            game_won = True

    best = (
        request.user.true_false_streak_best if request.user.is_authenticated
        else request.session.get(TRUE_FALSE_BEST_ANON_KEY, 0)
    )

    return render(request, "games/true_false_game.html", {
        "statement": next_statement, "streak": streak, "best": best,
        "game_over": game_over, "game_won": game_won, "is_new_record": is_new_record,
        "final_streak": final_streak, "correct_answer": correct_answer,
    })


# --- Qué personaje eres ----------------------------------------------------
# Test de personalidad clásico: preguntas en orden fijo, cada respuesta suma
# un punto a un personaje, y al final gana el que más puntos tiene — sin
# racha ni fallo, no es un juego de acertar. El índice de la pregunta actual
# y los puntos acumulados viven en sesión mientras dura el test.

PERSONALITY_INDEX_KEY = "personality_quiz_index"
PERSONALITY_SCORES_KEY = "personality_quiz_scores"


def personality_quiz(request):
    if request.method == "POST" and request.POST.get("restart"):
        request.session.pop(PERSONALITY_INDEX_KEY, None)
        request.session.pop(PERSONALITY_SCORES_KEY, None)
        return redirect("games:personality-quiz")

    questions = list(PersonalityQuestion.objects.prefetch_related("answers"))
    total = len(questions)
    index = request.session.get(PERSONALITY_INDEX_KEY, 0)
    scores = request.session.get(PERSONALITY_SCORES_KEY, {})
    # Si la sesión venía de una partida a medias con un formato antiguo
    # (versiones previas guardaban un contador, no la lista de respuestas),
    # se descarta en vez de reventar al intentar usarla como lista.
    if not all(isinstance(value, list) for value in scores.values()):
        scores = {}
        index = 0

    if request.method == "POST" and 0 <= index < total:
        try:
            answer = PersonalityAnswer.objects.get(pk=request.POST.get("answer_id"), question=questions[index])
        except (PersonalityAnswer.DoesNotExist, ValueError, TypeError):
            # Partida a medias de antes de un cambio de contenido del test
            # (la respuesta que se envía ya no existe en esa pregunta) — se
            # reinicia en limpio en vez de romper con un error.
            request.session.pop(PERSONALITY_INDEX_KEY, None)
            request.session.pop(PERSONALITY_SCORES_KEY, None)
            return redirect("games:personality-quiz")
        char_id = str(answer.character_id)
        # Se guarda el propio texto de cada respuesta elegida (no solo un
        # contador) para poder explicar el resultado con tus respuestas.
        scores.setdefault(char_id, []).append(answer.text)
        index += 1
        request.session[PERSONALITY_SCORES_KEY] = scores
        request.session[PERSONALITY_INDEX_KEY] = index

    if total and index >= total:
        result = None
        why = []
        if scores:
            best_id = max(scores, key=lambda char_id: len(scores[char_id]))
            result = PersonalityCharacter.objects.filter(pk=best_id).first()
            why = scores[best_id]
        return render(request, "games/personality_quiz_result.html", {"character": result, "why": why})

    question = questions[index] if index < total else None
    return render(request, "games/personality_quiz.html", {
        "question": question, "progress": index + 1 if question else 0, "total": total,
    })


# --- Duelos --------------------------------------------------------------
# Duelo entre dos amigos, a elegir de entre varios juegos de trivia (todos
# con la misma forma: enunciado + respuesta correcta + 2 incorrectas): los
# dos ven la misma pregunta a la vez y avanzan juntos ronda a ronda
# (Duel.current_index, compartido); en cuanto uno falla, el duelo termina
# ahí mismo para los dos. Empieza como invitación (PENDING) hasta que el
# retado la acepta. DUEL_GAMES es el registro de qué modelo/campos usa cada
# juego disponible para duelo — añadir un juego nuevo aquí es lo único que
# hace falta para que también se pueda retar a él.

DUEL_GAMES = {
    Duel.Game.QUOTES: {
        "model": MovieQuote,
        "queryset": lambda: MovieQuote.objects.all(),
        "prompt": lambda obj: obj.quote,
        "correct": lambda obj: obj.correct_title,
        "wrong": lambda obj: (obj.wrong_title_1, obj.wrong_title_2),
    },
    Duel.Game.TRIVIA: {
        "model": TriviaQuestion,
        "queryset": lambda: TriviaQuestion.objects.filter(category=TriviaQuestion.Category.TRIVIA),
        "prompt": lambda obj: obj.prompt,
        "correct": lambda obj: obj.correct_answer,
        "wrong": lambda obj: (obj.wrong_answer_1, obj.wrong_answer_2),
    },
    Duel.Game.BAD_DESCRIPTION: {
        "model": TriviaQuestion,
        "queryset": lambda: TriviaQuestion.objects.filter(category=TriviaQuestion.Category.BAD_DESCRIPTION),
        "prompt": lambda obj: obj.prompt,
        "correct": lambda obj: obj.correct_answer,
        "wrong": lambda obj: (obj.wrong_answer_1, obj.wrong_answer_2),
    },
    Duel.Game.ACTOR: {
        "model": TriviaQuestion,
        "queryset": lambda: TriviaQuestion.objects.filter(category=TriviaQuestion.Category.ACTOR),
        "prompt": lambda obj: obj.prompt,
        "correct": lambda obj: obj.correct_answer,
        "wrong": lambda obj: (obj.wrong_answer_1, obj.wrong_answer_2),
    },
    Duel.Game.EMOJI: {
        # Aquí (a diferencia del modo en solitario) se ven todos los emojis
        # de golpe, no de uno en uno — revelarlos progresivamente solo tiene
        # sentido cuando juega una sola persona contra sí misma; en un duelo
        # los dos ven la misma ronda a la vez y hay que poder responder ya.
        "model": TriviaQuestion,
        "queryset": lambda: TriviaQuestion.objects.filter(category=TriviaQuestion.Category.EMOJI),
        "prompt": lambda obj: obj.prompt,
        "correct": lambda obj: obj.correct_answer,
        "wrong": lambda obj: (obj.wrong_answer_1, obj.wrong_answer_2),
    },
    Duel.Game.TRUE_FALSE: {
        "model": TrueFalseStatement,
        "queryset": lambda: TrueFalseStatement.objects.all(),
        "prompt": lambda obj: obj.statement,
        "correct": lambda obj: "Verdadero" if obj.is_true else "Falso",
        "wrong": lambda obj: ("Falso" if obj.is_true else "Verdadero",),
    },
    # "compare" es una forma de ronda distinta (dos portadas, no pregunta +
    # opciones de texto): en vez de "correct"/"wrong", usa "field" (el
    # atributo del Movie a comparar) y "format" (cómo se enseña ese valor).
    Duel.Game.RATING: {
        "kind": "compare",
        "queryset": lambda: Movie.objects.filter(imdb_rating__isnull=False, media_type="movie"),
        "field": "imdb_rating",
        "format": lambda movie: f"⭐ {movie.imdb_rating}",
    },
    Duel.Game.REVENUE: {
        "kind": "compare",
        "queryset": lambda: Movie.objects.filter(revenue__isnull=False, media_type="movie"),
        "field": "revenue",
        "format": lambda movie: f"💰 {movie.revenue_display}",
    },
}


def _pick_quote_id():
    return MovieQuote.objects.order_by("?").values_list("pk", flat=True).first()


def _duel_is_compare(game):
    return DUEL_GAMES[game].get("kind") == "compare"


def _pick_duel_round(game):
    """Para juegos de texto (pregunta + opciones), una ronda es un solo id.
    Para juegos "compare" (dos portadas, p. ej. Cuál está mejor valorada),
    una ronda son dos ids — ninguna campeona persistente entre rondas como
    en el modo en solitario, cada ronda del duelo sortea un par nuevo."""
    config = DUEL_GAMES[game]
    if config.get("kind") == "compare":
        pair = list(config["queryset"]().order_by("?").values_list("pk", flat=True)[:2])
        return pair if len(pair) == 2 else None
    return config["queryset"]().order_by("?").values_list("pk", flat=True).first()


def _duel_round_object(game, round_id):
    return get_object_or_404(DUEL_GAMES[game]["model"], pk=round_id)


def _duel_round_context(game, round_obj):
    config = DUEL_GAMES[game]
    correct = config["correct"](round_obj)
    options = [correct, *config["wrong"](round_obj)]
    random.shuffle(options)
    return config["prompt"](round_obj), correct, options


@login_required
def duel_invite(request, username):
    other = get_object_or_404(User, username=username)
    if request.method == "POST" and other.pk != request.user.pk and are_friends(request.user, other):
        game = request.POST.get("game")
        if game not in DUEL_GAMES:
            game = Duel.Game.QUOTES
        round_id = _pick_duel_round(game)
        if round_id is None:
            messages.error(request, "Todavía no hay preguntas cargadas para ese juego.")
        else:
            duel = Duel.objects.create(challenger=request.user, opponent=other, game=game, round_ids=[round_id])
            duel_url = request.build_absolute_uri(reverse("games:duel-detail", args=[duel.pk]))
            Message.objects.create(
                sender=request.user, recipient=other,
                body=f"¡Te reto a un duelo de {duel.get_game_display()}! {duel_url}",
            )
            messages.success(request, f"Solicitud de duelo enviada a {other.username}.")
            return redirect("games:duel-detail", pk=duel.pk)
    return redirect("games:hub")


@login_required
def duel_accept(request, pk):
    duel = get_object_or_404(Duel, pk=pk, opponent=request.user, status=Duel.Status.PENDING)
    if request.method == "POST":
        duel.status = Duel.Status.ACTIVE
        duel.save(update_fields=["status"])
    return redirect("games:duel-detail", pk=pk)


def _delete_duel_invite_message(duel):
    """Borra el mensaje de Social con el que se invitó a este duelo — una
    vez el duelo termina (rechazado, o jugado hasta el final y cerrado), ese
    mensaje ya no lleva a ninguna parte (el enlace apuntaba a un duelo que
    va a dejar de existir), así que no tiene sentido dejarlo en la
    conversación."""
    duel_path = reverse("games:duel-detail", args=[duel.pk])
    Message.objects.filter(body__contains=duel_path).delete()


@login_required
def duel_decline(request, pk):
    duel = get_object_or_404(Duel, pk=pk, opponent=request.user, status=Duel.Status.PENDING)
    if request.method == "POST":
        _delete_duel_invite_message(duel)
        duel.delete()
        messages.info(request, "Duelo rechazado.")
        return redirect("games:hub")
    return redirect("games:duel-detail", pk=pk)


@login_required
def duel_leave(request, pk):
    """Al salir de un duelo ya terminado, se borra: el resultado ya quedó
    registrado en el marcador (`DuelRecord`) en el momento en que acabó, así
    que no hace falta seguir acumulando duelos viejos en "Tus duelos"."""
    duel = get_object_or_404(Duel, pk=pk)
    if duel.role_for(request.user) is None:
        raise Http404
    if request.method == "POST" and duel.status == Duel.Status.FINISHED:
        _delete_duel_invite_message(duel)
        duel.delete()
    return redirect("games:hub")


@login_required
def duel_detail(request, pk):
    duel = get_object_or_404(Duel.objects.select_related("challenger", "opponent"), pk=pk)
    role = duel.role_for(request.user)
    if role is None:
        raise Http404

    if duel.status == Duel.Status.PENDING:
        return render(request, "games/duel_pending.html", {"duel": duel, "role": role})

    if duel.status == Duel.Status.FINISHED:
        if request.method == "POST" and not duel.wants_rematch_for(request.user):
            field = "challenger_wants_rematch" if role == "challenger" else "opponent_wants_rematch"
            setattr(duel, field, True)
            duel.save(update_fields=[field])
            if duel.challenger_wants_rematch and duel.opponent_wants_rematch:
                first_round_id = _pick_duel_round(duel.game)
                if first_round_id is not None:
                    duel.reset_for_rematch(first_round_id)
                    return redirect("games:duel-detail", pk=pk)
        return render(request, "games/duel_result.html", {
            "duel": duel, "role": role, "wants_rematch": duel.wants_rematch_for(request.user),
        })

    # ACTIVE: los dos juegan la misma ronda (duel.current_index) a la vez.
    is_compare = _duel_is_compare(duel.game)
    if request.method == "POST" and not duel.answered_for(request.user):
        if is_compare:
            field = DUEL_GAMES[duel.game]["field"]
            left = get_object_or_404(Movie, pk=request.POST.get("left_id"))
            right = get_object_or_404(Movie, pk=request.POST.get("right_id"))
            left_wins = getattr(left, field) >= getattr(right, field)
            correct = (request.POST.get("choice") == "left") == left_wins
        else:
            round_obj = _duel_round_object(duel.game, request.POST.get("round_id"))
            correct = request.POST.get("answer") == DUEL_GAMES[duel.game]["correct"](round_obj)

        if not correct:
            if role == "challenger":
                duel.challenger_lost = True
            else:
                duel.opponent_lost = True
            duel.status = Duel.Status.FINISHED
            duel.save()
            DuelRecord.record_result(duel.challenger, duel.opponent, duel.winner)
            _delete_duel_invite_message(duel)
            return render(request, "games/duel_result.html", {"duel": duel, "role": role})

        if role == "challenger":
            duel.challenger_answered = True
            duel.challenger_streak += 1
        else:
            duel.opponent_answered = True
            duel.opponent_streak += 1

        if duel.challenger_answered and duel.opponent_answered:
            duel.current_index += 1
            duel.challenger_answered = False
            duel.opponent_answered = False
            if duel.current_index >= len(duel.round_ids):
                duel.round_ids.append(_pick_duel_round(duel.game))  # se juega hasta fallar, no hay tanda fija
        duel.save()

    if duel.answered_for(request.user):
        return render(request, "games/duel_waiting.html", {
            "duel": duel, "role": role, "streak": duel.streak_for(request.user),
        })

    if is_compare:
        config = DUEL_GAMES[duel.game]
        left_id, right_id = duel.round_ids[duel.current_index]
        left = get_object_or_404(Movie, pk=left_id)
        right = get_object_or_404(Movie, pk=right_id)
        return render(request, "games/duel_play_compare.html", {
            "duel": duel, "left": left, "right": right,
            "left_display": config["format"](left), "right_display": config["format"](right),
            "streak": duel.streak_for(request.user),
        })

    round_obj = _duel_round_object(duel.game, duel.round_ids[duel.current_index])
    prompt, _correct, options = _duel_round_context(duel.game, round_obj)
    return render(request, "games/duel_play.html", {
        "duel": duel, "prompt": prompt, "round_id": round_obj.pk, "options": options,
        "streak": duel.streak_for(request.user),
    })


# --- Tier list personal (juego) ------------------------------------------
# Cada usuario tiene la suya propia — distinta de la de Top Secret (esa es
# una sola, del dueño del sitio). Los niveles son editables (nombre, color,
# añadir/borrar) igual que en la de Top Secret, pero cada usuario tiene los
# suyos, sin compartir ni mostrar nada a nadie más.

def _ensure_default_tier_levels(user):
    if not GameTierLevel.objects.filter(user=user).exists():
        GameTierLevel.objects.bulk_create([
            GameTierLevel(user=user, name=name, color=color, order=order)
            for order, (name, color) in enumerate(DEFAULT_TIER_LEVELS)
        ])


@login_required
def tier_list(request):
    _ensure_default_tier_levels(request.user)
    levels = list(GameTierLevel.objects.filter(user=request.user).order_by("order"))
    buckets = {None: []}
    buckets.update({level.pk: [] for level in levels})
    for entry in GameTierEntry.objects.filter(user=request.user).select_related("movie", "tier"):
        buckets[entry.tier_id].append(entry)

    level_rows = [(level, buckets[level.pk]) for level in levels]
    return render(request, "games/tier_list.html", {
        "level_rows": level_rows, "unsorted_entries": buckets[None],
    })


@login_required
def tier_list_search(request):
    query = request.GET.get("query", "").strip()
    results = []
    error = None
    if query:
        try:
            results = tmdb_search(query)[:8]
        except MovieAPIError as exc:
            error = str(exc)
    return render(request, "games/_tier_search_results.html", {
        "results": results, "error": error, "query": query,
    })


@login_required
def tier_list_add(request, tmdb_id):
    if request.method == "POST":
        try:
            movie = Movie.get_or_create_from_tmdb(tmdb_id)
        except MovieAPIError as exc:
            messages.error(request, str(exc))
        else:
            GameTierEntry.objects.get_or_create(user=request.user, movie=movie, defaults={"tier": None})
    return redirect("games:tier-list")


@login_required
def tier_list_move(request, pk):
    if request.method != "POST":
        raise Http404
    entry = get_object_or_404(GameTierEntry, pk=pk, user=request.user)
    raw_tier = request.POST.get("tier", "")
    level = None
    if raw_tier:
        try:
            level = GameTierLevel.objects.get(pk=raw_tier, user=request.user)
        except (GameTierLevel.DoesNotExist, ValueError):
            return JsonResponse({"ok": False, "error": "nivel inválido"}, status=400)

    max_order = GameTierEntry.objects.filter(
        user=request.user, tier=level,
    ).aggregate(Max("order"))["order__max"] or 0
    entry.tier = level
    entry.order = max_order + 1
    entry.save(update_fields=["tier", "order"])
    return JsonResponse({"ok": True})


@login_required
def tier_level_create(request):
    if request.method == "POST":
        form = GameTierLevelForm(request.POST)
        if form.is_valid():
            max_order = GameTierLevel.objects.filter(user=request.user).aggregate(Max("order"))["order__max"] or 0
            level = form.save(commit=False)
            level.user = request.user
            level.order = max_order + 1
            level.save()
        else:
            messages.error(request, "No se pudo añadir el nivel.")
    return redirect("games:tier-list")


@login_required
def tier_level_update(request, pk):
    level = get_object_or_404(GameTierLevel, pk=pk, user=request.user)
    if request.method == "POST":
        form = GameTierLevelForm(request.POST, instance=level)
        if form.is_valid():
            form.save()
        else:
            messages.error(request, "No se pudo guardar el nivel.")
    return redirect("games:tier-list")


@login_required
def tier_level_delete(request, pk):
    level = get_object_or_404(GameTierLevel, pk=pk, user=request.user)
    if request.method == "POST":
        level.delete()
        messages.success(request, "Nivel borrado. Sus películas han vuelto a 'Sin clasificar'.")
    return redirect("games:tier-list")


@login_required
def tier_list_reset(request):
    if request.method == "POST":
        GameTierEntry.objects.filter(user=request.user).delete()
        messages.success(request, "Tu tier list se ha vaciado. Puedes empezar de nuevo.")
    return redirect("games:tier-list")


# --- Candidatos al Oscar ---------------------------------------------------
# Herramienta compartida, no un juego de racha: cualquiera propone
# candidatas (películas del catálogo) por categoría y vota por su favorita
# — un voto por categoría y usuario, votar de nuevo reemplaza el anterior.

def oscar_home(request):
    categories = OscarCategory.objects.prefetch_related("candidates__movie", "candidates__votes")
    my_votes = {}
    if request.user.is_authenticated:
        my_votes = dict(
            OscarVote.objects.filter(user=request.user).values_list("category_id", "candidate_id")
        )

    category_rows = []
    for category in categories:
        candidates = sorted(category.candidates.all(), key=lambda c: len(c.votes.all()), reverse=True)
        category_rows.append({
            "category": category,
            "candidates": candidates,
            "my_vote_id": my_votes.get(category.pk),
        })

    return render(request, "games/oscars.html", {"category_rows": category_rows})


@login_required
def oscar_candidate_search(request, category_id):
    """Busca en TMDb películas o personas, según `category.candidate_type`
    — las categorías de intérpretes/dirección proponen personas (con foto),
    el resto proponen películas del catálogo, igual que en el tier list."""
    category = get_object_or_404(OscarCategory, pk=category_id)
    query = request.GET.get("query", "").strip()
    results = []
    error = None
    if query:
        try:
            if category.candidate_type == OscarCategory.CandidateType.PERSON:
                results = tmdb_search_person(query)[:8]
            else:
                results = tmdb_search(query)[:8]
        except MovieAPIError as exc:
            error = str(exc)
    return render(request, "games/_oscar_search_results.html", {
        "results": results, "error": error, "query": query, "category": category,
    })


@login_required
def oscar_candidate_add(request, category_id, tmdb_id):
    """Proponer ES votar: cada usuario tiene una única candidata por
    categoría (`OscarVote`, un voto por categoría y usuario) — proponer
    aquí siempre pone esta candidata como la tuya, sustituyendo la anterior
    si ya habías propuesto/votado otra. Si alguien más ya la había
    propuesto, no se duplica: tu voto se suma al contador de esa misma."""
    category = get_object_or_404(
        OscarCategory, pk=category_id, is_open=True, candidate_type=OscarCategory.CandidateType.MOVIE,
    )
    if request.method == "POST":
        try:
            movie = Movie.get_or_create_from_tmdb(tmdb_id)
        except MovieAPIError as exc:
            messages.error(request, str(exc))
        else:
            candidate, _ = OscarCandidate.objects.get_or_create(
                category=category, movie=movie, defaults={"submitted_by": request.user},
            )
            OscarVote.objects.update_or_create(
                category=category, user=request.user, defaults={"candidate": candidate},
            )
            messages.success(request, f"Tu propuesta en {category.name} es «{movie.title}».")
    return redirect("games:oscars")


@login_required
def oscar_candidate_add_person(request, category_id):
    category = get_object_or_404(
        OscarCategory, pk=category_id, is_open=True, candidate_type=OscarCategory.CandidateType.PERSON,
    )
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        tmdb_person_id = request.POST.get("tmdb_person_id")
        if name and tmdb_person_id:
            candidate, _ = OscarCandidate.objects.get_or_create(
                category=category, person_tmdb_id=tmdb_person_id,
                defaults={
                    "person_name": name, "person_photo_url": request.POST.get("photo_url", ""),
                    "submitted_by": request.user,
                },
            )
            OscarVote.objects.update_or_create(
                category=category, user=request.user, defaults={"candidate": candidate},
            )
            messages.success(request, f"Tu propuesta en {category.name} es «{name}».")
    return redirect("games:oscars")


@login_required
def oscar_vote(request, candidate_id):
    candidate = get_object_or_404(OscarCandidate, pk=candidate_id, category__is_open=True)
    if request.method == "POST":
        OscarVote.objects.update_or_create(
            category=candidate.category, user=request.user, defaults={"candidate": candidate},
        )
        messages.success(request, f"Voto registrado por «{candidate.display_title}».")
    return redirect("games:oscars")


@login_required
def oscar_candidate_withdraw(request, candidate_id):
    """Retirar una candidata propuesta por error (título repetido, persona
    equivocada...) — solo quien la propuso o un admin pueden quitarla; se
    borra entera junto con los votos que tuviera (on_delete=CASCADE en
    OscarVote.candidate), no solo el propio voto."""
    candidate = get_object_or_404(OscarCandidate, pk=candidate_id)
    if candidate.submitted_by_id != request.user.pk and not request.user.is_staff:
        messages.error(request, "Solo quien propuso una candidata (o un admin) puede retirarla.")
        return redirect("games:oscars")
    if request.method == "POST":
        title = candidate.display_title
        candidate.delete()
        messages.success(request, f"Candidata «{title}» retirada.")
    return redirect("games:oscars")
