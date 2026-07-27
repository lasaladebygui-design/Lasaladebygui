from django.contrib import admin

from .models import Movie, RouletteCandidate, RouletteRatingSeen, SavedMovie, Vote


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ("title", "year", "imdb_rating", "votes_count_display", "created_at")
    search_fields = ("title", "tmdb_id", "imdb_id")
    readonly_fields = ("tmdb_id", "imdb_id", "created_at")

    @admin.display(description="votos")
    def votes_count_display(self, obj):
        return obj.votes_count


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("movie", "user", "score", "updated_at")
    list_filter = ("score",)
    search_fields = ("movie__title", "user__email")


@admin.register(RouletteCandidate)
class RouletteCandidateAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "is_seen", "added_at")
    list_filter = ("is_seen",)


@admin.register(RouletteRatingSeen)
class RouletteRatingSeenAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "seen_at")


@admin.register(SavedMovie)
class SavedMovieAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "saved_at")
