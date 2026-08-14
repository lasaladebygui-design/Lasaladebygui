import json

from django import forms
from django.apps import apps as django_apps
from django.conf import settings as django_settings
from django.contrib import admin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.safestring import mark_safe
from django.utils.text import slugify

from .models import AdminMenuOrder, Announcement, ContactLink, FavoriteQuote, PersonalNote, SiteConfig, Theme


class SortableAdminMixin:
    """Arrastra las filas del listado para cambiar su orden, en vez de
    editar el número de `order` a mano — para modelos con ordering global
    (no repartido por usuario, eso ya se arrastra desde su propia página).
    Añade una columna con un tirador (⠿) al principio del listado; al
    soltar una fila se manda el nuevo orden completo por fetch."""

    class Media:
        js = (
            "https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js",
            "admin/js/sortable_admin.js",
        )

    def get_list_display(self, request):
        list_display = list(super().get_list_display(request))
        if "drag_handle" not in list_display:
            list_display.insert(0, "drag_handle")
        return list_display

    @admin.display(description="")
    def drag_handle(self, obj):
        return mark_safe('<span class="drag-handle" title="Arrastra para reordenar">⠿</span>')

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path(
                "reordenar/",
                self.admin_site.admin_view(self.reorder_view),
                name="%s_%s_reorder" % info,
            ),
        ]
        return custom + super().get_urls()

    def reorder_view(self, request):
        if request.method != "POST":
            return JsonResponse({"error": "Solo POST"}, status=405)
        try:
            ids = json.loads(request.body).get("order", [])
        except (TypeError, ValueError):
            return JsonResponse({"error": "JSON inválido"}, status=400)

        objects = {obj.pk: obj for obj in self.model.objects.filter(pk__in=ids)}
        updated = []
        for position, pk in enumerate(ids):
            obj = objects.get(pk)
            if obj is not None:
                obj.order = position
                updated.append(obj)
        if updated:
            self.model.objects.bulk_update(updated, ["order"])
        return JsonResponse({"ok": True})


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
class ThemeAdmin(SortableAdminMixin, ColorWidgetMixin, admin.ModelAdmin):
    """Gestión de temas: crear/editar temas nuevos sin tocar código. El tema
    que se aplica a la web se elige en Sitio → Configuración del sitio.

    Todos los colores viven juntos en un único apartado, en cuadrícula (ver
    admin_theme_form.css) en vez de repartidos en muchos apartados pequeños
    — más cómodo para comparar/ajustar de un vistazo. (Hubo una vista previa
    en vivo por iframe aquí; se quitó porque Render no la dejaba cargar.)"""

    class Media:
        css = {"all": ("css/admin_theme_form.css",)}
        js = (
            "https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js",
            "admin/js/sortable_admin.js",
        )

    list_display = ("name", "is_published", "is_dark", "color_accent", "color_accent_secondary")
    list_display_links = ("name",)
    list_editable = ("is_published",)
    ordering = ("order", "name")
    actions = ["publish_themes", "unpublish_themes"]
    fieldsets = (
        (None, {"fields": ("name", "description", "is_dark", "is_published")}),
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
        ("Campanita de avisos", {
            "fields": ("notifications_bell_enabled",),
            "description": "Cubre mensajes, solicitudes de amistad, artículos nuevos, avisos del equipo y novedades de la tienda.",
        }),
        ("Actividad reciente", {"fields": ("recent_activity_enabled",)}),
        ("Animación de entrada", {"fields": ("show_intro_animation", "intro_sound")}),
        ("Tema visual", {
            "fields": ("active_theme",),
            "description": "El tema elegido aquí se aplica a toda la web, salvo que un usuario elija otro distinto en su perfil.",
        }),
    )


@admin.register(ContactLink)
class ContactLinkAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("platform", "label", "url")
    list_display_links = ("platform",)
    list_filter = ("platform",)
    exclude = ("order",)


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


@admin.register(FavoriteQuote)
class FavoriteQuoteAdmin(admin.ModelAdmin):
    list_display = ("short_text", "source", "created_at")
    search_fields = ("text", "source", "notes")
    fields = ("text", "source", "notes", "created_at")
    readonly_fields = ("created_at",)

    @admin.display(description="frase")
    def short_text(self, obj):
        return obj.text[:80]


@admin.register(PersonalNote)
class PersonalNoteAdmin(admin.ModelAdmin):
    list_display = ("title", "updated_at")
    search_fields = ("title", "body")
    readonly_fields = ("created_at", "updated_at")
    fields = ("title", "body", "created_at", "updated_at")


def _app_display_name(app_label):
    try:
        return str(django_apps.get_app_config(app_label).verbose_name)
    except LookupError:
        return app_label


def _model_display_name(token):
    app_label, model_name = token.split(".", 1)
    try:
        return django_apps.get_model(app_label, model_name)._meta.verbose_name.title()
    except LookupError:
        return token


def _default_sections():
    """Punto de partida al abrir la página de arrastre por primera vez
    (nada guardado aún): una sección por app, tal como las agrupa Django
    de fábrica, usando DEFAULT_ADMIN_MENU_ORDER para el orden inicial."""
    sections = []
    current = None
    for token in django_settings.DEFAULT_ADMIN_MENU_ORDER:
        if "." not in token:
            current = {"name": _app_display_name(token), "items": []}
            sections.append(current)
        elif current is not None:
            current["items"].append(token)
    return sections


