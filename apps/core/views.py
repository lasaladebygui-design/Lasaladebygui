import random

from django.contrib import messages
from django.core.mail import EmailMessage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from apps.articles.models import Article
from apps.secret.models import MovieQuote

from .forms import ContactForm
from .models import SESSION_THEME_KEY, ContactLink, SiteConfig, Theme, get_effective_theme

QUOTE_STREAK_KEY = "quote_streak"
QUOTE_BEST_ANON_KEY = "quote_streak_best_anon"


def home(request):
    articles = Article.objects.select_related("author").prefetch_related("tags")[:4]
    return TemplateResponse(request, "core/home.html", {"featured_articles": articles})


def donations(request):
    return render(request, "core/donations.html", {"site_config": SiteConfig.load()})


def contact(request):
    config = SiteConfig.load()
    contact_links = ContactLink.objects.all()

    if not config.contact_email:
        return render(request, "core/contact.html", {"form": None, "contact_links": contact_links})

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            if not form.is_spam():
                EmailMessage(
                    subject=f"[Contacto La Sala de Bygui] {form.cleaned_data['name']}",
                    body=(
                        f"De: {form.cleaned_data['name']} <{form.cleaned_data['email']}>\n\n"
                        f"{form.cleaned_data['message']}"
                    ),
                    to=[config.contact_email],
                    reply_to=[form.cleaned_data["email"]],
                ).send()
            messages.success(request, "¡Mensaje enviado! Te responderemos lo antes posible.")
            return redirect("core:contact")
    else:
        form = ContactForm()

    return render(request, "core/contact.html", {"form": form, "contact_links": contact_links})


@cache_control(private=True, no_cache=True)
def theme_css(request):
    theme = get_effective_theme(request.user, request.session)
    return TemplateResponse(
        request, "core/theme.css", {"theme": theme}, content_type="text/css"
    )


@require_POST
def set_theme(request, slug):
    theme = get_object_or_404(Theme, slug=slug)
    if request.user.is_authenticated:
        request.user.theme = theme
        request.user.save(update_fields=["theme"])
    else:
        request.session[SESSION_THEME_KEY] = theme.slug
    return JsonResponse({"ok": True, "slug": theme.slug})


@require_POST
def reset_theme(request):
    if request.user.is_authenticated:
        request.user.theme = None
        request.user.save(update_fields=["theme"])
    request.session.pop(SESSION_THEME_KEY, None)
    return JsonResponse({"ok": True, "slug": None})


# --- Juegos ------------------------------------------------------------
# Frases célebres vivía antes dentro de Top Secret (código de acceso); se
# saca aquí para que "Juegos" agrupe Ruleta + Frases célebres sin pedir
# ningún código, evitando la redundancia de tener dos sitios distintos para
# "cosas para jugar/probar".

def games_hub(request):
    return render(request, "core/games.html")


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

    return render(request, "core/quote_game.html", {
        "quote": next_quote, "options": options, "streak": streak, "best": best,
        "game_over": game_over, "is_new_record": is_new_record,
        "final_streak": final_streak, "wrong_answer_title": wrong_answer_title,
    })
