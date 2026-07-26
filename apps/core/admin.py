from django import forms
from django.contrib import admin
from django.shortcuts import redirect

from .models import SiteConfig, Theme

COLOR_FIELDS = (
    "color_bg", "color_surface", "color_border",
    "color_text", "color_text_muted",
    "color_accent", "color_accent_hover", "color_on_accent",
    "color_accent_secondary", "color_accent_secondary_hover", "color_on_accent_secondary",
    "color_danger", "color_success",
)


class ColorWidgetMixin:
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in COLOR_FIELDS:
            kwargs["widget"] = forms.TextInput(attrs={"type": "color"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(Theme)
class ThemeAdmin(ColorWidgetMixin, admin.ModelAdmin):
    """Gestión de temas: crear/editar temas nuevos sin tocar código.
    El tema que se aplica a la web se elige en Sitio → Configuración del sitio."""

    list_display = ("name", "slug", "is_dark", "color_accent", "color_accent_secondary")
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "is_dark")}),
        ("Fondo y superficies", {"fields": ("color_bg", "color_surface", "color_border")}),
        ("Texto", {"fields": ("color_text", "color_text_muted")}),
        ("Acento principal", {"fields": ("color_accent", "color_accent_hover", "color_on_accent")}),
        ("Acento secundario", {
            "fields": ("color_accent_secondary", "color_accent_secondary_hover", "color_on_accent_secondary"),
        }),
        ("Estados", {"fields": ("color_danger", "color_success")}),
        ("Tipografía", {"fields": ("font_heading", "font_body")}),
        ("Espaciados y forma", {"fields": ("space_unit", "radius_base", "max_content_width")}),
    )


class SingletonAdmin(admin.ModelAdmin):
    """Evita listados/duplicados: siempre se edita la única fila existente."""

    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = self.model.load()
        return redirect("admin:%s_%s_change" % (self.model._meta.app_label, self.model._meta.model_name), obj.pk)


@admin.register(SiteConfig)
class SiteConfigAdmin(SingletonAdmin):
    fieldsets = (
        (None, {"fields": ("tagline", "contact_email", "require_email_verification")}),
        ("Donaciones", {"fields": ("bizum_number",)}),
        ("Animación de entrada", {"fields": ("show_intro_animation",)}),
        ("Tema visual", {
            "fields": ("active_theme",),
            "description": "El tema elegido aquí se aplica a toda la web, salvo que un usuario elija otro distinto en su perfil.",
        }),
    )
