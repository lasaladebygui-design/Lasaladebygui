import calendar as calendar_module
import random
from datetime import date, timedelta
from functools import wraps

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Max
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core.google_calendar import create_event as google_create_event
from apps.core.google_calendar import delete_event as google_delete_event
from apps.core.google_calendar import google_calendar_enabled
from apps.movies.models import Movie
from apps.movies.services import MovieAPIError, tmdb_search
from apps.social.models import are_friends, friends_of

from .forms import CodeForm, FullListFilterForm, NumberSelectForm, RatingSearchForm, SecretPhotoForm, TierLevelForm
from .models import (
    CalendarDayNote,
    Genre,
    PhotoBoardMember,
    ReleaseEvent,
    SecretMovie,
    SecretPhoto,
    TierLevel,
    TierListEntry,
    TopSecretConfig,
)

SESSION_KEY = "top_secret_unlocked"

MONTH_NAMES_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# El código de acceso es un PIN corto (4 dígitos por defecto) — sin esto,
# probarlos todos a fuerza bruta es trivial. Tras varios fallos seguidos
# desde la misma IP, se bloquean nuevos intentos un rato (se resetea en
# cuanto acierta).
GATE_MAX_ATTEMPTS = 8
GATE_LOCKOUT_SECONDS = 300

FULL_LIST_PAGE_SIZE = 24


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def secret_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.session.get(SESSION_KEY):
            messages.info(request, "Introduce el código para entrar en el maletín.")
            return redirect("secret:gate")
        return view_func(request, *args, **kwargs)
    return wrapped


def _gate_attempts_cache_key(request):
    return f"secret_gate_attempts:{request.META.get('REMOTE_ADDR', 'unknown')}"


def gate(request):
    if request.session.get(SESSION_KEY):
        return redirect("secret:home")

    if request.method == "POST":
        cache_key = _gate_attempts_cache_key(request)
        form = CodeForm(request.POST)
        if cache.get(cache_key, 0) >= GATE_MAX_ATTEMPTS:
            form.add_error(None, "Demasiados intentos. Espera unos minutos antes de volver a probar.")
        elif form.is_valid():
            config = TopSecretConfig.load()
            if config.check_code(form.cleaned_data["code"]):
                cache.delete(cache_key)
                request.session[SESSION_KEY] = True
                return redirect("secret:home")
            cache.set(cache_key, cache.get(cache_key, 0) + 1, GATE_LOCKOUT_SECONDS)
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
    genres = Genre.objects.all()
    selected_genre_name = next((g.name for g in genres if g.slug == genre_slug), "")

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
        "genres": genres, "selected_genre": genre_slug, "selected_genre_name": selected_genre_name,
    })


@secret_required
def full_list(request):
    form = FullListFilterForm(request.GET or None)
    movies = SecretMovie.objects.prefetch_related("genres").select_related("movie").all()
    if form.is_valid():
        genres = form.cleaned_data.get("genres")
        if genres:
            for genre in genres:
                movies = movies.filter(genres=genre)

    sort = request.GET.get("sort")
    if sort == "asc":
        movies = movies.order_by("personal_rating", "-tie_break", "-number")
    else:
        sort = "desc"
        movies = movies.order_by("-personal_rating", "tie_break", "number")

    # Parámetros a conservar al pedir la siguiente página (filtro de listas,
    # orden) — sin "page", que lo pone el propio enlace de paginación.
    querystring = request.GET.copy()
    querystring.pop("page", None)

    # Solo el filtro de listas, sin "sort" ni "page" — para que los enlaces
    # de ordenar puedan fijar su propio sort sin perder el filtro activo.
    genres_querystring = request.GET.copy()
    genres_querystring.pop("page", None)
    genres_querystring.pop("sort", None)

    page_obj = Paginator(movies, FULL_LIST_PAGE_SIZE).get_page(request.GET.get("page"))
    context = {
        "movies": page_obj, "form": form, "rating_config": TopSecretConfig.load(),
        "sort": sort, "querystring": querystring.urlencode(),
        "genres_querystring": genres_querystring.urlencode(),
    }
    if _is_htmx(request):
        return render(request, "secret/_list_items.html", context)
    return render(request, "secret/list.html", context)


