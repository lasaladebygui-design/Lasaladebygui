import calendar as calendar_module
import random
import unicodedata
from datetime import date, timedelta
from decimal import Decimal
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
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.models import User
from apps.core.google_calendar import create_event as google_create_event
from apps.core.google_calendar import delete_event as google_delete_event
from apps.core.google_calendar import google_calendar_enabled
from apps.core.models import get_effective_theme
from apps.movies.models import Movie, SavedMovie
from apps.movies.services import MovieAPIError, tmdb_search
from apps.movies.views import build_saved_movies_context
from apps.social.models import CONTACT_BOT_EMAIL, are_friends, friends_of

from .forms import (
    CodeForm,
    FullListFilterForm,
    GenreQuickForm,
    NumberSelectForm,
    RatingSearchForm,
    SecretMovieQuickEditForm,
    SecretPhotoForm,
    TierLevelForm,
)
from .models import (
    CalendarDayNote,
    CalendarShareMember,
    Genre,
    PhotoBoardMember,
    ReleaseEvent,
    SecretListMember,
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


def _shareable_friends(user):
    """`friends_of(user)` sin el Buzón de contacto -- `ensure_friends` os
    hace "amigos" en cuanto escribís por Escríbenos para que podáis
    chatear, pero no es una persona con la que compartir listas/tablón/
    calendario de Top Secret."""
    return [f for f in friends_of(user) if f.email != CONTACT_BOT_EMAIL]


def _visible_movies(user, owner):
    """Base queryset de SecretMovie de UN dueño concreto (`owner`, `None`
    para la lista de Bygui). La lista de Bygui sigue ocultando lo
    `admin_only` a quien no sea Admin, igual que siempre; una lista propia
    se ve entera por quien tenga permiso para verla — ese permiso ya se
    decidió en `_resolve_scope`, aquí no hay nada más que filtrar."""
    movies = SecretMovie.objects.filter(owner=owner).prefetch_related("genres").select_related("movie")
    if owner is None and not _is_admin(user):
        movies = movies.exclude(genres__admin_only=True).exclude(admin_only=True)
    return movies


def _resolve_scope(request):
    """A qué lista completa se refiere esta petición, y si quien mira
    puede editarla. Todo el mundo con cuenta tiene su propia lista,
    siempre editable por su dueño y de nadie más; la lista de Bygui es un
    caso especial de "propia" que por continuidad con los datos de
    siempre se sigue guardando con owner=None en vez de con su usuario, y
    que solo ella (Admin) puede editar — y únicamente mientras
    TopSecretConfig.allow_web_editing esté activo, igual que siempre.

    - 'own' (por defecto si tienes cuenta): tu propia lista.
    - 'bygui' (por defecto si no tienes cuenta): la lista de Bygui — de
      solo lectura para cualquiera que no sea ella.
    - cualquier otro valor: el username de alguien que te ha dado acceso
      de solo lectura a la suya (ver SecretListMember). 404 si no es así.

    Devuelve (owner, editable, scope): `owner` es el User dueño de esa
    lista (None para la de Bygui), `scope` es el valor a propagar en los
    enlaces/formularios de esa misma página."""
    user = request.user
    scope = request.GET.get("scope") or request.POST.get("scope")
    if not scope:
        scope = "own" if user.is_authenticated else "bygui"

    if _is_admin(user) and scope in ("own", "bygui"):
        # Para Bygui, "mi lista" y "la lista de Bygui" son la misma cosa —
        # los datos de siempre, sin una copia aparte vacía para ella.
        return None, _web_editing_allowed(), scope

    if scope == "own":
        if not user.is_authenticated:
            raise Http404
        return user, True, "own"

    if scope == "bygui":
        return None, False, "bygui"

    if not user.is_authenticated:
        raise Http404
    friend_owner = get_object_or_404(User, username=scope)
    if friend_owner.pk == user.pk:
        return user, True, "own"
    if not SecretListMember.objects.filter(owner=friend_owner, member=user).exists():
        raise Http404
    return friend_owner, False, scope


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
def by_number(request):
    owner, editable, scope = _resolve_scope(request)
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
        result = _visible_movies(request.user, owner).filter(number=number).first()
        if result is None and SecretMovie.objects.filter(owner=owner, number=number).exists():
            raise Http404

    comparable_owners = _comparable_owners(request.user) if request.user.is_authenticated else []
    compare = request.GET.get("compare") == "1"
    selected_with = request.GET.getlist("with")
    rows = []
    if compare and searched and selected_with:
        for key, label, o in comparable_owners:
            if key in selected_with:
                rows.append({"label": label, "movie": _visible_movies(request.user, o).filter(number=number).first()})

    return render(request, "secret/by_number.html", {
        "form": form, "result": result, "searched": searched,
        "scope": scope, "editable": editable, "list_owner": owner,
        "active_tab": "number", "shell_tab": "buscar", "can_add": scope == "own",
        "compare": compare, "rows": rows,
        "comparable_owners": comparable_owners, "selected_with": selected_with,
    })


@secret_required
def by_rating(request):
    owner, editable, scope = _resolve_scope(request)
    form = RatingSearchForm(request.GET or None)
    result = None
    searched = False
    genre_slug = request.GET.get("genre", "").strip()
    genres = Genre.objects.filter(owner=owner)
    if owner is None and not _is_admin(request.user):
        genres = genres.filter(admin_only=False)
    selected_genre_name = next((g.name for g in genres if g.slug == genre_slug), "")

    if request.GET and form.is_valid():
        searched = True
        min_r, max_r = int(form.cleaned_data["min_rating"]), int(form.cleaned_data["max_rating"])
        matches = _visible_movies(request.user, owner).filter(personal_rating__gte=min_r, personal_rating__lte=max_r)
        if genre_slug:
            matches = matches.filter(genres__slug=genre_slug)
        matches = list(matches)
        if matches:
            result = random.choice(matches)

    comparable_owners = _comparable_owners(request.user) if request.user.is_authenticated else []
    compare = request.GET.get("compare") == "1"
    selected_with = request.GET.getlist("with")
    rows = []
    if compare and searched and selected_with:
        for key, label, o in comparable_owners:
            if key not in selected_with:
                continue
            owner_matches = list(
                _visible_movies(request.user, o).filter(personal_rating__gte=min_r, personal_rating__lte=max_r)
                .order_by("-personal_rating")
            )
            rows.append({"label": label, "movies": owner_matches})

    return render(request, "secret/by_rating.html", {
        "form": form, "result": result, "searched": searched,
        "genres": genres, "selected_genre": genre_slug, "selected_genre_name": selected_genre_name,
        "scope": scope, "editable": editable, "list_owner": owner,
        "active_tab": "rating", "shell_tab": "buscar", "can_add": scope == "own",
        "compare": compare, "rows": rows,
        "comparable_owners": comparable_owners, "selected_with": selected_with,
    })


@secret_required
def full_list(request):
    owner, editable, scope = _resolve_scope(request)
    form = FullListFilterForm(request.GET or None, owner=owner, admin_user=_is_admin(request.user))
    movies = _visible_movies(request.user, owner)
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
        movies = movies.order_by("personal_rating", "tie_break", "-number")
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
        ).order_by("type_order", "-personal_rating", "-tie_break", "number")
    else:
        sort = "desc"
        movies = movies.order_by("-personal_rating", "-tie_break", "number")

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

    rating_config = TopSecretConfig.load()
    context = {
        "movies": page_obj, "form": form, "rating_config": rating_config,
        "sort": sort, "querystring": querystring.urlencode(), "query": query,
        "media_type": media_type,
        "all_genres": Genre.objects.filter(owner=owner) if editable else Genre.objects.none(),
        "scope": scope, "editable": editable, "list_owner": owner,
        "can_add": scope == "own", "shell_tab": "lista",
    }
    # El scroll infinito (_secret_list_sentinel.html) pide más páginas por
    # HTMX a esta misma URL, esperando solo las filas nuevas -- pero la
    # pestaña "Lista" de la barra lateral del maletín (ver secret/_shell.html)
    # TAMBIÉN pide esta URL por HTMX, y esa sí necesita la página completa
    # (usa hx-select para quedarse solo con #ts-content). Ambas llegan con
    # HX-Request, así que hace falta esta cabecera de más para distinguirlas.
    if _is_htmx(request) and not request.headers.get("HX-Shell-Nav"):
        return render(request, "secret/_list_items.html", context)
    return render(request, "secret/list.html", context)


