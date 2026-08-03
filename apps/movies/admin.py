from django.contrib import admin

from .models import (
    CalendarDayNote,
    Movie,
    ReleaseEvent,
    RouletteRatingSeen,
    RouletteSavedSeen,
    SavedMovie,
    SavedMovieList,
    Vote,
)


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ("title", "media_type", "year", "imdb_rating", "votes_count_display", "created_at")
    list_filter = ("media_type",)
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
class SavedMovieListAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "order")
    search_fields = ("user__username", "name")


@admin.register(ReleaseEvent)
class ReleaseEventAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "date", "note")
    list_filter = ("date",)
    search_fields = ("movie__title", "user__username")
    autocomplete_fields = ("movie",)
    ordering = ("date",)


@admin.register(CalendarDayNote)
class CalendarDayNoteAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "note")
    search_fields = ("user__username",)
    ordering = ("date",)