@secret_required
def movie_detail(request, pk):
    movie = get_object_or_404(
        SecretMovie.objects.prefetch_related("genres").select_related("movie"), pk=pk,
    )
    return render(request, "secret/movie_detail.html", {
        "movie": movie, "rating_config": TopSecretConfig.load(),
    })


@secret_required
def other(request):
    return render(request, "secret/other.html")


@secret_required
@login_required
def tier_list(request):
    levels = list(TierLevel.objects.filter(user=request.user))
    buckets = {None: []}
    buckets.update({level.pk: [] for level in levels})
    for entry in TierListEntry.objects.filter(user=request.user).select_related("movie"):
        buckets[entry.tier_id].append(entry)

    level_rows = [(level, buckets[level.pk]) for level in levels]
    return render(request, "secret/tier_list.html", {
        "level_rows": level_rows, "unsorted_entries": buckets[None],
    })


@secret_required
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
    return render(request, "secret/_tier_search_results.html", {
        "results": results, "error": error, "query": query,
    })


@secret_required
@login_required
def tier_list_add(request, tmdb_id):
    if request.method == "POST":
        try:
            movie = Movie.get_or_create_from_tmdb(tmdb_id)
        except MovieAPIError as exc:
            messages.error(request, str(exc))
        else:
            TierListEntry.objects.get_or_create(
                user=request.user, movie=movie, defaults={"title": movie.title, "tier": None},
            )
    return redirect("secret:tier-list")


@secret_required
@login_required
def tier_list_move(request, pk):
    if request.method != "POST":
        raise Http404
    entry = get_object_or_404(TierListEntry, pk=pk, user=request.user)
    raw_tier = request.POST.get("tier", "")
    level = None
    if raw_tier:
        try:
            level = TierLevel.objects.get(pk=raw_tier, user=request.user)
        except (TierLevel.DoesNotExist, ValueError):
            return JsonResponse({"ok": False, "error": "nivel inválido"}, status=400)

    max_order = TierListEntry.objects.filter(user=request.user, tier=level).aggregate(Max("order"))["order__max"] or 0
    entry.tier = level
    entry.order = max_order + 1
    entry.save(update_fields=["tier", "order"])
    return JsonResponse({"ok": True})


@secret_required
@login_required
def tier_level_create(request):
    if request.method == "POST":
        form = TierLevelForm(request.POST)
        if form.is_valid():
            max_order = TierLevel.objects.filter(user=request.user).aggregate(Max("order"))["order__max"] or 0
            level = form.save(commit=False)
            level.user = request.user
            level.order = max_order + 1
            level.save()
        else:
            messages.error(request, "No se pudo añadir el nivel.")
    return redirect("secret:tier-list")


@secret_required
@login_required
def tier_level_update(request, pk):
    level = get_object_or_404(TierLevel, pk=pk, user=request.user)
    if request.method == "POST":
        form = TierLevelForm(request.POST, instance=level)
        if form.is_valid():
            form.save()
        else:
            messages.error(request, "No se pudo guardar el nivel.")
    return redirect("secret:tier-list")


@secret_required
@login_required
def tier_level_delete(request, pk):
    level = get_object_or_404(TierLevel, pk=pk, user=request.user)
    if request.method == "POST":
        level.delete()
        messages.success(request, "Nivel borrado. Sus películas han vuelto a 'Sin clasificar'.")
    return redirect("secret:tier-list")


@secret_required
@login_required
def tier_list_reset(request):
    if request.method == "POST":
        TierListEntry.objects.filter(user=request.user).delete()
        messages.success(request, "Tier list vaciada. Puedes empezar de nuevo.")
    return redirect("secret:tier-list")