@secret_required
def movie_detail(request, pk):
    owner, editable, scope = _resolve_scope(request)
    movie = get_object_or_404(_visible_movies(request.user, owner), pk=pk)
    return render(request, "secret/movie_detail.html", {
        "movie": movie, "rating_config": TopSecretConfig.load(),
        "scope": scope, "editable": editable, "list_owner": owner,
        "can_add": scope == "own",
        "all_genres": Genre.objects.filter(owner=owner) if editable else Genre.objects.none(),
    })


# No vista → en emisión → vista → no vista... cualquier orden vale, lo
# importante es que sea el mismo ciclo siempre.
_WATCH_STATUS_CYCLE = [
    SecretMovie.SeriesWatchStatus.NOT_WATCHED,
    SecretMovie.SeriesWatchStatus.AIRING,
    SecretMovie.SeriesWatchStatus.WATCHED,
]


@secret_required
@login_required
def movie_watch_cycle(request, pk):
    owner, editable, scope = _resolve_scope(request)
    movie = get_object_or_404(_visible_movies(request.user, owner), pk=pk)
    if request.method == "POST" and editable and movie.movie_id and movie.movie.is_tv:
        current = movie.series_watch_status or SecretMovie.SeriesWatchStatus.NOT_WATCHED
        next_index = (_WATCH_STATUS_CYCLE.index(current) + 1) % len(_WATCH_STATUS_CYCLE)
        movie.series_watch_status = _WATCH_STATUS_CYCLE[next_index]
        movie.save(update_fields=["series_watch_status"])
    template = "secret/_movie_detail_poster.html" if request.GET.get("context") == "detail" else "secret/_movie_poster.html"
    return render(request, template, {"movie": movie, "scope": scope, "editable": editable})


