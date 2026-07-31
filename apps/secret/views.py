import random
from functools import wraps

from django.contrib import messages
from django.db.models import Max
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.movies.models import Movie
from apps.movies.services import MovieAPIError, tmdb_search

from .forms import CodeForm, NumberSelectForm, RatingSearchForm, SecretPhotoForm, TierLevelForm
from .models import Genre, SecretMovie, SecretPhoto, TierLevel, TierListEntry, TopSecretConfig

SESSION_KEY = "top_secret_unlocked"


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
    movies = SecretMovie.objects.prefetch_related("genres").all()
    return render(request, "secret/list.html", {"movies": movies})


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
