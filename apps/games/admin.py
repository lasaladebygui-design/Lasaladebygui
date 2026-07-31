from django.contrib import admin

from .models import Duel, MovieQuote


@admin.register(MovieQuote)
class MovieQuoteAdmin(admin.ModelAdmin):
    list_display = ("quote", "correct_title")
    search_fields = ("quote", "correct_title")


@admin.register(Duel)
class DuelAdmin(admin.ModelAdmin):
    list_display = ("challenger", "opponent", "status", "challenger_streak", "opponent_streak", "created_at")
    list_filter = ("status",)
    search_fields = ("challenger__username", "opponent__username")
