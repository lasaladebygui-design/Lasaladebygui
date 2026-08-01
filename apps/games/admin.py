from django.contrib import admin

from .models import Duel, DuelRecord, GameTierEntry, MovieQuote


@admin.register(MovieQuote)
class MovieQuoteAdmin(admin.ModelAdmin):
    list_display = ("quote", "correct_title")
    search_fields = ("quote", "correct_title")


@admin.register(Duel)
class DuelAdmin(admin.ModelAdmin):
    list_display = ("challenger", "opponent", "status", "challenger_streak", "opponent_streak", "created_at")
    list_filter = ("status",)
    search_fields = ("challenger__username", "opponent__username")


@admin.register(DuelRecord)
class DuelRecordAdmin(admin.ModelAdmin):
    list_display = ("player_low", "player_high", "player_low_wins", "player_high_wins", "draws")
    search_fields = ("player_low__username", "player_high__username")


@admin.register(GameTierEntry)
class GameTierEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "tier", "order")
    list_filter = ("tier",)
    search_fields = ("user__username", "movie__title")
