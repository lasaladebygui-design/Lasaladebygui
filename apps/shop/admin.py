from django.contrib import admin

from apps.core.admin import SortableAdminMixin

from .models import Product


@admin.register(Product)
class ProductAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ("name", "price", "is_visible")
    list_display_links = ("name",)
    list_editable = ("is_visible",)
    list_filter = ("is_visible",)
    search_fields = ("name",)
    ordering = ("order", "name")
    exclude = ("order",)
    actions = ["show_products", "hide_products"]

    @admin.action(description="👁️ Mostrar en la tienda")
    def show_products(self, request, queryset):
        queryset.update(is_visible=True)

    @admin.action(description="🙈 Ocultar de la tienda")
    def hide_products(self, request, queryset):
        queryset.update(is_visible=False)
