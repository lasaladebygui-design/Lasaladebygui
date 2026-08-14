from django import forms
from django.contrib import admin

from apps.core.admin import SingletonAdmin, SortableAdminMixin

from .forms import SecretMovieForm
from .models import (
    CalendarDayNote,
    Genre,
    PhotoBoardMember,
    ReleaseEvent,
    SecretMovie,
    SecretPhoto,
    TierLevel,
    TierListEntry,
    TopSecretConfig,
)


class TopSecretConfigForm(forms.ModelForm):
    new_code = forms.CharField(
        label="Nuevo código de acceso",
        required=False,
        help_text=(
            "El código actual está hasheado y no se puede consultar. "
            "Déjalo vacío para no cambiarlo."
        ),
    )

    class Meta:
        model = TopSecretConfig
        fields = [
            "rating_good_threshold", "rating_mid_threshold",
            "color_rating_good", "color_rating_mid", "color_rating_bad",
        ]
        widgets = {
            "color_rating_good": forms.TextInput(attrs={"type": "color"}),
            "color_rating_mid": forms.TextInput(attrs={"type": "color"}),
            "color_rating_bad": forms.TextInput(attrs={"type": "color"}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_code = self.cleaned_data.get("new_code")
        if new_code:
            instance.set_code(new_code)
        if commit:
            instance.save()
        return instance


@admin.register(TopSecretConfig)
class TopSecretConfigAdmin(SingletonAdmin):
    form = TopSecretConfigForm
    fieldsets = (
        (None, {"fields": ("new_code",)}),
        ("Colores de la lista completa según nota", {
            "fields": (
                "rating_good_threshold", "color_rating_good",
                "rating_mid_threshold", "color_rating_mid",
                "color_rating_bad",
            ),
            "description": "Por debajo de la nota media, el color siempre es el de \"nota baja\".",
        }),
    )


@admin.register(Genre)
class GenreAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name", "admin_only")
    list_display_links = ("name",)
    list_editable = ("admin_only",)
    list_filter = ("admin_only",)
    exclude = ("slug", "order")
    search_fields = ("name",)


@admin.register(SecretMovie)
class SecretMovieAdmin(admin.ModelAdmin):
    form = SecretMovieForm
    list_display = ("number", "title", "personal_rating", "rating_verdict", "tie_break", "genre_list")
    list_filter = ("rating_verdict",)
    search_fields = ("title",)
    autocomplete_fields = ("movie",)
    ordering = ("number",)

    @admin.display(description="listas")
    def genre_list(self, obj):
        return ", ".join(obj.genres.values_list("name", flat=True))


@admin.register(SecretPhoto)
class SecretPhotoAdmin(admin.ModelAdmin):
    list_display = ("description", "board_owner", "uploaded_by", "created_at")
    list_filter = ("board_owner",)
    search_fields = ("description", "board_owner__username", "uploaded_by__username")
    autocomplete_fields = ("board_owner", "uploaded_by")


@admin.register(PhotoBoardMember)
class PhotoBoardMemberAdmin(admin.ModelAdmin):
    list_display = ("owner", "member", "invited_at")
    search_fields = ("owner__username", "member__username")
    autocomplete_fields = ("owner", "member")


@admin.register(TierLevel)
class TierLevelAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "color", "order")
    list_editable = ("color", "order")
    list_filter = ("user",)
    ordering = ("user_id", "order")


@admin.register(TierListEntry)
class TierListEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "tier", "order")
    list_display_links = ("title",)
    list_editable = ("tier", "order")
    list_filter = ("user", "tier")
    search_fields = ("title",)
    autocomplete_fields = ("movie",)
    ordering = ("user_id", "tier__order", "order")


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
