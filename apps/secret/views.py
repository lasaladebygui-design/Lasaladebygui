import calendar as calendar_module
import random
from datetime import date, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Max
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.core.push import send_push_to_users
from apps.movies.models import Movie, ReleaseEvent
from apps.movies.services import MovieAPIError, tmdb_search

from .forms import CodeForm, FullListFilterForm, NumberSelectForm, RatingSearchForm, SecretPhotoForm, TierLevelForm
from .models import Genre, SecretMovie, SecretPhoto, TierLevel, TierListEntry, TopSecretConfig

SESSION_KEY = "top_secret_unlocked"

MONTH_NAMES_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def secret_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.session.get(SESSION_KEY):
            messages.info(request, "Introduce el código para entrar en el maletín.")
            return redirect("secret:gate")
        return view_func(request, *args, **kwargs)
    return wrapped


def gate(request):
    if request.session.get(SESSION_KEY):
        return redirect("secret:home")

    if request.method == "POST":
        form = CodeForm(request.POST)
        if form.is_valid():
            config = TopSecretConfig.load()
            if config.check_code(form.cleaned_data["code"]):
                request.session[SESSION_KEY] = True
                return redirect("secret:home")
            form.add_error("code", "Código incorrecto.")
    else:
        form = CodeForm()

    return render(request, "secret/gate.html", {"form": form})


def lock(request):
    request.session.pop(SESSION_KEY, None)
    messages.info(request, "Maletín cerrado.")
    return redirect("secret:gate")


@secret_required
def home(request):
    return render(request, "secret/home.html")


@secret_required
def by_number(request):
    form = NumberSelectForm(request.GET or None)
    result = None
    if request.GET and form.is_valid():
        result = get_object_or_404(SecretMovie, number=form.cleaned_data["number"])
    return render(request, "secret/by_number.html", {"form": form, "result": result})


@secret_required
def by_rating(request):
    form = RatingSearchForm(request.GET or None)
    result = None
    searched = False
    genre_slug = request.GET.get("genre", "").strip()

    if request.GET and form.is_valid():
        searched = True
        min_r, max_r = int(form.cleaned_data["min_rating"]), int(form.cleaned_data["max_rating"])
        matches = SecretMovie.objects.filter(personal_rating__gte=min_r, personal_rating__lte=max_r)
        if genre_slug:
            matches = matches.filter(genres__slug=genre_slug)
        matches = list(matches)
        if matches:
            result = random.choice(matches)

    return render(request, "secret/by_rating.html", {
        "form": form, "result": result, "searched": searched,
        "genres": Genre.objects.all(), "selected_genre": genre_slug,
    })


@secret_required
def full_list(request):
    form = FullListFilterForm(request.GET or None)
    movies = SecretMovie.objects.prefetch_related("genres").all()
    if form.is_valid():
        genre = form.cleaned_data.get("genre")
        rating = form.cleaned_data.get("rating")
        if genre:
            movies = movies.filter(genres=genre)
        if rating:
            movies = movies.filter(personal_rating=rating)
    return render(request, "secret/list.html", {"movies": movies, "form": form})


@secret_required
def other(request):
    return render(request, "secret/other.html")


@secret_required
def tier_list(request):
    levels = list(TierLevel.objects.all())
    buckets = {None: []}
    buckets.update({level.pk: [] for level in levels})
    for entry in TierListEntry.objects.select_related("movie"):
        buckets[entry.tier_id].append(entry)

    level_rows = [(level, buckets[level.pk]) for level in levels]
    return render(request, "secret/tier_list.html", {
        "level_rows": level_rows, "unsorted_entries": buckets[None],
    })


@secret_required
def tier_list_search(request):
    query = request.GET.get("query", "").strip()
    results = []
    error = None
    if query:
        try:
            results = tmdb_search(query)[:8]
        except MovieAPIError as exc:
            error = str(exc)
    return render(request, "secret/_tier_search_results.html", {
        "results": results, "error": error, "query": query,
    })