def _web_editing_allowed():
    return TopSecretConfig.load().allow_web_editing


def _drop_from_saved(user, movie):
    """Una película que acabas de catalogar en una lista secreta (la tuya
    o la de Bygui) ya no necesita seguir en tus Guardadas de "quiero
    verla" -- se quita solo de las TUYAS, nunca de las de otro usuario.
    Si más tarde la vuelves a guardar a mano, se guarda sin problema (esto
    no la bloquea, solo la quita una vez en el momento de catalogarla)."""
    if user.is_authenticated and movie is not None:
        SavedMovie.objects.filter(user=user, movie=movie).delete()


@secret_required
@login_required
def movie_quick_edit(request, pk):
    """Editar título, nota, desempate, comentario y listas de una película
    directamente desde una lista completa, sin pasar por el admin —
    disponible en tu propia lista (u otra que edites vía _resolve_scope)
    sin restricción, y en la de Bygui solo si eres Admin y
    TopSecretConfig.allow_web_editing está activo."""
    owner, editable, scope = _resolve_scope(request)
    if not editable:
        raise Http404
    movie = get_object_or_404(_visible_movies(request.user, owner), pk=pk)
    if request.method == "POST":
        form = SecretMovieQuickEditForm(request.POST, instance=movie, owner=owner)
        if form.is_valid():
            form.save()
            messages.success(request, f"«{movie.title}» actualizada.")
        else:
            messages.error(request, "No se pudo guardar: revisa la nota.")
    return _movie_quick_edit_redirect(request)


def _movie_quick_edit_redirect(request):
    # "next" viene de un campo oculto del propio formulario (para volver a
    # la misma página/filtro, con su ?scope= incluido) — se valida igual
    # que cualquier redirección con destino enviado por el cliente, para
    # que manipular ese campo no sirva para mandar a otra web (open
    # redirect).
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect("secret:list")


@secret_required
@login_required
def movie_poster_search(request, pk):
    """Buscar en TMDb para enlazar como portada desde una lista completa
    (mismo hueco que nota/desempate/listas, ver movie_quick_edit)."""
    owner, editable, scope = _resolve_scope(request)
    if not editable:
        raise Http404
    get_object_or_404(_visible_movies(request.user, owner), pk=pk)
    query = request.GET.get("query", "").strip()
    results = []
    error = None
    if query:
        try:
            results = tmdb_search(query)[:8]
        except MovieAPIError as exc:
            error = str(exc)
    return render(request, "secret/_movie_poster_search_results.html", {
        "results": results, "error": error, "query": query, "movie_pk": pk, "scope": scope,
    })


