import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.accounts.models import User
from apps.movies.models import Movie
from apps.movies.services import MovieAPIError, tmdb_search
from apps.social.models import Message, are_friends, friends_of

from .forms import GameTierLevelForm
from .models import Duel, DuelRecord, GameTierEntry, GameTierLevel, MovieQuote

DEFAULT_TIER_LEVELS = [
    ("S", "#FFD700"),
    ("A", "#FFA94D"),
    ("B", "#A9E34B"),
    ("C", "#74C0FC"),
    ("D", "#D98C8C"),
]

QUOTE_STREAK_KEY = "quote_streak"
QUOTE_BEST_ANON_KEY = "quote_streak_best_anon"


def games_hub(request):
    duels = []
    friends = []
    if request.user.is_authenticated:
        duels = Duel.objects.filter(
            Q(challenger=request.user) | Q(opponent=request.user)
        ).select_related("challenger", "opponent")
        friends = friends_of(request.user)
    return render(request, "games/games.html", {"duels": duels, "friends": friends})


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


# --- Duelos --------------------------------------------------------------
# Duelo de Frases célebres entre dos amigos: los dos ven la misma pregunta
# a la vez y avanzan juntos ronda a ronda (Duel.current_index, compartido);
# en cuanto uno falla, el duelo termina ahí mismo para los dos. Empieza
# como invitación (PENDING) hasta que el retado la acepta.

def _pick_quote_id():
    return MovieQuote.objects.order_by("?").values_list("pk", flat=True).first()


@login_required
def duel_invite(request, username):
    other = get_object_or_404(User, username=username)
    if request.method == "POST" and other.pk != request.user.pk and are_friends(request.user, other):
        quote_id = _pick_quote_id()
        if quote_id is None:
            messages.error(request, "Todavía no hay frases cargadas para un duelo.")
        else:
            duel = Duel.objects.create(challenger=request.user, opponent=other, quote_ids=[quote_id])
            duel_url = request.build_absolute_uri(reverse("games:duel-detail", args=[duel.pk]))
            Message.objects.create(
                sender=request.user, recipient=other,
                body=f"¡Te reto a un duelo de Frases célebres! {duel_url}",
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
                duel.reset_for_rematch()
                return redirect("games:duel-detail", pk=pk)
        return render(request, "games/duel_result.html", {
            "duel": duel, "role": role, "wants_rematch": duel.wants_rematch_for(request.user),
        })

    # ACTIVE: los dos juegan la misma ronda (duel.current_index) a la vez.
    if request.method == "POST" and not duel.answered_for(request.user):
        quote = get_object_or_404(MovieQuote, pk=request.POST.get("quote_id"))
        correct = request.POST.get("answer") == quote.correct_title

        if not correct:
            if role == "challenger":
                duel.challenger_lost = True
            else:
                duel.opponent_lost = True
            duel.status = Duel.Status.FINISHED
            duel.save()
            DuelRecord.record_result(duel.challenger, duel.opponent, duel.winner)
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
            if duel.current_index >= len(duel.quote_ids):
                duel.quote_ids.append(_pick_quote_id())  # se juega hasta fallar, no hay tanda fija
        duel.save()

    if duel.answered_for(request.user):
        return render(request, "games/duel_waiting.html", {
            "duel": duel, "role": role, "streak": duel.streak_for(request.user),
        })

    quote = get_object_or_404(MovieQuote, pk=duel.quote_ids[duel.current_index])
    options = [quote.correct_title, quote.wrong_title_1, quote.wrong_title_2]
    random.shuffle(options)
    return render(request, "games/duel_play.html", {
        "duel": duel, "quote": quote, "options": options,
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
