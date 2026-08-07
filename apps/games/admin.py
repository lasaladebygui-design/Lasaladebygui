from django.contrib import admin

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
class PersonalityCharacterAdmin(admin.ModelAdmin):
    list_display = ("name", "source", "order")
    search_fields = ("name", "source")


class PersonalityAnswerInline(admin.TabularInline):
    model = PersonalityAnswer
    extra = 1
    autocomplete_fields = ("character",)


@admin.register(PersonalityQuestion)
class PersonalityQuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "order")
    inlines = [PersonalityAnswerInline]


@admin.register(OscarCategory)
class OscarCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "candidate_type", "is_open", "order")
    list_editable = ("is_open", "order")
    list_filter = ("candidate_type",)


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


@admin.register(Duel)
class DuelAdmin(admin.ModelAdmin):
    list_display = ("challenger", "opponent", "game", "status", "challenger_streak", "opponent_streak", "created_at")
    list_filter = ("game", "status")
    search_fields = ("challenger__username", "opponent__username")


@admin.register(DuelRecord)
class DuelRecordAdmin(admin.ModelAdmin):
    list_display = ("player_low", "player_high", "player_low_wins", "player_high_wins", "draws")
    search_fields = ("player_low__username", "player_high__username")


@admin.register(GameTierLevel)
class GameTierLevelAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "color", "order")
    search_fields = ("user__username", "name")


@admin.register(GameTierEntry)
class GameTierEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "tier", "order")
    list_filter = ("tier",)
    search_fields = ("user__username", "movie__title")
    autocomplete_fields = ("movie",)