@secret_required
@login_required
def movie_poster_set(request, pk, tmdb_id):
    owner, editable, scope = _resolve_scope(request)
    if not editable:
        raise Http404
    movie = get_object_or_404(_visible_movies(request.user, owner), pk=pk)
    if request.method == "POST":
        try:
            catalog_movie = Movie.get_or_create_from_tmdb(tmdb_id)
        except MovieAPIError as exc:
            messages.error(request, str(exc))
        else:
            movie.movie = catalog_movie
            movie.save(update_fields=["movie"])
            _drop_from_saved(request.user, catalog_movie)
            messages.success(request, "Portada actualizada.")
    return redirect(f"{reverse('secret:list')}?scope={scope}")


@secret_required
@login_required
def movie_poster_remove(request, pk):
    owner, editable, scope = _resolve_scope(request)
    if not editable:
        raise Http404
    movie = get_object_or_404(_visible_movies(request.user, owner), pk=pk)
    if request.method == "POST":
        movie.movie = None
        movie.save(update_fields=["movie"])
        messages.success(request, "Portada quitada.")
    return _movie_quick_edit_redirect(request)


@secret_required
@login_required
def genre_manage(request):
    owner, editable, scope = _resolve_scope(request)
    if not editable:
        raise Http404
    if request.method == "POST":
        form = GenreQuickForm(request.POST)
        if form.is_valid():
            genre = form.save(commit=False)
            genre.owner = owner
            genre.save()
            messages.success(request, "Lista creada.")
        else:
            messages.error(request, "No se pudo crear la lista (¿ya existe ese nombre?).")
        return redirect(f"{reverse('secret:genre-manage')}?scope={scope}")
    return render(request, "secret/genre_manage.html", {
        "genres": Genre.objects.filter(owner=owner), "form": GenreQuickForm(), "scope": scope,
    })


@secret_required
@login_required
def genre_delete(request, pk):
    owner, editable, scope = _resolve_scope(request)
    if not editable:
        raise Http404
    genre = get_object_or_404(Genre, pk=pk, owner=owner)
    if request.method == "POST":
        genre.delete()
        messages.success(request, f"Lista «{genre.name}» eliminada.")
    return redirect(f"{reverse('secret:genre-manage')}?scope={scope}")


@secret_required
@login_required
def own_movie_add_search(request):
    """Buscar en TMDb (películas Y series) para añadir algo nuevo a tu
    propia lista — a diferencia de la de Bygui (gestionada desde el
    admin), tu lista no tiene equivalente en /admin/: todo el alta se
    hace desde aquí. Solo se elige aquí -- nota, comentario, listas y
    estado de visionado se rellenan justo después, en la propia ficha de
    la película (ver own_movie_add / movie_detail), igual que hace
    Admin al dar de alta una nueva entrada."""
    query = request.GET.get("query", "").strip()
    results = []
    error = None
    if query:
        try:
            results = tmdb_search(query, media_type="movie")[:6] + tmdb_search(query, media_type="tv")[:6]
        except MovieAPIError as exc:
            error = str(exc)
    return render(request, "secret/_own_add_results.html", {"results": results, "error": error, "query": query})


@secret_required
@login_required
def own_movie_add(request, media_type, tmdb_id):
    """Elegida en la búsqueda, se da de alta con una nota provisional --
    el siguiente paso es su propia ficha (con ?edit=1, ya abierta en modo
    edición) para ponerle la nota de verdad, comentario, listas y estado
    de visionado si es serie, exactamente como se editaría cualquier otra
    entrada ya existente."""
    if request.method != "POST" or media_type not in ("movie", "tv"):
        return redirect(f"{reverse('secret:list')}?scope=own")

    try:
        catalog_movie = Movie.get_or_create_from_tmdb(tmdb_id, media_type=media_type)
    except MovieAPIError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('secret:list')}?scope=own")

    existing = SecretMovie.objects.filter(owner=request.user, movie=catalog_movie).first()
    if existing:
        messages.info(request, f"«{catalog_movie.title}» ya está en tu lista.")
        return redirect(f"{reverse('secret:movie-detail', args=[existing.pk])}?scope=own")

    entry = SecretMovie.objects.create(
        owner=request.user, movie=catalog_movie, title=catalog_movie.title, personal_rating=Decimal("5"),
    )
    _drop_from_saved(request.user, catalog_movie)
    return redirect(f"{reverse('secret:movie-detail', args=[entry.pk])}?scope=own&edit=1")


