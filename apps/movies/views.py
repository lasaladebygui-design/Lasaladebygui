import json
import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Max, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core.models import get_effective_theme
from apps.core.text import ascii_safe

from .forms import MovieSearchForm, RatingRangeForm, VoteForm
from .models import Movie, RouletteRatingSeen, RouletteSavedSeen, SavedMovie, SavedMovieList, Vote
from .services import MovieAPIError, tmdb_search

SPIN_DECOYS = 5
SPIN_REELS = 3
DECOY_SAMPLE_SIZE = 30
MEDIA_TYPES = ("movie", "tv", "all")


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _media_type_from_request(request, default="movie"):
    value = request.GET.get("type", default)
    return value if value in MEDIA_TYPES else default


def _random_row(queryset):
    """Elige una fila al azar sin `order_by("?")`: ese truco obliga a la
    base de datos a calcular un número aleatorio y ORDENAR LA TABLA ENTERA
    solo para quedarse con una fila — con un catálogo grande es justo lo que
    seguía haciendo lenta la ruleta incluso después de dejar de traer todo a
    Python. Contar filas y saltar a un OFFSET al azar es muchísimo más
    barato para la base de datos."""
    count = queryset.count()
    if not count:
        return None
    return queryset[random.randrange(count)]


def _random_sample(queryset, sample_size):
    """Igual que `_random_row` pero para varias filas: salta a un tramo al
    azar y coge de ahí, en vez de ordenar la tabla entera al azar."""
    count = queryset.count()
    if count <= sample_size:
        return list(queryset)
    offset = random.randint(0, count - sample_size)
    return list(queryset[offset:offset + sample_size])


def _build_reel(final_movie, decoy_queryset):
    """Tres tiras (tipo tragaperras) que giran por separado y acaban todas
    en el mismo cartel — cada una baraja sus propios señuelos, así no se ven
    tres tiras idénticas girando a la vez.

    `decoy_queryset` puede ser un catálogo entero (miles de filas): solo se
    trae una muestra aleatoria acotada de la base de datos en vez de volcarlo
    todo a Python, que es justo lo que hacía tardar tanto en cargar la
    ruleta por nota (se traía el catálogo completo dos veces por cada giro)."""
    others = _random_sample(decoy_queryset.exclude(pk=final_movie.pk), DECOY_SAMPLE_SIZE)
    reels = []
    for _ in range(SPIN_REELS):
        decoys = list(others)
        random.shuffle(decoys)
        decoys = decoys[:SPIN_DECOYS] or [final_movie] * SPIN_DECOYS
        reel = decoys + [final_movie]
        reels.append([m.poster_url or "" for m in reel])
    return json.dumps(reels)


# --- Catálogo y votación ----------------------------------------------------

def movie_list(request):
    form = MovieSearchForm(request.GET or None)
    media_type = _media_type_from_request(request)
    movies = Movie.objects.all() if media_type == "all" else Movie.objects.filter(media_type=media_type)
    query = ""

    if form.is_valid() and form.cleaned_data["query"]:
        query = form.cleaned_data["query"]
        movies = movies.filter(title__icontains=query)

    paginator = Paginator(movies, 24)
    page = paginator.get_page(request.GET.get("page"))

    if _is_htmx(request):
        # Scroll infinito: cada tramo siguiente solo necesita las tarjetas
        # de esa página y, si hay más, el próximo "sensor" — no hace falta
        # repetir la búsqueda en vivo a TMDb en cada tramo.
        return render(request, "movies/_movie_grid_page.html", {"page_obj": page, "query": query, "media_type": media_type})

    external_results = []
    search_error = None
    if query:
        # El catálogo local solo tiene lo ya sembrado/visto antes: se
        # complementa con una búsqueda en vivo a TMDb para que cualquier
        # título que se busque aparezca, no solo los ya cacheados. Si el
        # tipo elegido es "all" se busca en los dos catálogos de TMDb.
        types_to_search = ("movie", "tv") if media_type == "all" else (media_type,)
        local_ids = set(
            Movie.objects.filter(media_type__in=types_to_search).values_list("tmdb_id", "media_type")
        )
        try:
            tmdb_results = []
            for t in types_to_search:
                tmdb_results += tmdb_search(query, media_type=t)
        except MovieAPIError as exc:
            search_error = str(exc)
        else:
            external_results = [
                r for r in tmdb_results if (r.tmdb_id, r.media_type) not in local_ids
            ][:12]

    return render(request, "movies/list.html", {
        "page_obj": page,
        "form": form,
        "query": query,
        "external_results": external_results,
        "search_error": search_error,
        "media_type": media_type,
    })


