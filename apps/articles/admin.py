from django.contrib import admin

from .models import Article, ArticleComment, ArticleView, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


class ArticleCommentInline(admin.TabularInline):
    model = ArticleComment
    extra = 0
    readonly_fields = ("author", "created_at")


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "is_private", "created_at", "updated_at")
    list_filter = ("is_private", "tags", "author")
    search_fields = ("title", "body")
    autocomplete_fields = ("author",)
    filter_horizontal = ("tags",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [ArticleCommentInline]


@admin.register(ArticleComment)
class ArticleCommentAdmin(admin.ModelAdmin):
    list_display = ("article", "author", "created_at")
    list_filter = ("created_at",)
    search_fields = ("body", "author__email")


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
