from django import forms
from django.contrib import admin

from apps.core.admin import SingletonAdmin, SortableAdminMixin

from .forms import SecretMovieForm
from .models import (
    CalendarDayNote,
    Genre,
    PhotoBoardMember,
    RatingColorBand,
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
        fields = []

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_code = self.cleaned_data.get("new_code")
        if new_code:
            instance.set_code(new_code)
        if commit:
            instance.save()
        return instance


class RatingColorBandInline(admin.TabularInline):
    """Tantos tramos de nota→color como se quiera (no solo "bueno/medio/
    malo" fijo) — p. ej. "1 a 4: rojo", "4.1 a 7: naranja", "7.1 a 10: verde",
    o cualquier otro reparto. El primer tramo cuyo rango incluya la nota es
    el que se usa (ver TopSecretConfig.rating_color)."""

    model = RatingColorBand
    extra = 1
    fields = ("min_rating", "max_rating", "color", "order")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "color":
            kwargs["widget"] = forms.TextInput(attrs={"type": "color"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(TopSecretConfig)
class TopSecretConfigAdmin(SingletonAdmin):
    form = TopSecretConfigForm
    inlines = [RatingColorBandInline]
    fieldsets = (
        (None, {"fields": ("new_code",)}),
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
    list_display = ("number", "title", "personal_rating", "tie_break", "genre_list")
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