@secret_required
@login_required
def own_movie_delete(request, pk):
    movie = get_object_or_404(SecretMovie, pk=pk, owner=request.user)
    if request.method == "POST":
        movie.delete()
        messages.success(request, f"«{movie.title}» eliminada de tu lista.")
    return redirect(f"{reverse('secret:list')}?scope=own")


@secret_required
@login_required
def saved_movies(request):
    """Guardados dentro del maletín -- mismos datos que Guardadas en
    Películas (ver `build_saved_movies_context`), pero sin salir de Top
    Secret: es la lista de "quiero verla" de siempre, solo que vivida
    como un espacio más de aquí en vez de un salto a otra sección."""
    context = build_saved_movies_context(request)
    context["shell_tab"] = "guardados"
    return render(request, "secret/saved_movies.html", context)


def _comparable_owners(user):
    """Las listas que `user` puede comparar entre sí: la suya propia, la
    de Bygui (siempre visible, como en cualquier otro sitio de Top
    Secret) y la de cada amigo que se la haya compartido. Devuelve una
    lista de (clave, etiqueta, owner) — owner=None es Bygui. `clave` es
    lo que viaja en la URL (?with=...) para elegir con quién comparar;
    ninguna va marcada por defecto, ni siquiera la propia."""
    owners = [("own", "Tú", user), ("bygui", "Admin", None)]
    shared = SecretListMember.objects.filter(member=user).select_related("owner")
    for member in shared:
        owners.append((member.owner.username, member.owner.username, member.owner))
    return owners


@secret_required
@login_required
def compare_lists(request):
    """Comparar la misma posición o el mismo intervalo de nota entre tu
    lista, la de Bygui y las que te hayan compartido tus amigos --
    integra el selector numérico y el buscador por nota (que ya existen
    para una sola lista) pero aplicados a la vez sobre varias listas en
    paralelo, para ver de un vistazo qué puso cada uno en ese hueco."""
    owners = _comparable_owners(request.user)
    mode = request.GET.get("mode", "number")
    if mode not in ("number", "rating"):
        mode = "number"

    number_form = NumberSelectForm(request.GET or None)
    rating_form = RatingSearchForm(request.GET or None, initial={"min_rating": 7, "max_rating": 9})
    searched = False
    rows = []

    if mode == "number" and "number" in request.GET and number_form.is_valid():
        searched = True
        number = number_form.cleaned_data["number"]
        for key, label, owner in owners:
            movie = _visible_movies(request.user, owner).filter(number=number).first()
            rows.append({"label": label, "owner": owner, "movie": movie, "movies": None})
    elif mode == "rating" and "min_rating" in request.GET and rating_form.is_valid():
        searched = True
        min_r = int(rating_form.cleaned_data["min_rating"])
        max_r = int(rating_form.cleaned_data["max_rating"])
        for key, label, owner in owners:
            matches = list(
                _visible_movies(request.user, owner)
                .filter(personal_rating__gte=min_r, personal_rating__lte=max_r)
                .order_by("-personal_rating")
            )
            rows.append({"label": label, "owner": owner, "movie": None, "movies": matches})

    return render(request, "secret/compare.html", {
        "mode": mode, "number_form": number_form, "rating_form": rating_form,
        "searched": searched, "rows": rows, "owners": owners,
        "active_tab": "compare", "scope": request.GET.get("scope") or "own",
    })


