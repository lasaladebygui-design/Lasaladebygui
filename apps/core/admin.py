from django import forms
from django.contrib import admin
from django.shortcuts import redirect

from .models import ContactLink, SiteConfig, Theme

COLOR_FIELDS = (
    "color_bg", "color_surface", "color_border",
    "color_text", "color_text_muted",
    "color_accent", "color_accent_hover", "color_on_accent",
    "color_accent_secondary", "color_accent_secondary_hover", "color_on_accent_secondary",
    "color_danger", "color_success",
)

# Solo estas cuatro tipografías están cargadas de verdad en el sitio
# (templates/base.html, enlace a Google Fonts) — escribir un nombre a mano
# que no esté aquí no rompe nada, pero cae en la fuente del sistema sin que
# se note por qué. Un desplegable evita ese despiste.
FONT_FIELDS = ("font_heading", "font_body")
FONT_CHOICES = [
    ("'Playfair Display', Georgia, serif", "Playfair Display (elegante, serif)"),
    ("'Bebas Neue', Impact, sans-serif", "Bebas Neue (grande, tipo cartel)"),
    ("'Special Elite', 'Playfair Display', Georgia, serif", "Special Elite (máquina de escribir)"),
    ("'Inter', system-ui, -apple-system, sans-serif", "Inter (moderna, sans-serif)"),
]


class ColorWidgetMixin:
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in COLOR_FIELDS:
            kwargs["widget"] = forms.TextInput(attrs={"type": "color"})
        elif db_field.name in FONT_FIELDS:
            kwargs["widget"] = forms.Select(choices=FONT_CHOICES)
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(Theme)
class ThemeAdmin(ColorWidgetMixin, admin.ModelAdmin):
    """Gestión de temas: crear/editar temas nuevos sin tocar código.
    El tema que se aplica a la web se elige en Sitio → Configuración del sitio.

    Al editar un tema se ve una vista previa en vivo (un iframe con una
    página de muestra aparte + `static/js/admin_theme_preview.js`, que va
    empujando cada cambio de campo como variable CSS dentro de ese iframe),
    para no tener que adivinar de memoria cómo queda una combinación de
    colores antes de guardar."""

    change_form_template = "admin/core/theme/change_form.html"

    class Media:
        js = ("js/admin_theme_preview.js",)

    list_display = ("name", "slug", "is_published", "is_dark", "color_accent", "color_accent_secondary")
    list_editable = ("is_published",)
    actions = ["publish_themes", "unpublish_themes"]
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "is_dark", "is_published")}),
        ("Fondo y superficies", {"fields": ("color_bg", "color_surface", "color_border")}),
        ("Texto", {"fields": ("color_text", "color_text_muted")}),
        ("Acento principal", {"fields": ("color_accent", "color_accent_hover", "color_on_accent")}),
        ("Acento secundario", {
            "fields": ("color_accent_secondary", "color_accent_secondary_hover", "color_on_accent_secondary"),
        }),
        ("Estados", {"fields": ("color_danger", "color_success")}),
        ("Tipografía", {"fields": ("font_heading", "font_body")}),
        ("Espaciados y forma", {"fields": ("space_unit", "radius_base")}),
    )

    @admin.action(description="👁️ Publicar (mostrar en el selector de temas)")
    def publish_themes(self, request, queryset):
        queryset.update(is_published=True)

    @admin.action(description="🙈 Despublicar (ocultar del selector de temas)")
    def unpublish_themes(self, request, queryset):
        queryset.update(is_published=False)


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


@admin.register(ContactLink)
class ContactLinkAdmin(admin.ModelAdmin):
    list_display = ("platform", "label", "url", "order")
    list_editable = ("order",)
    list_filter = ("platform",)
