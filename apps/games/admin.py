from django.contrib import admin

from apps.core.admin import SortableAdminMixin

from .models import (
    Duel, DuelRecord, GameTierEntry, GameTierLevel, MovieQuote, OscarCandidate, OscarCategory, OscarVote,
    PersonalityAnswer, PersonalityCharacter, PersonalityQuestion, TriviaQuestion, TrueFalseStatement,
)


@admin.register(MovieQuote)
class MovieQuoteAdmin(admin.ModelAdmin):
    list_display = ("quote", "media_type", "correct_title")
    list_filter = ("media_type",)
    search_fields = ("quote", "correct_title")


@admin.register(TriviaQuestion)
class TriviaQuestionAdmin(admin.ModelAdmin):
    list_display = ("prompt", "category", "media_type", "correct_answer")
    list_filter = ("category", "media_type")
    search_fields = ("prompt", "correct_answer")


@admin.register(TrueFalseStatement)
class TrueFalseStatementAdmin(admin.ModelAdmin):
    list_display = ("statement", "is_true")
    list_filter = ("is_true",)
    search_fields = ("statement",)


@admin.register(PersonalityCharacter)
class PersonalityCharacterAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name", "source")
    list_display_links = ("name",)
    search_fields = ("name", "source")
    exclude = ("order",)


class PersonalityAnswerInline(admin.TabularInline):
    model = PersonalityAnswer
    extra = 1
    autocomplete_fields = ("character",)


@admin.register(PersonalityQuestion)
class PersonalityQuestionAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("text",)
    list_display_links = ("text",)
    inlines = [PersonalityAnswerInline]
    exclude = ("order",)


@admin.register(OscarCategory)
class OscarCategoryAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name", "candidate_type", "is_open")
    list_display_links = ("name",)
    list_editable = ("is_open",)
    list_filter = ("candidate_type",)
    exclude = ("order",)
    actions = ["open_categories", "close_categories"]

    @admin.action(description="🔓 Abrir a candidaturas y votos")
    def open_categories(self, request, queryset):
        queryset.update(is_open=True)

    @admin.action(description="🔒 Cerrar a candidaturas y votos")
    def close_categories(self, request, queryset):
        queryset.update(is_open=False)


@admin.register(OscarCandidate)
class OscarCandidateAdmin(admin.ModelAdmin):
    list_display = ("display_title", "category", "submitted_by", "created_at")
    list_filter = ("category",)
    search_fields = ("movie__title", "person_name")
    autocomplete_fields = ("movie",)


@admin.register(OscarVote)
class OscarVoteAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "candidate")
    list_filter = ("category",)
    search_fields = ("user__username",)
    autocomplete_fields = ("user",)


@admin.register(Duel)
class DuelAdmin(admin.ModelAdmin):
    list_display = ("challenger", "opponent", "game", "status", "challenger_streak", "opponent_streak", "created_at")
    list_filter = ("game", "status")
    search_fields = ("challenger__username", "opponent__username")
    autocomplete_fields = ("challenger", "opponent")
    date_hierarchy = "created_at"


@admin.register(DuelRecord)
class DuelRecordAdmin(admin.ModelAdmin):
    list_display = ("player_low", "player_high", "player_low_wins", "player_high_wins", "draws")
    search_fields = ("player_low__username", "player_high__username")
    autocomplete_fields = ("player_low", "player_high")


@admin.register(GameTierLevel)
class GameTierLevelAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "color", "order")
    search_fields = ("user__username", "name")
    autocomplete_fields = ("user",)


@admin.register(GameTierEntry)
class GameTierEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "tier", "order")
    list_filter = ("tier",)
    search_fields = ("user__username", "movie__title")
    autocomplete_fields = ("user", "movie")
