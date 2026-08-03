import json
import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import MovieSearchForm, RatingRangeForm, VoteForm
from .models import Movie, RouletteRatingSeen, RouletteSavedSeen, SavedMovie, SavedMovieList, Vote
from .services import MovieAPIError, tmdb_search

SPIN_DECOYS = 5
MEDIA_TYPES = ("movie", "tv", "all")


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _media_type_from_request(request):
    value = request.GET.get("type", "movie")
    return value if value in MEDIA_TYPES else "movie"


def _build_reel(final_movie, decoy_pool):
    decoys = [m for m in decoy_pool if m.pk != final_movie.pk]
    random.shuffle(decoys)
    decoys = decoys[:SPIN_DECOYS] or [final_movie] * SPIN_DECOYS
    reel = decoys + [final_movie]
    return json.dumps([m.poster_url or "" for m in reel])


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
    if request.user.is_authenticated:
        user_vote = Vote.objects.filter(movie=movie, user=request.user).first()
        is_saved = SavedMovie.objects.filter(movie=movie, user=request.user).exists()
    vote_form = VoteForm(initial={"score": user_vote.score if user_vote else None})
    return render(request, "movies/detail.html", {
        "movie": movie, "vote_form": vote_form, "user_vote": user_vote, "is_saved": is_saved,
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
def my_movies(request):
    media_type = _media_type_from_request(request)
    votes = Vote.objects.filter(user=request.user).select_related("movie").order_by("-updated_at")
    if media_type != "all":
        votes = votes.filter(movie__media_type=media_type)
    return render(request, "movies/my_movies.html", {"votes": votes, "media_type": media_type})


def _filter_by_sublist(queryset, list_param):
    if list_param == "none":
        return queryset.filter(sublist__isnull=True)
    if list_param:
        return queryset.filter(sublist_id=list_param)
    return queryset


@login_required
def saved_movies(request):
    media_type = _media_type_from_request(request)
    list_param = request.GET.get("list", "")

    saved = SavedMovie.objects.filter(user=request.user).select_related("movie", "sublist").order_by("order", "-saved_at")
    if media_type != "all":
        saved = saved.filter(movie__media_type=media_type)
    saved = _filter_by_sublist(saved, list_param)

    return render(request, "movies/saved_movies.html", {
        "saved": saved, "media_type": media_type,
        "sublists": SavedMovieList.objects.filter(user=request.user),
        "list_param": list_param,
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
                messages.info(request, "Ya tenías una sublista con ese nombre.")
    return redirect("movies:saved-movies")


@login_required
def saved_list_delete(request, pk):
    sublist = get_object_or_404(SavedMovieList, pk=pk, user=request.user)
    if request.method == "POST":
        sublist.delete()
        messages.success(request, "Sublista borrada. Sus películas siguen guardadas, sin sublista.")
    return redirect("movies:saved-movies")


@login_required
def saved_movie_set_sublist(request, pk):
    saved = get_object_or_404(SavedMovie, pk=pk, user=request.user)
    if request.method == "POST":
        sublist_id = request.POST.get("sublist", "")
        saved.sublist = get_object_or_404(SavedMovieList, pk=sublist_id, user=request.user) if sublist_id else None
        saved.save(update_fields=["sublist"])
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

        if not candidates.exists():
            messages.warning(request, "Todavía no hay películas del catálogo en ese rango de nota.")
        elif not unseen.exists():
            messages.info(request, "Has agotado las películas de ese rango. Dale a «reiniciar» para verlas de nuevo.")
        else:
            result = random.choice(list(unseen))
            RouletteRatingSeen.objects.get_or_create(user=request.user, movie=result)
            reel = _build_reel(result, list(candidates))

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
    saved = _filter_by_sublist(SavedMovie.objects.filter(user=user).select_related("movie", "sublist"), list_param)
    seen_ids = set(RouletteSavedSeen.objects.filter(user=user).values_list("movie_id", flat=True))
    for item in saved:
        item.is_seen = item.movie_id in seen_ids
    return {
        "saved": saved, "unseen_count": sum(1 for item in saved if not item.is_seen),
        "sublists": SavedMovieList.objects.filter(user=user), "list_param": list_param,
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
            reel = _build_reel(result, [s.movie for s in saved])

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
