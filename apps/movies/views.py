import json
import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MovieSearchForm, RatingRangeForm, VoteForm
from .models import Movie, RouletteCandidate, RouletteRatingSeen, SavedMovie, Vote
from .services import MovieAPIError, tmdb_search

SPIN_DECOYS = 5


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _build_reel(final_movie, decoy_pool):
    decoys = [m for m in decoy_pool if m.pk != final_movie.pk]
    random.shuffle(decoys)
    decoys = decoys[:SPIN_DECOYS] or [final_movie] * SPIN_DECOYS
    reel = decoys + [final_movie]
    return json.dumps([m.poster_url or "" for m in reel])


def _roulette_list_context(user):
    candidates = RouletteCandidate.objects.filter(user=user).select_related("movie")
    # Guardadas que todavía no están en la lista: para poder añadirlas a la
    # ruleta con un clic en vez de tener que volver a buscarlas.
    saved_available = SavedMovie.objects.filter(user=user).exclude(
        movie_id__in=candidates.values_list("movie_id", flat=True)
    ).select_related("movie")
    return {"candidates": candidates, "saved_available": saved_available}


# --- Catálogo y votación ----------------------------------------------------

def movie_list(request):
    form = MovieSearchForm(request.GET or None)
    movies = Movie.objects.all()
    query = ""
    external_results = []
    search_error = None

    if form.is_valid() and form.cleaned_data["query"]:
        query = form.cleaned_data["query"]
        movies = movies.filter(title__icontains=query)

        # El catálogo local solo tiene lo ya sembrado/visto antes: se
        # complementa con una búsqueda en vivo a TMDb para que cualquier
        # película que se busque aparezca, no solo las ya cacheadas.
        local_tmdb_ids = set(Movie.objects.values_list("tmdb_id", flat=True))
        try:
            tmdb_results = tmdb_search(query)
        except MovieAPIError as exc:
            search_error = str(exc)
        else:
            external_results = [r for r in tmdb_results if r.tmdb_id not in local_tmdb_ids][:12]

    paginator = Paginator(movies, 12)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "movies/list.html", {
        "page_obj": page,
        "form": form,
        "query": query,
        "external_results": external_results,
        "search_error": search_error,
    })


def movie_from_tmdb(request, tmdb_id):
    try:
        movie = Movie.get_or_create_from_tmdb(tmdb_id)
    except MovieAPIError as exc:
        messages.error(request, str(exc))
        return redirect("movies:list")
    return redirect("movies:detail", pk=movie.pk)


def movie_detail(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    user_vote = None
    is_saved = False
    is_candidate = False
    if request.user.is_authenticated:
        user_vote = Vote.objects.filter(movie=movie, user=request.user).first()
        is_saved = SavedMovie.objects.filter(movie=movie, user=request.user).exists()
        is_candidate = RouletteCandidate.objects.filter(movie=movie, user=request.user).exists()
    vote_form = VoteForm(initial={"score": user_vote.score if user_vote else None})
    return render(request, "movies/detail.html", {
        "movie": movie, "vote_form": vote_form, "user_vote": user_vote,
        "is_saved": is_saved, "is_candidate": is_candidate,
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
    votes = Vote.objects.filter(user=request.user).select_related("movie").order_by("-updated_at")
    saved = SavedMovie.objects.filter(user=request.user).select_related("movie")
    candidates = RouletteCandidate.objects.filter(user=request.user).select_related("movie")
    return render(request, "movies/my_movies.html", {"votes": votes, "saved": saved, "candidates": candidates})


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


# --- Ruleta Modo 2: lista personalizada -------------------------------------

@login_required
def roulette_list(request):
    search_form = MovieSearchForm()
    return render(request, "movies/roulette_list.html", {
        "search_form": search_form, **_roulette_list_context(request.user),
    })


@login_required
def roulette_list_search(request):
    query = request.GET.get("query", "").strip()
    results = []
    error = None
    if query:
        try:
            results = tmdb_search(query)[:8]
        except MovieAPIError as exc:
            error = str(exc)
    return render(request, "movies/_search_results.html", {
        "results": results, "error": error, "query": query,
    })


@login_required
def roulette_candidate_add(request, tmdb_id):
    if request.method == "POST":
        try:
            movie = Movie.get_or_create_from_tmdb(tmdb_id)
        except MovieAPIError as exc:
            messages.error(request, str(exc))
        else:
            RouletteCandidate.objects.get_or_create(user=request.user, movie=movie)

    if _is_htmx(request):
        return render(request, "movies/roulette_list_result.html", _roulette_list_context(request.user))
    return redirect("movies:roulette-list")


@login_required
def roulette_candidate_remove(request, pk):
    candidate = get_object_or_404(RouletteCandidate, pk=pk, user=request.user)
    if request.method == "POST":
        candidate.delete()

    if _is_htmx(request):
        return render(request, "movies/roulette_list_result.html", _roulette_list_context(request.user))
    return redirect("movies:roulette-list")


@login_required
def roulette_candidate_toggle(request, pk):
    """Añadir/quitar una película (del catálogo, no de una búsqueda TMDb en
    vivo) a la lista de la ruleta Modo 2. Se usa tanto desde la ficha de la
    película (redirige de vuelta) como desde la sección "tus guardadas" de
    la propia lista de la ruleta (HTMX, refresca el panel)."""
    movie = get_object_or_404(Movie, pk=pk)
    if request.method == "POST":
        candidate, created = RouletteCandidate.objects.get_or_create(user=request.user, movie=movie)
        if not created:
            candidate.delete()
            if not _is_htmx(request):
                messages.success(request, "Quitada de tu lista de la ruleta.")
        elif not _is_htmx(request):
            messages.success(request, "¡Añadida a tu lista de la ruleta!")

    if _is_htmx(request):
        return render(request, "movies/roulette_list_result.html", _roulette_list_context(request.user))
    return redirect("movies:detail", pk=movie.pk)


@login_required
def roulette_list_draw(request):
    result = None
    reel = None
    context = _roulette_list_context(request.user)
    candidates = context["candidates"]

    if request.method == "POST":
        unseen = list(candidates.filter(is_seen=False))
        if not candidates.exists():
            messages.warning(request, "Tu lista está vacía. Añade alguna película candidata primero.")
        elif not unseen:
            messages.info(request, "Has visto toda tu lista. Dale a «reiniciar» para volver a empezar.")
        else:
            chosen = random.choice(unseen)
            chosen.is_seen = True
            chosen.save(update_fields=["is_seen"])
            result = chosen.movie
            reel = _build_reel(result, [c.movie for c in candidates])

    return render(request, "movies/roulette_list_result.html", {
        **context, "result": result, "reel_json": reel,
    })


@login_required
def roulette_list_reset(request):
    if request.method == "POST":
        RouletteCandidate.objects.filter(user=request.user).update(is_seen=False)
        messages.success(request, "Lista reiniciada: todas tus candidatas vuelven a estar disponibles.")
    return redirect("movies:roulette-list")
