import json

from django.contrib import admin
from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.urls import path

from apps.core.admin import SortableAdminMixin

from .models import (
    Duel, DuelRecord, GameTierEntry, GameTierLevel, MovieQuote, OscarCandidate, OscarCategory, OscarVote,
    PersonalityAnswer, PersonalityCharacter, PersonalityQuestion, QuoteCandidate, TriviaQuestion, TrueFalseStatement,
)


@admin.register(MovieQuote)
class MovieQuoteAdmin(admin.ModelAdmin):
    list_display = ("quote", "media_type", "correct_title")
    list_filter = ("media_type",)
    search_fields = ("quote", "correct_title")
    change_list_template = "admin/games/moviequote/change_list.html"


@admin.register(QuoteCandidate)
class QuoteCandidateAdmin(admin.ModelAdmin):
    """No se usa el listado normal: la propia página de listado ES el panel
    de curación (tarjeta por título, botones por frase candidata — nada que
    escribir). Elegir una opción crea el MovieQuote y marca la fila
    resuelta; "descartar" la marca skipped sin crear nada. Ver el diseño
    reutilizado de AdminMenuOrderAdmin (apps.core.admin) para esta misma
    técnica de "el changelist es una herramienta, no una tabla"."""

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        pending = self.model.objects.filter(resolved=False, skipped=False).order_by("-source_rating", "title")
        done_count = self.model.objects.filter(resolved=True).count()
        skipped_count = self.model.objects.filter(skipped=True).count()
        context = {
            **self.admin_site.each_context(request),
            "title": "Curar frases célebres",
            "pending": pending,
            "pending_count": pending.count(),
            "done_count": done_count,
            "skipped_count": skipped_count,
            "opts": self.model._meta,
        }
        if extra_context:
            context.update(extra_context)
        return TemplateResponse(request, "admin/games/quotecandidate/changelist.html", context)

    def get_urls(self):
        custom = [
            path("elegir/", self.admin_site.admin_view(self.choose_view), name="games_quotecandidate_choose"),
            path("descartar/", self.admin_site.admin_view(self.skip_view), name="games_quotecandidate_skip"),
        ]
        return custom + super().get_urls()

    def choose_view(self, request):
        if request.method != "POST":
            return JsonResponse({"error": "Solo POST"}, status=405)
        try:
            payload = json.loads(request.body)
            candidate_id = int(payload["candidate_id"])
            option_index = int(payload["option_index"])
        except (TypeError, ValueError, KeyError):
            return JsonResponse({"error": "Petición inválida"}, status=400)

        candidate = QuoteCandidate.objects.filter(pk=candidate_id, resolved=False, skipped=False).first()
        if candidate is None:
            return JsonResponse({"error": "Ya resuelta o no existe"}, status=404)
        try:
            option = candidate.options[option_index]
        except IndexError:
            return JsonResponse({"error": "Opción inválida"}, status=400)

        quote = MovieQuote.objects.create(
            quote=option["quote"], media_type=candidate.media_type,
            correct_title=candidate.title, wrong_title_1=option["wrong1"], wrong_title_2=option["wrong2"],
        )
        candidate.resolved = True
        candidate.chosen_quote = quote
        candidate.save(update_fields=["resolved", "chosen_quote"])
        return JsonResponse({"ok": True})

    def skip_view(self, request):
        if request.method != "POST":
            return JsonResponse({"error": "Solo POST"}, status=405)
        try:
            candidate_id = int(json.loads(request.body)["candidate_id"])
        except (TypeError, ValueError, KeyError):
            return JsonResponse({"error": "Petición inválida"}, status=400)
        updated = QuoteCandidate.objects.filter(pk=candidate_id, resolved=False).update(skipped=True)
        if not updated:
            return JsonResponse({"error": "No existe"}, status=404)
        return JsonResponse({"ok": True})


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