@secret_required
def tier_list_add(request, tmdb_id):
    if request.method == "POST":
        try:
            movie = Movie.get_or_create_from_tmdb(tmdb_id)
        except MovieAPIError as exc:
            messages.error(request, str(exc))
        else:
            TierListEntry.objects.get_or_create(
                movie=movie, defaults={"title": movie.title, "tier": None},
            )
    return redirect("secret:tier-list")


@secret_required
def tier_list_move(request, pk):
    if request.method != "POST":
        raise Http404
    entry = get_object_or_404(TierListEntry, pk=pk)
    raw_tier = request.POST.get("tier", "")
    level = None
    if raw_tier:
        try:
            level = TierLevel.objects.get(pk=raw_tier)
        except (TierLevel.DoesNotExist, ValueError):
            return JsonResponse({"ok": False, "error": "nivel inválido"}, status=400)

    max_order = TierListEntry.objects.filter(tier=level).aggregate(Max("order"))["order__max"] or 0
    entry.tier = level
    entry.order = max_order + 1
    entry.save(update_fields=["tier", "order"])
    return JsonResponse({"ok": True})


@secret_required
def tier_level_create(request):
    if request.method == "POST":
        form = TierLevelForm(request.POST)
        if form.is_valid():
            max_order = TierLevel.objects.aggregate(Max("order"))["order__max"] or 0
            level = form.save(commit=False)
            level.order = max_order + 1
            level.save()
        else:
            messages.error(request, "No se pudo añadir el nivel.")
    return redirect("secret:tier-list")


@secret_required
def tier_level_update(request, pk):
    level = get_object_or_404(TierLevel, pk=pk)
    if request.method == "POST":
        form = TierLevelForm(request.POST, instance=level)
        if form.is_valid():
            form.save()
        else:
            messages.error(request, "No se pudo guardar el nivel.")
    return redirect("secret:tier-list")


@secret_required
def tier_level_delete(request, pk):
    level = get_object_or_404(TierLevel, pk=pk)
    if request.method == "POST":
        level.delete()
        messages.success(request, "Nivel borrado. Sus películas han vuelto a 'Sin clasificar'.")
    return redirect("secret:tier-list")


@secret_required
def tier_list_reset(request):
    if request.method == "POST":
        TierListEntry.objects.all().delete()
        messages.success(request, "Tier list vaciada. Puedes empezar de nuevo.")
    return redirect("secret:tier-list")


@secret_required
def photo_board(request):
    if request.method == "POST":
        form = SecretPhotoForm(request.POST, request.FILES)
        if form.is_valid():
            photo = form.save(commit=False)
            if request.user.is_authenticated and not form.cleaned_data["post_as_anonymous"]:
                photo.uploaded_by = request.user
            photo.save()
            messages.success(request, "Foto subida al tablón.")
            return redirect("secret:photo-board")
    else:
        form = SecretPhotoForm()

    photos = SecretPhoto.objects.select_related("uploaded_by")
    return render(request, "secret/photo_board.html", {"form": form, "photos": photos})


# --- Calendario de estrenos --------------------------------------------------
# Vive dentro de Top Secret (privado, tras el código) en vez de en el
# catálogo público: aquí es donde se decide qué toca qué día, y solo quien
# ha entrado con el código puede verlo o tocarlo. Se puede añadir una
# película o serie a una fecha buscándola (mismo patrón que la tier list) y,
# al añadirla, se manda una notificación push a los usuarios suscritos —
# no hay sincronización real con Google Calendar (necesitaría OAuth y
# credenciales por usuario), así que cada evento tiene además un botón
# para descargar su .ics e importarlo a mano en cualquier calendario.

