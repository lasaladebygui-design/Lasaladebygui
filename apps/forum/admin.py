from django.contrib import admin

from .models import Thread, ThreadComment


class ThreadCommentInline(admin.TabularInline):
    model = ThreadComment
    extra = 0
    fields = ("author", "parent", "body", "is_deleted", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "is_locked", "created_at")
    list_editable = ("is_locked",)
    list_filter = ("is_locked",)
    search_fields = ("title", "body")
    autocomplete_fields = ("author",)
    inlines = [ThreadCommentInline]


@admin.register(ThreadComment)
class ThreadCommentAdmin(admin.ModelAdmin):
    list_display = ("thread", "author", "parent", "is_deleted", "created_at")
    list_filter = ("is_deleted",)
    search_fields = ("body", "author__email")
