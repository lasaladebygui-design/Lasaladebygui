from django.contrib import admin

from apps.core.admin import SortableAdminMixin

from .models import Product


@admin.register(Product)
class ProductAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name", "price")
    list_display_links = ("name",)
    search_fields = ("name",)
    ordering = ("order", "name")
    exclude = ("order",)
