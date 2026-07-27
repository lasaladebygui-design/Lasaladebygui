from django import forms
from django.contrib import admin

from apps.core.admin import SingletonAdmin

from .models import MovieQuote, SecretMovie, TopSecretConfig


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


@admin.register(TopSecretConfig)
class TopSecretConfigAdmin(SingletonAdmin):
    form = TopSecretConfigForm
    fieldsets = ((None, {"fields": ("new_code",)}),)


@admin.register(SecretMovie)
class SecretMovieAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "personal_rating")
    search_fields = ("title",)
    autocomplete_fields = ("movie",)
    ordering = ("number",)


@admin.register(MovieQuote)
class MovieQuoteAdmin(admin.ModelAdmin):
    list_display = ("quote", "correct_title")
    search_fields = ("quote", "correct_title")
