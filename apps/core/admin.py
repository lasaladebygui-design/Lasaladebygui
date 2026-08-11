from django import forms
from django.contrib import admin
from django.shortcuts import redirect

from .models import Announcement, ContactLink, SiteConfig, Theme

COLOR_FIELDS = (
    "color_bg", "color_surface", "color_border",
    "color_text", "color_text_muted",
    "color_accent", "color_accent_hover", "color_on_accent",
    "color_accent_secondary", "color_accent_secondary_hover", "color_on_accent_secondary",
    "color_danger", "color_success",
    "color_intro_light", "color_intro_lamp", "color_intro_chair",
)

# Solo estas tipografías están cargadas de verdad en el sitio
# (templates/base.html, enlace a Google Fonts) — escribir un nombre a mano
# que no esté aquí no rompe nada, pero cae en la fuente del sistema sin que
# se note por qué. Un desplegable evita ese despiste.
FONT_FIELDS = ("font_heading", "font_body")
FONT_CHOICES = [
    ("'Playfair Display', Georgia, serif", "Playfair Display (elegante, serif)"),
    ("'Bebas Neue', Impact, sans-serif", "Bebas Neue (grande, tipo cartel)"),
    ("'Special Elite', 'Playfair Display', Georgia, serif", "Special Elite (máquina de escribir)"),
    ("'Inter', system-ui, -apple-system, sans-serif", "Inter (moderna, sans-serif)"),
    ("'Cinzel', Georgia, serif", "Cinzel (clásica, tipo épica/romana)"),
    ("'Oswald', Impact, sans-serif", "Oswald (condensada, titulares)"),
    ("'Cormorant Garamond', Georgia, serif", "Cormorant Garamond (fina, romántica)"),
    ("'Poppins', system-ui, -apple-system, sans-serif", "Poppins (geométrica, redondeada)"),
    ("'Abril Fatface', Georgia, serif", "Abril Fatface (cartel de cine, muy gruesa)"),
    ("'Creepster', 'Special Elite', cursive", "Creepster (terror, goteante)"),
    ("'Space Mono', monospace", "Space Mono (técnica, ciencia ficción)"),
    ("'Caveat', cursive", "Caveat (manuscrita, cercana)"),
    ("'Merriweather', Georgia, serif", "Merriweather (periódico, muy legible)"),
    ("'Righteous', sans-serif", "Righteous (redondeada, divertida)"),
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
    """Gestión de temas: crear/editar temas nuevos sin tocar código. El tema
    que se aplica a la web se elige en Sitio → Configuración del sitio.

    Todos los colores viven juntos en un único apartado, en cuadrícula (ver
    admin_theme_form.css) en vez de repartidos en muchos apartados pequeños
    — más cómodo para comparar/ajustar de un vistazo. (Hubo una vista previa
    en vivo por iframe aquí; se quitó porque Render no la dejaba cargar.)"""

    class Media:
        css = {"all": ("css/admin_theme_form.css",)}

    list_display = ("name", "order", "is_published", "is_dark", "color_accent", "color_accent_secondary")
    list_editable = ("order", "is_published")
    ordering = ("order", "name")
    actions = ["publish_themes", "unpublish_themes"]
    fieldsets = (
        (None, {"fields": ("name", "description", "order", "is_dark", "is_published")}),
        ("Colores", {
            "fields": (
                "color_bg", "color_surface", "color_border",
                "color_text", "color_text_muted",
                "color_accent", "color_accent_hover", "color_on_accent",
                "color_accent_secondary", "color_accent_secondary_hover", "color_on_accent_secondary",
                "color_danger", "color_success",
                "color_intro_light", "color_intro_lamp", "color_intro_chair",
            ),
            "classes": ("theme-color-grid",),
            "description": "Las tres últimas (luz, lámpara, sillón) son solo para la animación de inicio.",
        }),
        ("Tipografía y espaciado", {"fields": ("font_heading", "font_body", "space_unit", "radius_base")}),
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
        (None, {"fields": ("tagline",)}),
        ("Donaciones", {"fields": ("bizum_number",)}),
        ("Animación de entrada", {"fields": ("show_intro_animation", "intro_sound")}),
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


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    """Enviar un aviso ES publicarlo aquí: en cuanto se guarda, sale para
    todo el mundo en la campanita de la cabecera — no hace falta elegir
    destinatarios ni nada más. Para que llegue por email en vez de (o además
    de) esto, usa "Enviar un email" en el admin de usuarios."""

    list_display = ("title", "created_by", "created_at", "read_count")
    readonly_fields = ("created_at",)
    fields = ("title", "body", "url", "created_at")

    @admin.display(description="leído por")
    def read_count(self, obj):
        return obj.read_by.count()

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("created_by", request.user.pk)
        return initial

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
