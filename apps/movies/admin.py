from django.contrib import admin

from .models import (
    CalendarDayNote,
    Movie,
    ReleaseEvent,
    ReleaseEventGoogleLink,
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
    list_display = ("user", "movie", "sublist", "saved_at")
    list_filter = ("sublist",)


@admin.register(SavedMovieList)
class SavedMovieListAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "order")
    search_fields = ("user__username", "name")


@admin.register(ReleaseEvent)
class ReleaseEventAdmin(admin.ModelAdmin):
    list_display = ("movie", "date", "note")
    list_filter = ("date",)
    search_fields = ("movie__title",)
    autocomplete_fields = ("movie",)
    ordering = ("date",)


@admin.register(ReleaseEventGoogleLink)
class ReleaseEventGoogleLinkAdmin(admin.ModelAdmin):
    list_display = ("release_event", "user", "google_event_id")
    search_fields = ("user__username", "release_event__movie__title")


@admin.register(CalendarDayNote)
class CalendarDayNoteAdmin(admin.ModelAdmin):
    list_display = ("date", "note")
    ordering = ("date",)
