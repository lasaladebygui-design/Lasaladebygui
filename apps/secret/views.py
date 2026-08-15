import calendar as calendar_module
import random
import unicodedata
from datetime import date, timedelta
from functools import wraps

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Max, Value, When
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core.google_calendar import create_event as google_create_event
from apps.core.google_calendar import delete_event as google_delete_event
from apps.core.google_calendar import google_calendar_enabled
from apps.core.models import get_effective_theme
from apps.movies.models import Movie
from apps.movies.services import MovieAPIError, tmdb_search
from apps.social.models import are_friends, friends_of

from .forms import (
    CodeForm,
    FullListFilterForm,
    NumberSelectForm,
    RatingSearchForm,
    SecretPhotoEditForm,
    SecretPhotoForm,
    TierLevelForm,
)
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


def _is_admin(user):
    return user.is_authenticated and user.role == User.Role.ADMIN


def _visible_movies(user):
    """Base queryset de SecretMovie según quién mira: un Admin ve todo,
    cualquier otra persona (aunque tenga el código) no ve ninguna
    película marcada con una lista `admin_only`."""
    movies = SecretMovie.objects.prefetch_related("genres").select_related("movie")
    if _is_admin(user):
        return movies
    return movies.exclude(genres__admin_only=True)


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
    searched = False
    if request.GET and form.is_valid():
        searched = True
        number = form.cleaned_data["number"]
        # Ya no es un desplegable limitado a números existentes: cualquier
        # entero es válido para el formulario, así que puede no haber
        # ninguna película con ese número — se enseña como "no encontrada"
        # en vez de una página de error 404. Pero si el número SÍ existe y
        # solo se ha filtrado por ser de una lista oculta para este
        # usuario, se mantiene el 404 (igual que movie_detail): no se
        # distingue "no existe" de "no puedes verla".
        result = _visible_movies(request.user).filter(number=number).first()
        if result is None and SecretMovie.objects.filter(number=number).exists():
            raise Http404
    return render(request, "secret/by_number.html", {"form": form, "result": result, "searched": searched})