# --- Tablón de fotos ----------------------------------------------------
# Cada usuario tiene el suyo, privado por defecto; puede invitar a amigos
# concretos (apps.social) para que lo vean y suban fotos también, y
# expulsarlos cuando quiera. `photo_board_view` sirve tanto para tu propio
# tablón (con gestión de invitados) como para uno compartido contigo (sin
# ella, solo subir/ver).

def _can_access_photo_board(viewer, owner):
    return viewer.pk == owner.pk or PhotoBoardMember.objects.filter(owner=owner, member=viewer).exists()


@secret_required
@login_required
def photo_serve(request, pk):
    """La imagen se sirve SIEMPRE por aquí, nunca por su URL de storage
    directa: en producción esa URL va firmada y caduca al minuto (ver
    STORAGES["secret_photos"] en settings), así que aunque alguien la copie
    del código fuente de la página deja de funcionar casi al momento. En
    local (sin Supabase configurado) no hay firma posible, así que el
    archivo se manda directamente desde aquí en vez de redirigir a /media/."""
    photo = get_object_or_404(SecretPhoto, pk=pk)
    if not _can_access_photo_board(request.user, photo.board_owner):
        raise Http404
    if settings.USE_SUPABASE_STORAGE:
        return redirect(photo.image.url)
    return FileResponse(photo.image.open("rb"))


@secret_required
@login_required
def photo_board(request, username=None):
    owner = request.user
    if username:
        owner = get_object_or_404(User, username=username)
        if not _can_access_photo_board(request.user, owner):
            raise Http404

    is_owner = owner.pk == request.user.pk

    if request.method == "POST":
        if not _can_access_photo_board(request.user, owner):
            raise Http404
        form = SecretPhotoForm(request.POST, request.FILES)
        if form.is_valid():
            photo = form.save(commit=False)
            photo.board_owner = owner
            photo.uploaded_by = request.user
            photo.save()
            messages.success(request, "Foto subida al tablón.")
            if is_owner:
                return redirect("secret:photo-board")
            return redirect("secret:photo-board-shared", owner.username)
    else:
        form = SecretPhotoForm()

    photos = SecretPhoto.objects.filter(board_owner=owner).select_related("uploaded_by")
    context = {"form": form, "photos": photos, "board_owner": owner, "is_owner": is_owner}

    if is_owner:
        members = PhotoBoardMember.objects.filter(owner=request.user).select_related("member")
        member_ids = {m.member_id for m in members}
        invitable_friends = [f for f in friends_of(request.user) if f.pk not in member_ids]
        shared_with_me = PhotoBoardMember.objects.filter(member=request.user).select_related("owner")
        context.update({
            "members": members,
            "invitable_friends": invitable_friends,
            "shared_with_me": shared_with_me,
        })

    return render(request, "secret/photo_board.html", context)


@secret_required
@login_required
def photo_board_invite(request, username):
    friend = get_object_or_404(User, username=username)
    if request.method == "POST" and are_friends(request.user, friend):
        PhotoBoardMember.objects.get_or_create(owner=request.user, member=friend)
        messages.success(request, f"{friend} ya puede ver y subir fotos a tu tablón.")
    return redirect("secret:photo-board")


@secret_required
@login_required
def photo_board_kick(request, pk):
    member = get_object_or_404(PhotoBoardMember, pk=pk, owner=request.user)
    if request.method == "POST":
        member.delete()
        messages.success(request, f"{member.member} ya no tiene acceso a tu tablón.")
    return redirect("secret:photo-board")


# --- Calendario de estrenos --------------------------------------------------
# Vive dentro de Top Secret (hay que entrar con el código para llegar hasta
# aquí) pero es personal de cada usuario: nadie más, ni siquiera otro con el
# mismo código de acceso al maletín, ve tus películas/series ni tus
# comentarios de un día — por eso hace falta estar logueado, no solo tener
# el código. Se puede añadir una película o serie a una fecha buscándola
# (mismo patrón que la tier list); si tienes conectado de verdad tu Google
# Calendar, se crea solo ahí también (`ReleaseEvent.google_event_id`); si
# no, cada evento tiene un botón para descargar su .ics a mano.