def _shared_hub_data(user):
    """Qué comparte `user` de su Top Secret (lista, tablón, calendario)
    con cada amigo, y qué le han compartido a él -- una sola función
    porque el panel se pinta en dos sitios: la propia pantalla de
    Compartidos y, embebido, la home de Top Secret (ver `home`)."""
    friends = _shareable_friends(user)
    list_members = {m.member_id: m for m in SecretListMember.objects.filter(owner=user)}
    photo_members = {m.member_id: m for m in PhotoBoardMember.objects.filter(owner=user)}
    calendar_members = {m.member_id: m for m in CalendarShareMember.objects.filter(owner=user)}

    rows = [
        {
            "friend": friend,
            "list_member": list_members.get(friend.pk),
            "photo_member": photo_members.get(friend.pk),
            "calendar_member": calendar_members.get(friend.pk),
        }
        for friend in friends
    ]

    # Agrupado por amigo (no por apartado) para poder enseñar, de un
    # vistazo en Compartidos, todo lo que te ha compartido cada uno --
    # antes eran tres listas sueltas de nombres, una por apartado.
    shared_list_owners = {m.owner_id: m.owner for m in SecretListMember.objects.filter(member=user).select_related("owner")}
    shared_photo_owners = {m.owner_id: m.owner for m in PhotoBoardMember.objects.filter(member=user).select_related("owner")}
    shared_calendar_owners = {m.owner_id: m.owner for m in CalendarShareMember.objects.filter(member=user).select_related("owner")}
    all_sharer_ids = set(shared_list_owners) | set(shared_photo_owners) | set(shared_calendar_owners)
    all_sharers = {**shared_list_owners, **shared_photo_owners, **shared_calendar_owners}
    shared_with_me = [
        {
            "owner": all_sharers[owner_id],
            "has_list": owner_id in shared_list_owners,
            "has_photos": owner_id in shared_photo_owners,
            "has_calendar": owner_id in shared_calendar_owners,
        }
        for owner_id in all_sharer_ids
    ]
    shared_with_me.sort(key=lambda row: row["owner"].username.lower())
    return rows, shared_with_me


def _amigos_preview(request_user, friend, tab):
    """Adelanto de lo que `friend` te ha compartido, para verlo sin salir
    de Amigos -- unas pocas filas de cada cosa (no toda la lista/tablón/
    calendario entero: para eso está el enlace "Ver completo" a la
    página de siempre, con toda su paginación/filtros/edición)."""
    if tab == "tablon":
        return list(
            SecretPhoto.objects.filter(board_owner=friend).select_related("uploaded_by")[:8]
        )
    if tab == "calendario":
        today = timezone.localdate()
        return list(
            ReleaseEvent.objects.filter(user=friend, date__gte=today)
            .select_related("movie").order_by("date")[:6]
        )
    return list(_visible_movies(request_user, friend).order_by("number")[:12])


@secret_required
@login_required
def shared_hub(request):
    """Amigos: a la izquierda quién te comparte algo, a la derecha un
    adelanto de su Lista/Tablón/Calendario (según lo que te haya
    compartido) con pestañas para moverte entre ellas -- sin salir de
    aquí ni pasar por una página nueva por cada amigo. Debajo sigue "Con
    quién compartes", para decidir qué le enseñas tú a cada uno (los
    interruptores reutilizan las mismas invitar/expulsar de cada
    apartado, así que activarlos ahí o desde aquí es exactamente lo
    mismo)."""
    rows, shared_with_me = _shared_hub_data(request.user)

    by_username = {row["owner"].username: row for row in shared_with_me}
    selected_username = request.GET.get("friend") or (shared_with_me[0]["owner"].username if shared_with_me else None)
    selected_row = by_username.get(selected_username)

    selected_tab = request.GET.get("tab", "lista")
    tab_available = {
        "lista": selected_row and selected_row["has_list"],
        "tablon": selected_row and selected_row["has_photos"],
        "calendario": selected_row and selected_row["has_calendar"],
    }
    if not tab_available.get(selected_tab):
        selected_tab = next((tab for tab, available in tab_available.items() if available), "lista")

    preview = None
    if selected_row and tab_available.get(selected_tab):
        preview = _amigos_preview(request.user, selected_row["owner"], selected_tab)

    context = {
        "rows": rows, "shared_with_me": shared_with_me, "shell_tab": "compartidos",
        "selected_row": selected_row,
        "selected_tab": selected_tab,
        "preview": preview,
    }
    # Igual que en full_list: cambiar de amigo/pestaña pide esta misma URL
    # por HTMX y solo necesita el hueco de la derecha, pero la navegación
    # del maletín (hx-select sobre la página entera) TAMBIÉN pide esta URL
    # por HTMX -- la cabecera de más distingue una cosa de la otra.
    if _is_htmx(request) and not request.headers.get("HX-Shell-Nav"):
        return render(request, "secret/_amigos_panel.html", context)
    return render(request, "secret/shared_hub.html", context)