@secret_required
def by_rating(request):
    form = RatingSearchForm(request.GET or None)
    result = None
    searched = False
    genre_slug = request.GET.get("genre", "").strip()
    genres = Genre.objects.all() if _is_admin(request.user) else Genre.objects.filter(admin_only=False)
    selected_genre_name = next((g.name for g in genres if g.slug == genre_slug), "")

    if request.GET and form.is_valid():
        searched = True
        min_r, max_r = int(form.cleaned_data["min_rating"]), int(form.cleaned_data["max_rating"])
        matches = _visible_movies(request.user).filter(personal_rating__gte=min_r, personal_rating__lte=max_r)
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
    form = FullListFilterForm(request.GET or None, admin_user=_is_admin(request.user))
    movies = _visible_movies(request.user)
    if form.is_valid():
        genres = form.cleaned_data.get("genres")
        if genres:
            for genre in genres:
                movies = movies.filter(genres=genre)

    query = request.GET.get("q", "").strip()
    if query:
        movies = movies.filter(title__icontains=query)

    media_type = request.GET.get("type", "")
    if media_type in ("movie", "tv"):
        # Se sabe automáticamente en función de la película/serie del
        # catálogo enlazada como portada — no hay que etiquetar nada a
        # mano. Las que no tienen portada enlazada no salen en ninguno de
        # los dos filtros, solo en "Todas".
        movies = movies.filter(movie__media_type=media_type)

    sort = request.GET.get("sort")
    grouped_labels = None
    if sort == "asc":
        movies = movies.order_by("personal_rating", "-tie_break", "-number")
    elif sort in ("movies_first", "series_first"):
        # Dentro de cada grupo (películas / series), se ordena igual que el
        # modo por defecto (nota de mayor a menor). Las que no tienen
        # película enlazada del catálogo (así que no se sabe si son
        # película o serie) van al final, en su propio grupo.
        first_type, second_type = ("movie", "tv") if sort == "movies_first" else ("tv", "movie")
        grouped_labels = {
            0: "🎬 Películas" if first_type == "movie" else "📺 Series",
            1: "🎬 Películas" if second_type == "movie" else "📺 Series",
            2: "❔ Sin clasificar",
        }
        movies = movies.annotate(
            type_order=Case(
                When(movie__media_type=first_type, then=Value(0)),
                When(movie__media_type=second_type, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).order_by("type_order", "-personal_rating", "tie_break", "number")
    else:
        sort = "desc"
        movies = movies.order_by("-personal_rating", "tie_break", "number")

    # Parámetros a conservar al pedir la siguiente página (filtro de listas,
    # orden) — sin "page", que lo pone el propio enlace de paginación.
    querystring = request.GET.copy()
    querystring.pop("page", None)
    querystring.pop("prev_type", None)

    page_obj = Paginator(movies, FULL_LIST_PAGE_SIZE).get_page(request.GET.get("page"))

    if grouped_labels:
        # El separador ("🎬 Películas" / "📺 Series") solo debe salir una vez,
        # justo donde cambia el grupo — como el scroll infinito pide cada
        # tanda en una petición HTTP aparte (sin memoria de la anterior),
        # "prev_type" viaja de una tanda a la siguiente para saber si la
        # primera fila de esta tanda sigue el mismo grupo que la última de
        # la tanda anterior, o si toca abrir uno nuevo.
        prev_type_param = request.GET.get("prev_type")
        prev_type = int(prev_type_param) if prev_type_param and prev_type_param.isdigit() else None
        for movie_item in page_obj.object_list:
            if movie_item.type_order != prev_type:
                movie_item.group_label = grouped_labels[movie_item.type_order]
            prev_type = movie_item.type_order
        if prev_type is not None:
            querystring["prev_type"] = prev_type

    context = {
        "movies": page_obj, "form": form, "rating_config": TopSecretConfig.load(),
        "sort": sort, "querystring": querystring.urlencode(), "query": query,
        "media_type": media_type,
    }
    if _is_htmx(request):
        return render(request, "secret/_list_items.html", context)
    return render(request, "secret/list.html", context)


@secret_required
def movie_detail(request, pk):
    movie = get_object_or_404(_visible_movies(request.user), pk=pk)
    return render(request, "secret/movie_detail.html", {
        "movie": movie, "rating_config": TopSecretConfig.load(),
    })


@secret_required
def other(request):
    return render(request, "secret/other.html")


def _tier_list_buckets(user):
    levels = list(TierLevel.objects.filter(user=user))
    buckets = {None: []}
    buckets.update({level.pk: [] for level in levels})
    for entry in TierListEntry.objects.filter(user=user).select_related("movie"):
        buckets[entry.tier_id].append(entry)
    level_rows = [(level, buckets[level.pk]) for level in levels]
    return level_rows, buckets[None]


@secret_required
@login_required
def tier_list(request):
    level_rows, unsorted_entries = _tier_list_buckets(request.user)
    return render(request, "secret/tier_list.html", {
        "level_rows": level_rows, "unsorted_entries": unsorted_entries,
    })


def _contrast_text_color(hex_color):
    """Negro o blanco según el brillo del color de fondo, para que la
    etiqueta del nivel se lea bien sea cual sea el color que haya
    elegido cada usuario para ese nivel."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#111111" if luminance > 0.6 else "#f5f5f5"


def _wrap_text(draw, text, font, max_width):
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _render_tier_list_image(theme, level_rows, unsorted_entries):
    """PNG de solo lectura de la tier list — igual idea que la imagen del
    calendario: para enseñarla, no para editarla."""
    from PIL import Image, ImageDraw, ImageFont

    width, pad, label_w, row_gap, line_h = 900, 24, 110, 10, 20
    header_h = 76

    font_title = ImageFont.load_default(size=26)
    font_subtitle = ImageFont.load_default(size=13)
    font_level = ImageFont.load_default(size=16)
    font_item = ImageFont.load_default(size=14)

    rows = list(level_rows)
    if unsorted_entries:
        rows.append((None, unsorted_entries))

    dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    text_max_width = width - pad * 2 - label_w - 24

    row_lines = []
    for _level, entries in rows:
        if entries:
            joined = "  ·  ".join(_ascii_safe(entry.title) for entry in entries)
            row_lines.append(_wrap_text(dummy_draw, joined, font_item, text_max_width))
        else:
            row_lines.append(["(vacío)"])
    row_heights = [len(lines) * line_h + 16 for lines in row_lines]

    height = pad * 2 + header_h + sum(row_heights) + row_gap * max(0, len(rows) - 1)

    img = Image.new("RGB", (width, height), theme.color_bg)
    draw = ImageDraw.Draw(img)
    draw.text((pad, pad), "Mi tier list", font=font_title, fill=theme.color_accent)
    draw.text((pad, pad + 34), _ascii_safe("La Sala de Bygui - tier list personal"), font=font_subtitle, fill=theme.color_text_muted)

    y = pad + header_h
    for (level, _entries), lines, row_h in zip(rows, row_lines, row_heights):
        color = level.color if level else theme.color_border
        label = _ascii_safe(level.name) if level else "Sin clasificar"
        draw.rectangle([pad, y, pad + label_w, y + row_h], fill=color)
        draw.rectangle([pad + label_w, y, width - pad, y + row_h], outline=theme.color_border)
        draw.text((pad + 10, y + row_h / 2 - 8), label, font=font_level, fill=_contrast_text_color(color) if level else theme.color_text_muted)
        ty = y + 8
        for line in lines:
            draw.text((pad + label_w + 12, ty), line, font=font_item, fill=theme.color_text)
            ty += line_h
        y += row_h + row_gap

    return img


@secret_required
@login_required
def tier_list_share_image(request):
    level_rows, unsorted_entries = _tier_list_buckets(request.user)
    theme = get_effective_theme(request.user, request.session)
    image = _render_tier_list_image(theme, level_rows, unsorted_entries)

    response = HttpResponse(content_type="image/png")
    image.save(response, "PNG")
    response["Content-Disposition"] = 'inline; filename="tier_list.png"'
    return response


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


def _photo_board_redirect(board_owner, viewer):
    if board_owner.pk == viewer.pk:
        return redirect("secret:photo-board")
    return redirect("secret:photo-board-shared", board_owner.username)


@secret_required
@login_required
def photo_board_edit(request, pk):
    # Solo quien subió la foto puede editar su descripción — no el dueño
    # del tablón por sí solo, si la foto es de otra persona invitada.
    photo = get_object_or_404(SecretPhoto, pk=pk, uploaded_by=request.user)
    if request.method == "POST":
        form = SecretPhotoEditForm(request.POST, instance=photo)
        if form.is_valid():
            form.save()
            messages.success(request, "Descripción actualizada.")
    return _photo_board_redirect(photo.board_owner, request.user)


@secret_required
@login_required
def photo_board_delete(request, pk):
    photo = get_object_or_404(SecretPhoto, pk=pk, uploaded_by=request.user)
    board_owner = photo.board_owner
    if request.method == "POST":
        photo.delete()
        messages.success(request, "Foto eliminada del tablón.")
    return _photo_board_redirect(board_owner, request.user)


# --- Calendario de estrenos --------------------------------------------------
# Vive dentro de Top Secret (hay que entrar con el código para llegar hasta
# aquí) pero es personal de cada usuario: nadie más, ni siquiera otro con el
# mismo código de acceso al maletín, ve tus películas/series ni tus
# comentarios de un día — por eso hace falta estar logueado, no solo tener
# el código. Se puede añadir una película o serie a una fecha buscándola
# (mismo patrón que la tier list); si tienes conectado de verdad tu Google
# Calendar, se crea solo ahí también (`ReleaseEvent.google_event_id`); si
# no, cada evento tiene un botón para descargar su .ics a mano.

def _parse_calendar_month(request, today):
    """(year, month, primer_dia) a partir de ?year=&month=, o el mes
    actual si no vienen — usado tanto por la vista del calendario como
    por la imagen para compartir, para no repetir el parseo/validación."""
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        first_of_month = date(year, month, 1)
    except (TypeError, ValueError):
        raise Http404
    return year, month, first_of_month


def _events_by_date(user, year, month):
    events = ReleaseEvent.objects.filter(
        user=user, date__year=year, date__month=month,
    ).select_related("movie")
    events_by_date = {}
    for event in events:
        events_by_date.setdefault(event.date, []).append(event)
    return events_by_date


@secret_required
@login_required
def calendar_view(request):
    today = timezone.localdate()
    year, month, first_of_month = _parse_calendar_month(request, today)

    raw_weeks = calendar_module.Calendar(firstweekday=0).monthdatescalendar(year, month)
    events_by_date = _events_by_date(request.user, year, month)

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


def _ascii_safe(text, fallback="(titulo no compatible)"):
    """La fuente por defecto de Pillow solo tiene glifos latinos/ASCII —
    se usa solo para dibujar esta imagen (el resto del sitio sigue
    mostrando el texto tal cual, con tildes, japonés, etc.). Primero
    quita acentos/ñ; lo que siga sin ser ASCII (japonés, coreano,
    árabe...) directamente se descarta en vez de salir como un cuadro
    ilegible, y si no queda nada legible se usa un texto de repuesto."""
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    stripped = stripped.replace("—", "-").replace("–", "-").replace("…", "...")
    renderable = "".join(ch for ch in stripped if 32 <= ord(ch) < 127)
    renderable = " ".join(renderable.split())
    return renderable or fallback


def _render_calendar_image(theme, month_label, weeks):
    """PNG de solo lectura del mes (número de cada día + títulos de ese
    día) para poder mandarlo a alguien — no lleva comentarios personales
    ni nada editable, y usa los mismos colores del tema activo del
    usuario para que no desentone con el resto del sitio."""
    from PIL import Image, ImageDraw, ImageFont

    cols, pad = 7, 24
    cell_w, cell_h = 150, 108
    header_h = 76
    weekday_h = 32
    width = pad * 2 + cols * cell_w
    height = pad * 2 + header_h + weekday_h + len(weeks) * cell_h

    font_title = ImageFont.load_default(size=30)
    font_subtitle = ImageFont.load_default(size=13)
    font_weekday = ImageFont.load_default(size=13)
    font_day = ImageFont.load_default(size=15)
    font_event = ImageFont.load_default(size=12)

    img = Image.new("RGB", (width, height), theme.color_bg)
    draw = ImageDraw.Draw(img)

    draw.text((pad, pad), _ascii_safe(month_label.capitalize()), font=font_title, fill=theme.color_accent)
    draw.text((pad, pad + 38), _ascii_safe("La Sala de Bygui - calendario personal"), font=font_subtitle, fill=theme.color_text_muted)

    top = pad + header_h
    for i, name in enumerate(["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]):
        x = pad + i * cell_w
        draw.rectangle([x, top, x + cell_w, top + weekday_h], fill=theme.color_surface, outline=theme.color_border)
        draw.text((x + 10, top + 8), name, font=font_weekday, fill=theme.color_text_muted)

    grid_top = top + weekday_h
    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            x, y = pad + c * cell_w, grid_top + r * cell_h
            draw.rectangle([x, y, x + cell_w, y + cell_h], fill=theme.color_bg, outline=theme.color_border)
            draw.text(
                (x + 10, y + 8), str(day["date"].day), font=font_day,
                fill=theme.color_text if day["in_month"] else theme.color_text_muted,
            )
            titles = [_ascii_safe(event.movie.title) for event in day["events"]]
            ey = y + 32
            for title in titles[:3]:
                snippet = title if len(title) <= 20 else title[:19] + "..."
                draw.text((x + 10, ey), snippet, font=font_event, fill=theme.color_accent_secondary)
                ey += 16
            if len(titles) > 3:
                draw.text((x + 10, ey), f"+{len(titles) - 3} mas", font=font_event, fill=theme.color_text_muted)

    return img


@secret_required
@login_required
def calendar_share_image(request):
    today = timezone.localdate()
    year, month, _ = _parse_calendar_month(request, today)

    raw_weeks = calendar_module.Calendar(firstweekday=0).monthdatescalendar(year, month)
    events_by_date = _events_by_date(request.user, year, month)

    weeks = [
        [{"date": day, "in_month": day.month == month, "events": events_by_date.get(day, [])} for day in week]
        for week in raw_weeks
    ]

    theme = get_effective_theme(request.user, request.session)
    image = _render_calendar_image(theme, f"{MONTH_NAMES_ES[month]} {year}", weeks)

    response = HttpResponse(content_type="image/png")
    image.save(response, "PNG")
    response["Content-Disposition"] = f'inline; filename="calendario_{year}_{month:02d}.png"'
    return response


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
