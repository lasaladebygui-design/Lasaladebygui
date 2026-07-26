from django.contrib import admin

from .models import Article, ArticleComment, Tag


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
    list_display = ("title", "author", "created_at", "updated_at")
    list_filter = ("tags", "author")
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
