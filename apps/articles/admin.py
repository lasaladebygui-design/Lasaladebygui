from django import forms
from django.contrib import admin

from apps.core.admin import SortableAdminMixin

from .models import Article, ArticleComment, ArticleIdea, ArticleView, Tag


@admin.register(Tag)
class TagAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name",)
    list_display_links = ("name",)
    exclude = ("slug", "order")
    search_fields = ("name",)


class ArticleCommentInline(admin.TabularInline):
    model = ArticleComment
    extra = 0
    readonly_fields = ("author", "created_at")


class ImagePreviewWidget(forms.ClearableFileInput):
    """Como el ClearableFileInput de siempre, pero con una miniatura en
    vez de la ruta completa del archivo en texto — la ruta de Supabase
    es larga y no aporta nada al ver el formulario."""

    template_name = "admin/widgets/image_preview_clearable_file_input.html"


class ArticleAdminForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = "__all__"
        widgets = {"cover": ImagePreviewWidget}


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    form = ArticleAdminForm
    list_display = ("title", "author", "is_featured", "is_private", "created_at")
    list_editable = ("is_featured",)
    list_filter = ("is_featured", "is_private", "tags", "author")
    search_fields = ("title", "body")
    # Autocomplete en vez del widget de "listas disponibles / elegidas" de
    # filter_horizontal (dos columnas con flechas) — un buscador con
    # resultados en vivo es mucho más cómodo, para autor y para listas.
    autocomplete_fields = ("author", "tags")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ArticleCommentInline]
    actions = ["make_private", "make_public"]
    # Agrupados por lo que se toca a menudo (contenido, publicación) y lo
    # que casi nunca (fechas) — antes era una lista plana de campos, así
    # de un vistazo es más fácil ver qué es cada cosa.
    fieldsets = (
        (None, {"fields": ("title", "cover", "body")}),
        ("Publicación", {"fields": ("author", "tags", "is_featured", "is_private")}),
        ("Info", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_changeform_initial_data(self, request):
        # Al crear un artículo nuevo desde el admin, el autor eres tú por
        # defecto (quien ha iniciado sesión) — se puede cambiar a mano si
        # hace falta, gracias al autocomplete de arriba.
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("author", request.user.pk)
        return initial

    @admin.action(description="🔒 Marcar como privados (solo Gestor/Admin)")
    def make_private(self, request, queryset):
        queryset.update(is_private=True)

    @admin.action(description="🌐 Marcar como públicos")
    def make_public(self, request, queryset):
        queryset.update(is_private=False)


@admin.register(ArticleComment)
class ArticleCommentAdmin(admin.ModelAdmin):
    list_display = ("article", "author", "created_at")
    list_filter = ("created_at",)
    search_fields = ("body", "author__email")


@admin.register(ArticleIdea)
class ArticleIdeaAdmin(admin.ModelAdmin):
    """Cuaderno de ideas: un sitio para apuntar temas de futuros artículos
    sin tener que escribirlos ya — marcar "ya escrito" cuando se use."""

    list_display = ("text", "is_done", "created_by", "created_at")
    list_editable = ("is_done",)
    list_filter = ("is_done",)
    search_fields = ("text", "notes")
    fields = ("text", "notes", "is_done", "created_at")
    readonly_fields = ("created_at",)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("created_by", request.user.pk)
        return initial

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ArticleView)
class ArticleViewAdmin(admin.ModelAdmin):
    """Solo lectura: es un registro de quién ha leído qué, no algo que
    tenga sentido crear o editar a mano desde el admin."""

    list_display = ("article", "user", "viewed_at")
    list_filter = ("article",)
    search_fields = ("article__title", "user__username", "user__email")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