def movie_from_tmdb(request, media_type, tmdb_id):
    if media_type not in ("movie", "tv"):
        raise Http404
    try:
        movie = Movie.get_or_create_from_tmdb(tmdb_id, media_type=media_type)
    except MovieAPIError as exc:
        messages.error(request, str(exc))
        return redirect("movies:list")
    return redirect("movies:detail", pk=movie.pk)


def movie_detail(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    user_vote = None
    is_saved = False
    saved_lists = []
    current_list_ids = set()
    if request.user.is_authenticated:
        user_vote = Vote.objects.filter(movie=movie, user=request.user).first()
        is_saved = SavedMovie.objects.filter(movie=movie, user=request.user).exists()
        saved_lists = SavedMovieList.objects.filter(user=request.user)
        current_list_ids = set(
            SavedMovie.objects.filter(movie=movie, user=request.user).values_list("sublists__pk", flat=True)
        )
    vote_form = VoteForm(initial={"score": user_vote.score if user_vote else None})
    return render(request, "movies/detail.html", {
        "movie": movie, "vote_form": vote_form, "user_vote": user_vote, "is_saved": is_saved,
        "saved_lists": saved_lists, "current_list_ids": current_list_ids,
    })


@login_required
def movie_save_toggle(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    if request.method == "POST":
        saved, created = SavedMovie.objects.get_or_create(movie=movie, user=request.user)
        if not created:
            saved.delete()
            messages.success(request, "Quitada de tus películas guardadas.")
        else:
            messages.success(request, "¡Guardada en tus películas!")
    return redirect("movies:detail", pk=movie.pk)


@login_required
def movie_save_lists(request, pk):
    """Marcar en qué listas está una guardada, directamente desde su ficha
    (no solo desde 'Guardadas') — guardarla y añadirla a listas es un único
    paso: marcar una casilla ya la guarda si no lo estaba todavía. Solo
    aparece si ya tienes alguna lista creada, así no estorba a quien no usa
    listas."""
    movie = get_object_or_404(Movie, pk=pk)
    just_saved = False
    if request.method == "POST":
        saved, created = SavedMovie.objects.get_or_create(movie=movie, user=request.user)
        just_saved = created
        list_ids = request.POST.getlist("sublists")
        saved.sublists.set(SavedMovieList.objects.filter(user=request.user, pk__in=list_ids))

    saved_lists = SavedMovieList.objects.filter(user=request.user)
    current_list_ids = set(
        SavedMovie.objects.filter(movie=movie, user=request.user).values_list("sublists__pk", flat=True)
    )
    menu_html = render_to_string("movies/_save_lists_menu.html", {
        "movie": movie, "saved_lists": saved_lists, "current_list_ids": current_list_ids,
    }, request=request)
    if just_saved:
        # Marcar una lista guarda la película de paso si no lo estaba —
        # el botón "Guardar película" de al lado tiene que reflejarlo,
        # por eso este trozo extra "fuera de banda" (hx-swap-oob) además
        # del propio desplegable de listas.
        menu_html += render_to_string("movies/_save_toggle_oob.html", {}, request=request)
    return HttpResponse(menu_html)


@login_required
def my_movies(request):
    media_type = _media_type_from_request(request)
    votes = Vote.objects.filter(user=request.user).select_related("movie").order_by("-updated_at")
    if media_type != "all":
        votes = votes.filter(movie__media_type=media_type)
    return render(request, "movies/my_movies.html", {"votes": votes, "media_type": media_type})


def _filter_by_sublist(queryset, list_param):
    if list_param == "none":
        return queryset.filter(sublists__isnull=True)
    if list_param:
        return queryset.filter(sublists=list_param)
    return queryset


@login_required
def saved_movies(request):
    media_type = _media_type_from_request(request, default="all")
    list_param = request.GET.get("list", "")
    query = request.GET.get("q", "").strip()

    saved = SavedMovie.objects.filter(user=request.user).select_related("movie").prefetch_related("sublists").order_by("order", "-saved_at")
    if media_type != "all":
        saved = saved.filter(movie__media_type=media_type)
    saved = _filter_by_sublist(saved, list_param)
    if query:
        saved = saved.filter(movie__title__icontains=query)

    sublists = SavedMovieList.objects.filter(user=request.user)
    current_list = None
    if list_param and list_param != "none":
        current_list = next((s for s in sublists if str(s.pk) == list_param), None)

    return render(request, "movies/saved_movies.html", {
        "saved": saved, "media_type": media_type,
        "sublists": sublists,
        "list_param": list_param,
        "current_list": current_list,
        "query": query,
    })


def _wrap_text(draw, text, font, max_width):
    words = text.split(" ")
    lines, current = [], ""
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


def _render_saved_movies_image(theme, username, groups):
    """PNG minimalista para compartir Guardadas agrupadas por lista (ver
    _render_favorites_image en apps/accounts/views.py, mismo patrón).
    `groups` es una lista de (nombre_de_lista, [títulos]), en el mismo
    orden en que el usuario las tiene colocadas."""
    from PIL import Image, ImageDraw, ImageFont

    width, pad = 640, 32
    font_title = ImageFont.load_default(size=26)
    font_meta = ImageFont.load_default(size=13)
    font_group = ImageFont.load_default(size=16)
    font_item = ImageFont.load_default(size=15)

    dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    content_width = width - pad * 2

    group_lines = []
    for name, titles in groups:
        items = [_wrap_text(dummy_draw, f"·  {ascii_safe(title)}", font_item, content_width) for title in titles] or [["(vacía)"]]
        group_lines.append((ascii_safe(name), items))

    header_h = 78
    groups_h = 0
    for _, items in group_lines:
        groups_h += 28 + sum(len(lines) * 22 for lines in items) + 14
    footer_h = 30
    height = pad * 2 + header_h + groups_h + footer_h

    img = Image.new("RGB", (width, height), theme.color_bg)
    draw = ImageDraw.Draw(img)

    draw.text((pad, pad), "Guardadas", font=font_title, fill=theme.color_accent)
    draw.text((pad, pad + 36), ascii_safe(f"por {username} - La Sala de Bygui"), font=font_meta, fill=theme.color_text_muted)
    draw.line([(pad, pad + 58), (width - pad, pad + 58)], fill=theme.color_border, width=1)

    y = pad + header_h
    for name, items in group_lines:
        draw.text((pad, y), name, font=font_group, fill=theme.color_accent_secondary)
        y += 28
        for lines in items:
            for line in lines:
                draw.text((pad, y), line, font=font_item, fill=theme.color_text)
                y += 22
        y += 14

    return img


@login_required
def saved_movies_share_image(request):
    saved = list(
        SavedMovie.objects.filter(user=request.user)
        .select_related("movie").prefetch_related("sublists").order_by("order", "-saved_at")
    )
    sublists = SavedMovieList.objects.filter(user=request.user)

    groups = []
    for sublist in sublists:
        titles = [s.movie.title for s in saved if sublist in s.sublists.all()]
        if titles:
            groups.append((sublist.name, titles))
    no_list_titles = [s.movie.title for s in saved if not s.sublists.all()]
    if no_list_titles:
        groups.append(("Sin lista", no_list_titles))
    if not groups:
        groups = [("Guardadas", [])]

    theme = get_effective_theme(request.user, request.session)
    image = _render_saved_movies_image(theme, str(request.user), groups)

    response = HttpResponse(content_type="image/png")
    image.save(response, "PNG")
    response["Content-Disposition"] = f'inline; filename="guardadas_{request.user.username}.png"'
    return response


@login_required
def saved_movies_share_preview(request):
    return render(request, "core/_share_image_preview.html", {
        "title": "Guardadas",
        "image_url": reverse("movies:saved-movies-share-image"),
        "filename": f"guardadas_{request.user.username}.png",
        "back_url": reverse("movies:saved-movies"),
    })


@login_required
def saved_list_create(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()[:60]
        if name:
            max_order = SavedMovieList.objects.filter(user=request.user).aggregate(Max("order"))["order__max"] or 0
            _, created = SavedMovieList.objects.get_or_create(
                user=request.user, name=name, defaults={"order": max_order + 1},
            )
            if not created:
                messages.info(request, "Ya tenías una lista con ese nombre.")
    return redirect("movies:saved-movies")


@login_required
def saved_list_reorder(request):
    """Arrastrar y soltar las propias listas de guardadas (ver
    static/js/sortable_list.js) — antes solo se podía cambiar su orden
    entrando al admin y editando el número a mano. Solo toca las del
    usuario que hace la petición, cada uno tiene su propio orden."""
    if request.method != "POST":
        return JsonResponse({"error": "Solo POST"}, status=405)
    try:
        ids = json.loads(request.body).get("order", [])
    except (TypeError, ValueError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    lists = {sl.pk: sl for sl in SavedMovieList.objects.filter(user=request.user)}
    updated = []
    for position, pk in enumerate(ids):
        sublist = lists.get(pk)
        if sublist is not None:
            sublist.order = position
            updated.append(sublist)
    if updated:
        SavedMovieList.objects.bulk_update(updated, ["order"])
    return JsonResponse({"ok": True})


@login_required
def saved_list_delete(request, pk):
    sublist = get_object_or_404(SavedMovieList, pk=pk, user=request.user)
    if request.method == "POST":
        sublist.delete()
        messages.success(request, "Lista borrada. Sus películas siguen guardadas.")
    return redirect("movies:saved-movies")


@login_required
def saved_movie_toggle_sublist(request, pk, list_id):
    saved = get_object_or_404(SavedMovie, pk=pk, user=request.user)
    sublist = get_object_or_404(SavedMovieList, pk=list_id, user=request.user)
    if request.method == "POST":
        if saved.sublists.filter(pk=sublist.pk).exists():
            saved.sublists.remove(sublist)
        else:
            saved.sublists.add(sublist)
    return redirect("movies:saved-movies")


@login_required
def saved_movie_remove(request, pk):
    saved = get_object_or_404(SavedMovie, pk=pk, user=request.user)
    if request.method == "POST":
        saved.delete()
        if _is_htmx(request):
            return HttpResponse(status=200)
        messages.success(request, "Quitada de tus películas guardadas.")
    return redirect("movies:saved-movies")


@login_required
def saved_movie_move(request, pk, direction):
    if request.method != "POST" or direction not in ("up", "down"):
        raise Http404
    saved = get_object_or_404(SavedMovie, pk=pk, user=request.user)
    ordered = list(SavedMovie.objects.filter(user=request.user).order_by("order", "-saved_at"))
    index = next((i for i, s in enumerate(ordered) if s.pk == saved.pk), None)
    if index is None:
        raise Http404

    swap_index = index - 1 if direction == "up" else index + 1
    if 0 <= swap_index < len(ordered):
        other = ordered[swap_index]
        saved.order, other.order = swap_index, index
        SavedMovie.objects.bulk_update([saved, other], ["order"])
    return redirect("movies:saved-movies")


@login_required
def saved_movie_reorder(request):
    """Arrastrar y soltar en la lista de guardadas (ver static/js/sortable_list.js).
    La lista arrastrada puede estar filtrada (por lista o por tipo), así que
    los pks que llegan son solo un subconjunto de todas las guardadas del
    usuario: en vez de renumerarlas de 0 a N (eso desordenaría las que no se
    ven ahora mismo), se recorre el orden global actual y, en cada hueco que
    ocupaba una guardada visible, se coloca la siguiente según el nuevo
    orden — las no visibles no se mueven de su sitio."""
    if request.method != "POST":
        return JsonResponse({"error": "Solo POST"}, status=405)
    try:
        ids = json.loads(request.body).get("order", [])
    except (TypeError, ValueError):
        return JsonResponse({"error": "JSON inválido"}, status=400)

    all_saved = list(SavedMovie.objects.filter(user=request.user).order_by("order", "-saved_at"))
    by_pk = {s.pk: s for s in all_saved}
    visible_ids = [pk for pk in ids if pk in by_pk]
    visible_set = set(visible_ids)
    ids_iter = iter(visible_ids)

    final_sequence = [
        by_pk[next(ids_iter)] if obj.pk in visible_set else obj
        for obj in all_saved
    ]
    for position, saved in enumerate(final_sequence):
        saved.order = position
    SavedMovie.objects.bulk_update(final_sequence, ["order"])
    return JsonResponse({"ok": True})


@login_required
def movie_vote(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    if request.method == "POST":
        form = VoteForm(request.POST)
        if form.is_valid():
            Vote.objects.update_or_create(
                movie=movie, user=request.user, defaults={"score": form.cleaned_data["score"]}
            )
            if not _is_htmx(request):
                messages.success(request, "¡Voto registrado!")

    movie.refresh_from_db()
    user_vote = Vote.objects.filter(movie=movie, user=request.user).first()
    vote_form = VoteForm(initial={"score": user_vote.score if user_vote else None})
    context = {"movie": movie, "vote_form": vote_form, "user_vote": user_vote}

    if _is_htmx(request):
        return render(request, "movies/_vote_widget.html", context)
    return redirect("movies:detail", pk=movie.pk)


@login_required
def movie_vote_remove(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    if request.method == "POST":
        Vote.objects.filter(movie=movie, user=request.user).delete()
        if not _is_htmx(request):
            messages.success(request, "Nota quitada. Ya no aparece en «Mis películas».")

    movie.refresh_from_db()
    vote_form = VoteForm()
    context = {"movie": movie, "vote_form": vote_form, "user_vote": None}

    if _is_htmx(request):
        return render(request, "movies/_vote_widget.html", context)
    return redirect("movies:detail", pk=movie.pk)


# --- Ruleta: selector de modo -----------------------------------------------

def roulette_home(request):
    return render(request, "movies/roulette_home.html")


# --- Ruleta Modo 1: rango de nota IMDb --------------------------------------

@login_required
def roulette_rating(request):
    result = None
    reel = None
    form = RatingRangeForm(request.POST or None, initial={"min_rating": 1, "max_rating": 10})

    if request.method == "POST" and form.is_valid():
        min_r, max_r = int(form.cleaned_data["min_rating"]), int(form.cleaned_data["max_rating"])
        candidates = Movie.objects.filter(imdb_rating__gte=min_r, imdb_rating__lte=max_r)
        seen_ids = RouletteRatingSeen.objects.filter(user=request.user).values_list("movie_id", flat=True)
        unseen = candidates.exclude(pk__in=seen_ids)

        # random.choice(list(unseen)) traía el catálogo entero a Python solo
        # para elegir una fila — con miles de películas eso es justo lo que
        # hacía tardar la ruleta en cargar. _random_row cuenta y salta a un
        # offset al azar en vez de eso (y en vez de order_by("?"), que
        # también sale caro: obliga a la base de datos a ordenar la tabla
        # entera al azar solo para quedarse con una fila).
        result = _random_row(unseen)

        if not candidates.exists():
            messages.warning(request, "Todavía no hay películas del catálogo en ese rango de nota.")
        elif result is None:
            messages.info(request, "Has agotado las películas de ese rango. Dale a «reiniciar» para verlas de nuevo.")
        else:
            RouletteRatingSeen.objects.get_or_create(user=request.user, movie=result)
            reel = _build_reel(result, candidates)

    return render(request, "movies/roulette_rating.html", {
        "form": form, "result": result, "reel_json": reel,
    })


@login_required
def roulette_rating_reset(request):
    if request.method == "POST":
        RouletteRatingSeen.objects.filter(user=request.user).delete()
        messages.success(request, "Reiniciado: volverás a ver todas las películas de cada rango.")
    return redirect("movies:roulette-rating")


# --- Ruleta Modo 2: gira sobre tus Guardadas --------------------------------
# No hay una lista de candidatas aparte: guardar una película (botón
# "Guardar película" en su ficha) ya la hace elegible aquí. Esto solo
# registra cuáles ya han salido, para no repetir hasta reiniciar.

def _roulette_saved_context(user, list_param=""):
    saved = _filter_by_sublist(SavedMovie.objects.filter(user=user).select_related("movie"), list_param)
    seen_ids = set(RouletteSavedSeen.objects.filter(user=user).values_list("movie_id", flat=True))
    for item in saved:
        item.is_seen = item.movie_id in seen_ids
    sublists = SavedMovieList.objects.filter(user=user)
    current_list = None
    if list_param and list_param != "none":
        current_list = next((s for s in sublists if str(s.pk) == list_param), None)
    return {
        "saved": saved, "unseen_count": sum(1 for item in saved if not item.is_seen),
        "sublists": sublists, "list_param": list_param, "current_list": current_list,
    }


@login_required
def roulette_list(request):
    list_param = request.GET.get("list", "")
    return render(request, "movies/roulette_list.html", _roulette_saved_context(request.user, list_param))


@login_required
def roulette_list_draw(request):
    result = None
    reel = None
    list_param = request.POST.get("list", "")
    saved = _filter_by_sublist(SavedMovie.objects.filter(user=request.user).select_related("movie"), list_param)

    if request.method == "POST":
        seen_ids = RouletteSavedSeen.objects.filter(user=request.user).values_list("movie_id", flat=True)
        unseen = list(saved.exclude(movie_id__in=seen_ids))
        if not saved.exists():
            messages.warning(request, "Todavía no has guardado ninguna película en esta lista.")
        elif not unseen:
            messages.info(request, "Has visto todas las de esta lista. Dale a «reiniciar» para volver a empezar.")
        else:
            chosen = random.choice(unseen).movie
            RouletteSavedSeen.objects.get_or_create(user=request.user, movie=chosen)
            result = chosen
            reel = _build_reel(result, Movie.objects.filter(pk__in=[s.movie_id for s in saved]))

    return render(request, "movies/roulette_list_result.html", {
        **_roulette_saved_context(request.user, list_param), "result": result, "reel_json": reel,
    })


@login_required
def roulette_list_reset(request):
    list_param = request.POST.get("list", "")
    if request.method == "POST":
        RouletteSavedSeen.objects.filter(user=request.user).delete()
        messages.success(request, "Reiniciado: volverás a ver todas tus guardadas.")
    if list_param:
        return redirect(f"{reverse('movies:roulette-list')}?list={list_param}")
    return redirect("movies:roulette-list")