@secret_required
@login_required
def own_list_share(request):
    """Gestionar con qué amigos compartes tu lista propia (solo lectura
    para ellos) — mismo patrón que el tablón de fotos (PhotoBoardMember)."""
    members = SecretListMember.objects.filter(owner=request.user).select_related("member")
    member_ids = {m.member_id for m in members}
    invitable_friends = [f for f in _shareable_friends(request.user) if f.pk not in member_ids]
    shared_with_me = SecretListMember.objects.filter(member=request.user).select_related("owner")
    return render(request, "secret/own_list_share.html", {
        "members": members, "invitable_friends": invitable_friends, "shared_with_me": shared_with_me,
    })


@secret_required
@login_required
def own_list_share_invite(request, username):
    """El propio interruptor (visible sea cual sea el resultado) ya deja
    claro que la invitación se aplicó -- el mensaje de confirmación solo
    hace falta cuando la petición viene de fuera de HTMX, si no se queda
    en cola sin mostrarse nunca (el parcial no pinta `messages`) y acaba
    reapareciendo de golpe, fuera de contexto, en la próxima página
    completa que se cargue -- fue justo el bug reportado."""
    friend = get_object_or_404(User, username=username)
    member = None
    if request.method == "POST" and are_friends(request.user, friend):
        member, _ = SecretListMember.objects.get_or_create(owner=request.user, member=friend)
        if not _is_htmx(request):
            messages.success(request, f"{friend} ya puede ver tu lista.")
    if _is_htmx(request):
        return render(request, "secret/_share_toggle_list.html", {"friend": friend, "member": member})
    return redirect("secret:own-list-share")


@secret_required
@login_required
def own_list_share_kick(request, pk):
    member = get_object_or_404(SecretListMember, pk=pk, owner=request.user)
    friend = member.member
    if request.method == "POST":
        member.delete()
        if _is_htmx(request):
            return render(request, "secret/_share_toggle_list.html", {"friend": friend, "member": None})
        messages.success(request, f"{friend} ya no puede ver tu lista.")
    return redirect("secret:own-list-share")


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

    photos = SecretPhoto.objects.filter(board_owner=owner).select_related("uploaded_by")
    context = {"photos": photos, "board_owner": owner, "is_owner": is_owner, "shell_tab": "tablon"}

    if is_owner:
        members = PhotoBoardMember.objects.filter(owner=request.user).select_related("member")
        member_ids = {m.member_id for m in members}
        invitable_friends = [f for f in _shareable_friends(request.user) if f.pk not in member_ids]
        shared_with_me = PhotoBoardMember.objects.filter(member=request.user).select_related("owner")
        context.update({
            "members": members,
            "invitable_friends": invitable_friends,
            "shared_with_me": shared_with_me,
        })

    return render(request, "secret/photo_board.html", context)


@secret_required
@login_required
def photo_board_upload(request, username=None):
    # Antes vivía como un formulario más metido dentro de la propia página
    # del tablón, mezclado con "gestionar acceso" y la cuadrícula de fotos —
    # ahora es su propia pantalla, con un botón "Subir foto" que lleva aquí.
    owner = request.user
    if username:
        owner = get_object_or_404(User, username=username)
        if not _can_access_photo_board(request.user, owner):
            raise Http404

    is_owner = owner.pk == request.user.pk

    if request.method == "POST":
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

    return render(request, "secret/photo_board_upload.html", {
        "form": form, "board_owner": owner, "is_owner": is_owner,
    })


@secret_required
@login_required
def photo_board_invite(request, username):
    friend = get_object_or_404(User, username=username)
    member = None
    if request.method == "POST" and are_friends(request.user, friend):
        member, _ = PhotoBoardMember.objects.get_or_create(owner=request.user, member=friend)
        if not _is_htmx(request):
            messages.success(request, f"{friend} ya puede ver y subir fotos a tu tablón.")
    if _is_htmx(request):
        return render(request, "secret/_share_toggle_photos.html", {"friend": friend, "member": member})
    return redirect("secret:photo-board")


