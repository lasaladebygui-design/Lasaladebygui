from django.contrib import admin

from .models import Thread, ThreadComment, ThreadRead


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
    autocomplete_fields = ("thread", "author", "parent")
    date_hierarchy = "created_at"


@admin.register(ThreadRead)
class ThreadReadAdmin(admin.ModelAdmin):
    """Solo lectura: quién ha entrado a cada hilo — visible únicamente
    para el equipo desde aquí, no hay botón equivalente en el foro público."""

    list_display = ("thread", "user", "read_at")
    list_filter = ("thread",)
    search_fields = ("thread__title", "user__username", "user__email")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
