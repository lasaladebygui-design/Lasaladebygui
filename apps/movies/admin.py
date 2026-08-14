from django.contrib import admin

from apps.core.admin import SortableAdminMixin

from .models import (
    Movie,
    RouletteRatingSeen,
    RouletteSavedSeen,
    SavedMovie,
    SavedMovieList,
    Vote,
)
from .services import MovieAPIError, tmdb_search


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ("title", "media_type", "year", "imdb_rating", "votes_count_display", "created_at")
    list_filter = ("media_type",)
    search_fields = ("title", "tmdb_id", "imdb_id")
    readonly_fields = ("tmdb_id", "imdb_id", "created_at")

    @admin.display(description="votos")
    def votes_count_display(self, obj):
        return obj.votes_count

    def get_search_results(self, request, queryset, search_term):
        """El autocompletar (usado p. ej. al enlazar la "portada" de una
        película secreta o de un tier list) solo buscaba en el catálogo ya
        importado — si nadie había buscado antes ese título en "Cine", no
        salía. Si la búsqueda local no encuentra nada, se trae de TMDb
        (películas y series) y se cachea localmente antes de repetir la
        búsqueda, igual que hace el buscador de "Cine"."""
        results, use_distinct = super().get_search_results(request, queryset, search_term)
        term = search_term.strip()
        if term and not results.exists():
            self._import_from_tmdb(term)
            results, use_distinct = super().get_search_results(request, self.get_queryset(request), search_term)
        return results, use_distinct

    def _import_from_tmdb(self, term):
        for media_type in (Movie.MediaType.MOVIE, Movie.MediaType.TV):
            try:
                found = tmdb_search(term, media_type=media_type)
            except MovieAPIError:
                continue
            for item in found[:10]:
                Movie.objects.get_or_create(
                    tmdb_id=item.tmdb_id, media_type=media_type,
                    defaults={
                        "title": item.title, "year": item.year,
                        "poster_path": item.poster_path, "overview": item.overview,
                    },
                )


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("movie", "user", "score", "updated_at")
    list_filter = ("score",)
    search_fields = ("movie__title", "user__email")


@admin.register(RouletteRatingSeen)
class RouletteRatingSeenAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "seen_at")


@admin.register(RouletteSavedSeen)
class RouletteSavedSeenAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "seen_at")


@admin.register(SavedMovie)
class SavedMovieAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "saved_at")
    list_filter = ("sublists",)
    filter_horizontal = ("sublists",)


@admin.register(SavedMovieList)
class SavedMovieListAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("user", "name")
    list_display_links = ("name",)
    list_filter = ("user",)
    exclude = ("order",)
    search_fields = ("user__username", "name")
    ordering = ("user_id", "order")
