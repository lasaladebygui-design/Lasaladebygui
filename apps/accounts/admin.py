from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import EmailVerificationToken, FavoriteMovie, PushSubscription, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Gestión de usuarios: listar, cambiar rol, banear/desbanear."""

    ordering = ("-date_joined",)
    list_display = (
        "email",
        "username",
        "role",
        "email_verified",
        "is_active",
        "date_joined",
    )
    list_editable = ("role",)
    list_filter = ("role", "is_active", "email_verified")
    search_fields = ("email", "username")
    readonly_fields = ("date_joined", "last_login")

    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name", "bio")}),
        ("Perfil público", {"fields": ("avatar",)}),
        ("Preferencias", {"fields": ("theme",)}),
        ("Rol y estado", {"fields": ("role", "email_verified", "is_active", "is_staff", "is_superuser")}),
        ("Permisos avanzados", {"fields": ("groups", "user_permissions"), "classes": ("collapse",)}),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "username", "role", "password1", "password2"),
        }),
    )

    actions = ["banear_usuarios", "desbanear_usuarios"]

    @admin.action(description="Banear usuarios seleccionados")
    def banear_usuarios(self, request, queryset):
        for user in queryset:
            user.role = User.Role.BANEADO
            user.save()
        self.message_user(request, f"{queryset.count()} usuario(s) baneado(s).")

    @admin.action(description="Desbanear usuarios seleccionados (pasan a Lector)")
    def desbanear_usuarios(self, request, queryset):
        for user in queryset.filter(role=User.Role.BANEADO):
            user.role = User.Role.LECTOR
            user.save()
        self.message_user(request, "Usuarios desbaneados.")


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "used_at")
    readonly_fields = ("token", "created_at")
    search_fields = ("user__email",)


@admin.register(FavoriteMovie)
class FavoriteMovieAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "movie", "order")
    list_filter = ("category",)
    search_fields = ("user__username", "movie__title")
    autocomplete_fields = ("movie",)


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("endpoint", "p256dh", "auth", "created_at")