def _valid_sections_payload(sections):
    if not isinstance(sections, list):
        return False
    for section in sections:
        if not isinstance(section, dict):
            return False
        if not isinstance(section.get("name"), str) or not section["name"].strip():
            return False
        items = section.get("items")
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            return False
    return True


@admin.register(AdminMenuOrder)
class AdminMenuOrderAdmin(admin.ModelAdmin):
    """Arrastrar para decidir el orden Y el agrupado del menú lateral —a
    diferencia del agrupado nativo de Django (por app real), aquí un
    modelo se puede mover a la sección que se quiera con solo arrastrarlo,
    gracias a que get_app_list() (parcheado más abajo) reconstruye el
    menú a partir de estas secciones en vez de por app_label."""

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = self.model.load()
        sections = obj.sections or _default_sections()
        view_sections = [
            {
                "name": section["name"],
                "models": [
                    {"token": token, "name": _model_display_name(token)}
                    for token in section["items"]
                ],
            }
            for section in sections
        ]
        context = {
            **self.admin_site.each_context(request),
            "title": "Orden del menú del admin",
            "sections": view_sections,
            "opts": self.model._meta,
        }
        if extra_context:
            context.update(extra_context)
        return TemplateResponse(request, "admin/core/adminmenuorder/changelist.html", context)

    def get_urls(self):
        custom = [
            path(
                "guardar/",
                self.admin_site.admin_view(self.save_sections_view),
                name="core_adminmenuorder_save",
            ),
        ]
        return custom + super().get_urls()

    def save_sections_view(self, request):
        if request.method != "POST":
            return JsonResponse({"error": "Solo POST"}, status=405)
        try:
            sections = json.loads(request.body).get("sections", [])
        except (TypeError, ValueError):
            return JsonResponse({"error": "JSON inválido"}, status=400)
        if not _valid_sections_payload(sections):
            return JsonResponse({"error": "Formato inválido"}, status=400)

        obj = self.model.load()
        obj.sections = sections
        obj.save()
        return JsonResponse({"ok": True})


_original_get_app_list = admin.site.__class__.get_app_list


def get_app_list(request, app_label=None):
    """Sustituye el agrupado nativo de Django (por app real) por las
    secciones guardadas en AdminMenuOrder — así un modelo se puede mover
    de verdad a otra sección, no solo reordenar dentro de la suya.
    Jazzmin arma el menú lateral leyendo esto de `available_apps` en el
    contexto (ver AdminSite.each_context → get_app_list), así que
    cambiarlo aquí basta para que el menú real cambie, sin tocar nada de
    Jazzmin. Con `app_label` (la página de listado de una sola app) se
    deja el comportamiento nativo intacto: esa vista no depende de esto.
    Los permisos los sigue calculando Django tal cual (_build_app_dict),
    esto solo decide en qué "cajón" visual cae cada modelo ya permitido."""
    if app_label:
        return _original_get_app_list(admin.site, request, app_label)

    app_dict = admin.site._build_app_dict(request)
    sections = AdminMenuOrder.load().sections
    if not sections:
        app_list = sorted(app_dict.values(), key=lambda x: x["name"].lower())
        for app in app_list:
            app["models"].sort(key=lambda x: x["name"])
        return app_list

    flat_models = {}
    for label, app in app_dict.items():
        for model_dict in app["models"]:
            flat_models[f"{label}.{model_dict['object_name']}".lower()] = (label, model_dict)

    used = set()
    result = []
    for index, section in enumerate(sections):
        models = []
        for token in section.get("items", []):
            key = token.lower()
            if "." in key:
                if key in flat_models and key not in used:
                    _, model_dict = flat_models[key]
                    models.append(model_dict)
                    used.add(key)
            else:
                app = app_dict.get(key)
                if app:
                    for model_dict in app["models"]:
                        model_key = f"{key}.{model_dict['object_name']}".lower()
                        if model_key not in used:
                            models.append(model_dict)
                            used.add(model_key)
        if models:
            name = section.get("name") or "Sin nombre"
            result.append({
                "name": name,
                "app_label": f"section-{slugify(name) or 'sin-nombre'}-{index}",
                "app_url": "#",
                "has_module_perms": True,
                "models": models,
            })

    # Modelos con permiso que no estén en ninguna sección guardada (apps
    # nuevas desde la última vez que se organizó el menú, típicamente) —
    # se añaden al final agrupados por su app real, para que nunca
    # desaparezcan del menú sin más.
    leftovers = {}
    for label, app in app_dict.items():
        for model_dict in app["models"]:
            key = f"{label}.{model_dict['object_name']}".lower()
            if key not in used:
                leftovers.setdefault(label, {"name": app["name"], "models": []})["models"].append(model_dict)
    for label, info in leftovers.items():
        result.append({
            "name": info["name"],
            "app_label": label,
            "app_url": "#",
            "has_module_perms": True,
            "models": info["models"],
        })

    return result


admin.site.get_app_list = get_app_list