@secret_required
@login_required
def photo_board_kick(request, pk):
    member = get_object_or_404(PhotoBoardMember, pk=pk, owner=request.user)
    friend = member.member
    if request.method == "POST":
        member.delete()
        if _is_htmx(request):
            return render(request, "secret/_share_toggle_photos.html", {"friend": friend, "member": None})
        messages.success(request, f"{friend} ya no tiene acceso a tu tablón.")
    return redirect("secret:photo-board")


def _photo_board_redirect(board_owner, viewer):
    if board_owner.pk == viewer.pk:
        return redirect("secret:photo-board")
    return redirect("secret:photo-board-shared", board_owner.username)


@secret_required
@login_required
def photo_board_edit(request, pk):
    # Solo quien subió la foto puede editarla — no el dueño del tablón por
    # sí solo, si la foto es de otra persona invitada. Antes era una
    # cajita minúscula solo para la descripción, sin poder tocar la
    # imagen — ahora es su propia pantalla, con el mismo formulario que
    # subir (así si la foto salió mal también se puede resubir de verdad,
    # no solo retocar el texto).
    photo = get_object_or_404(SecretPhoto, pk=pk, uploaded_by=request.user)
    if request.method == "POST":
        form = SecretPhotoForm(request.POST, request.FILES, instance=photo)
        if form.is_valid():
            form.save()
            messages.success(request, "Foto actualizada.")
            return _photo_board_redirect(photo.board_owner, request.user)
    else:
        form = SecretPhotoForm(instance=photo)

    return render(request, "secret/photo_board_edit.html", {"form": form, "photo": photo})


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


def _can_access_calendar(viewer, owner):
    return viewer.pk == owner.pk or CalendarShareMember.objects.filter(owner=owner, member=viewer).exists()


@secret_required
@login_required
def calendar_view(request, username=None):
    owner = request.user
    if username:
        owner = get_object_or_404(User, username=username)
        if not _can_access_calendar(request.user, owner):
            raise Http404
    is_owner = owner.pk == request.user.pk

    today = timezone.localdate()
    year, month, first_of_month = _parse_calendar_month(request, today)

    raw_weeks = calendar_module.Calendar(firstweekday=0).monthdatescalendar(year, month)
    events_by_date = _events_by_date(owner, year, month)

    notes_by_date = {
        note.date: note.note
        for note in CalendarDayNote.objects.filter(user=owner, date__year=year, date__month=month)
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
        "google_calendar_enabled": google_calendar_enabled() if is_owner else False,
        "google_calendar_connected": is_owner and hasattr(request.user, "google_calendar_connection"),
        "calendar_owner": owner,
        "is_owner": is_owner,
        "shell_tab": "calendario",
    })


@secret_required
@login_required
def calendar_share(request):
    """Gestionar con qué amigos compartes tu calendario (solo lectura para
    ellos) — mismo patrón que el tablón de fotos y tu lista propia."""
    members = CalendarShareMember.objects.filter(owner=request.user).select_related("member")
    member_ids = {m.member_id for m in members}
    invitable_friends = [f for f in _shareable_friends(request.user) if f.pk not in member_ids]
    shared_with_me = CalendarShareMember.objects.filter(member=request.user).select_related("owner")
    return render(request, "secret/calendar_share.html", {
        "members": members, "invitable_friends": invitable_friends, "shared_with_me": shared_with_me,
    })


@secret_required
@login_required
def calendar_share_invite(request, username):
    friend = get_object_or_404(User, username=username)
    member = None
    if request.method == "POST" and are_friends(request.user, friend):
        member, _ = CalendarShareMember.objects.get_or_create(owner=request.user, member=friend)
        if not _is_htmx(request):
            messages.success(request, f"{friend} ya puede ver tu calendario.")
    if _is_htmx(request):
        return render(request, "secret/_share_toggle_calendar.html", {"friend": friend, "member": member})
    return redirect("secret:calendar-share")


@secret_required
@login_required
def calendar_share_kick(request, pk):
    member = get_object_or_404(CalendarShareMember, pk=pk, owner=request.user)
    friend = member.member
    if request.method == "POST":
        member.delete()
        if _is_htmx(request):
            return render(request, "secret/_share_toggle_calendar.html", {"friend": friend, "member": None})
        messages.success(request, f"{friend} ya no puede ver tu calendario.")
    return redirect("secret:calendar-share")


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