@secret_required
def calendar_view(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        first_of_month = date(year, month, 1)
    except (TypeError, ValueError):
        raise Http404

    raw_weeks = calendar_module.Calendar(firstweekday=0).monthdatescalendar(year, month)
    events = ReleaseEvent.objects.filter(date__year=year, date__month=month).select_related("movie")
    events_by_date = {}
    for event in events:
        events_by_date.setdefault(event.date, []).append(event)

    weeks = [
        [
            {
                "date": day,
                "in_month": day.month == month,
                "is_today": day == today,
                "events": events_by_date.get(day, []),
            }
            for day in week
        ]
        for week in raw_weeks
    ]

    prev_month_date = first_of_month - timedelta(days=1)
    next_month_date = (first_of_month + timedelta(days=32)).replace(day=1)

    return render(request, "secret/calendar.html", {
        "weeks": weeks,
        "year": year,
        "month": month,
        "month_label": f"{MONTH_NAMES_ES[month]} {year}",
        "prev_year": prev_month_date.year,
        "prev_month": prev_month_date.month,
        "next_year": next_month_date.year,
        "next_month": next_month_date.month,
        "today_iso": today.isoformat(),
    })


@secret_required
def calendar_search(request):
    query = request.GET.get("query", "").strip()
    event_date = request.GET.get("date", "")
    results = []
    error = None
    if query:
        try:
            results = tmdb_search(query, media_type="movie")[:6] + tmdb_search(query, media_type="tv")[:6]
        except MovieAPIError as exc:
            error = str(exc)
    return render(request, "secret/_calendar_search_results.html", {
        "results": results, "error": error, "query": query, "date": event_date,
    })


@secret_required
def calendar_add(request, media_type, tmdb_id):
    if request.method != "POST" or media_type not in ("movie", "tv"):
        raise Http404

    try:
        year, month, day = (int(part) for part in request.POST.get("date", "").split("-"))
        event_date = date(year, month, day)
    except (TypeError, ValueError):
        messages.error(request, "Fecha inválida.")
        return redirect("secret:calendar")

    try:
        movie = Movie.get_or_create_from_tmdb(tmdb_id, media_type=media_type)
    except MovieAPIError as exc:
        messages.error(request, str(exc))
        return redirect("secret:calendar")

    ReleaseEvent.objects.create(movie=movie, date=event_date)
    messages.success(request, f"«{movie.title}» añadida al {event_date:%d/%m/%Y}.")

    User = get_user_model()
    subscribers = User.objects.filter(push_subscriptions__isnull=False).distinct()
    if request.user.is_authenticated:
        subscribers = subscribers.exclude(pk=request.user.pk)
    send_push_to_users(
        subscribers,
        title="Nuevo estreno en el calendario",
        body=f"{movie.title} — {event_date:%d/%m/%Y}",
        url=f"{reverse('secret:calendar')}?year={event_date.year}&month={event_date.month}",
    )

    return redirect(f"{reverse('secret:calendar')}?year={event_date.year}&month={event_date.month}")


@secret_required
def calendar_remove(request, pk):
    event = get_object_or_404(ReleaseEvent, pk=pk)
    if request.method != "POST":
        raise Http404
    year, month = event.date.year, event.date.month
    event.delete()
    return redirect(f"{reverse('secret:calendar')}?year={year}&month={month}")


def _ics_escape(value):
    """Escapa una cadena para incrustarla en un campo de texto de un
    archivo .ics (RFC 5545): la barra invertida y los separadores propios
    del formato (coma, punto y coma, salto de línea) van escapados con \\."""
    return (
        value.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


@secret_required
def calendar_ics(request, pk):
    event = get_object_or_404(ReleaseEvent, pk=pk)
    summary = _ics_escape(event.movie.title)
    description = _ics_escape(event.note) if event.note else ""
    stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//La Sala de Bygui//Calendario//ES",
        "BEGIN:VEVENT",
        f"UID:release-{event.pk}@lasaladebygui",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{event.date:%Y%m%d}",
        f"SUMMARY:{summary}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{description}")
    lines += ["END:VEVENT", "END:VCALENDAR"]

    response = HttpResponse("\r\n".join(lines), content_type="text/calendar; charset=utf-8")
    filename = slugify(event.movie.title) or "evento"
    response["Content-Disposition"] = f'attachment; filename="{filename}.ics"'
    return response
