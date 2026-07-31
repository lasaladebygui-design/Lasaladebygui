import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.accounts.models import User
from apps.social.models import Message, are_friends, friends_of

from .models import Duel, MovieQuote

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
# Duelo de Frases célebres entre dos amigos: mismo duelo, misma tanda de
# frases (orden fijo) jugada por separado, y al final se compara la racha.

@login_required
def duel_invite(request, username):
    other = get_object_or_404(User, username=username)
    if request.method == "POST" and other.pk != request.user.pk and are_friends(request.user, other):
        quote_ids = list(MovieQuote.objects.order_by("?").values_list("pk", flat=True)[:Duel.QUOTE_COUNT])
        if len(quote_ids) < Duel.QUOTE_COUNT:
            messages.error(request, "Todavía no hay frases suficientes para un duelo.")
        else:
            duel = Duel.objects.create(challenger=request.user, opponent=other, quote_ids=quote_ids)
            duel_url = request.build_absolute_uri(reverse("games:duel-detail", args=[duel.pk]))
            Message.objects.create(
                sender=request.user, recipient=other,
                body=f"¡Te reto a un duelo de Frases célebres! {duel_url}",
            )
            messages.success(request, f"Duelo enviado a {other.username}.")
            return redirect("games:duel-detail", pk=duel.pk)
    return redirect("games:hub")


@login_required
def duel_detail(request, pk):
    duel = get_object_or_404(Duel.objects.select_related("challenger", "opponent"), pk=pk)
    role = duel.role_for(request.user)
    if role is None:
        raise Http404

    if duel.has_finished(request.user):
        return render(request, "games/duel_result.html", {"duel": duel, "role": role})

    position_key = f"duel_{duel.pk}_position"
    streak_key = f"duel_{duel.pk}_streak"
    position = request.session.get(position_key, 0)
    streak = request.session.get(streak_key, 0)

    if request.method == "POST":
        quote = get_object_or_404(MovieQuote, pk=request.POST.get("quote_id"))
        correct = request.POST.get("answer") == quote.correct_title
        if correct:
            streak += 1
            position += 1
            request.session[position_key] = position
            request.session[streak_key] = streak
        else:
            position = len(duel.quote_ids)

        if not correct or position >= len(duel.quote_ids):
            if role == "challenger":
                duel.challenger_streak = streak
                duel.challenger_finished = True
            else:
                duel.opponent_streak = streak
                duel.opponent_finished = True
            if duel.both_finished:
                duel.status = Duel.Status.FINISHED
            duel.save()
            request.session.pop(position_key, None)
            request.session.pop(streak_key, None)
            return render(request, "games/duel_result.html", {"duel": duel, "role": role})

    quote = get_object_or_404(MovieQuote, pk=duel.quote_ids[position])
    options = [quote.correct_title, quote.wrong_title_1, quote.wrong_title_2]
    random.shuffle(options)
    return render(request, "games/duel_play.html", {
        "duel": duel, "quote": quote, "options": options, "streak": streak,
        "position": position + 1, "total": len(duel.quote_ids),
    })