@secret_required
@login_required
def calendar_view(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        first_of_month = date(year, month, 1)
    except (TypeError, ValueError):
        raise Http404

    raw_weeks = calendar_module.Calendar(firstweekday=0).monthdatescalendar(year, month)
    events = ReleaseEvent.objects.filter(
        user=request.user, date__year=year, date__month=month,
    ).select_related("movie")
    events_by_date = {}
    for event in events:
        events_by_date.setdefault(event.date, []).append(event)

    notes_by_date = {
        note.date: note.note
        for note in CalendarDayNote.objects.filter(user=request.user, date__year=year, date__month=month)
    }

    weeks = [
        [
            {
                "date": day,
                "in_month": day.month == month,
                "is_today": day == today,
                "events": events_by_date.get(day, []),
                "comment": notes_by_date.get(day, ""),
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
        "google_calendar_enabled": google_calendar_enabled(),
        "google_calendar_connected": hasattr(request.user, "google_calendar_connection"),
    })


@secret_required
@login_required
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
@login_required
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

    event = ReleaseEvent.objects.create(user=request.user, movie=movie, date=event_date)
    messages.success(request, f"«{movie.title}» añadida al {event_date:%d/%m/%Y}.")

    if google_calendar_enabled() and hasattr(request.user, "google_calendar_connection"):
        try:
            event.google_event_id = google_create_event(
                request.user.google_calendar_connection, movie.title, event_date, description=event.note,
            )
            event.save(update_fields=["google_event_id"])
        except requests.RequestException:
            pass

    return redirect(f"{reverse('secret:calendar')}?year={event_date.year}&month={event_date.month}")


@secret_required
@login_required
def calendar_remove(request, pk):
    event = get_object_or_404(ReleaseEvent, pk=pk, user=request.user)
    if request.method != "POST":
        raise Http404
    year, month = event.date.year, event.date.month

    if event.google_event_id and hasattr(request.user, "google_calendar_connection"):
        try:
            google_delete_event(request.user.google_calendar_connection, event.google_event_id)
        except requests.RequestException:
            pass

    event.delete()
    return redirect(f"{reverse('secret:calendar')}?year={year}&month={month}")


@secret_required
@login_required
def calendar_day_note(request):
    if request.method != "POST":
        raise Http404
    try:
        year, month, day = (int(part) for part in request.POST.get("date", "").split("-"))
        note_date = date(year, month, day)
    except (TypeError, ValueError):
        raise Http404

    note = request.POST.get("note", "").strip()
    if note:
        CalendarDayNote.objects.update_or_create(user=request.user, date=note_date, defaults={"note": note})
    else:
        CalendarDayNote.objects.filter(user=request.user, date=note_date).delete()

    return redirect(f"{reverse('secret:calendar')}?year={note_date.year}&month={note_date.month}")


@secret_required
@login_required
def calendar_move_event(request, pk):
    event = get_object_or_404(ReleaseEvent, pk=pk, user=request.user)
    if request.method != "POST":
        raise Http404
    try:
        year, month, day = (int(part) for part in request.POST.get("date", "").split("-"))
        new_date = date(year, month, day)
    except (TypeError, ValueError):
        messages.error(request, "Fecha inválida.")
        return redirect(f"{reverse('secret:calendar')}?year={event.date.year}&month={event.date.month}")

    old_year, old_month = event.date.year, event.date.month
    event.date = new_date

    if event.google_event_id and hasattr(request.user, "google_calendar_connection"):
        connection = request.user.google_calendar_connection
        try:
            google_delete_event(connection, event.google_event_id)
            event.google_event_id = google_create_event(connection, event.movie.title, new_date, description=event.note)
        except requests.RequestException:
            pass

    event.save(update_fields=["date", "google_event_id"])
    messages.success(request, f"«{event.movie.title}» movida al {new_date:%d/%m/%Y}.")
    return redirect(f"{reverse('secret:calendar')}?year={old_year}&month={old_month}")
