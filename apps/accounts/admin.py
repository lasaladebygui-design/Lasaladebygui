from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import path, reverse

from .forms import BroadcastEmailForm
from .models import EmailVerificationToken, FavoriteMovie, GoogleCalendarConnection, PushSubscription, User


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

    actions = ["banear_usuarios", "desbanear_usuarios", "enviar_email"]

    @admin.action(description="🚫 Banear a los seleccionados")
    def banear_usuarios(self, request, queryset):
        for user in queryset:
            user.role = User.Role.BANEADO
            user.save()
        self.message_user(request, f"{queryset.count()} usuario(s) baneado(s).")

    @admin.action(description="✅ Desbanear a los seleccionados (pasan a Lector)")
    def desbanear_usuarios(self, request, queryset):
        for user in queryset.filter(role=User.Role.BANEADO):
            user.role = User.Role.LECTOR
            user.save()
        self.message_user(request, "Usuarios desbaneados.")

    @admin.action(description="📧 Enviar un email a los seleccionados")
    def enviar_email(self, request, queryset):
        # "Enviar a todos" no necesita nada especial: el propio changelist ya
        # deja seleccionar "los N usuarios en todas las páginas" con el
        # filtro/búsqueda que tengas puesto, así que esta misma acción sirve
        # tanto para unos pocos concretos como para todos a la vez.
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        return redirect(f"{reverse('admin:accounts_user_send_email')}?ids={ids}")

    def get_urls(self):
        custom = [
            path(
                "enviar-email/",
                self.admin_site.admin_view(self.send_email_view),
                name="accounts_user_send_email",
            ),
        ]
        return custom + super().get_urls()

    def send_email_view(self, request):
        ids = (request.POST if request.method == "POST" else request.GET).get("ids", "")
        pks = [pk for pk in ids.split(",") if pk]
        recipients = User.objects.filter(pk__in=pks).exclude(email="").order_by("email")

        form = BroadcastEmailForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            for recipient in recipients:
                send_mail(
                    subject=form.cleaned_data["subject"],
                    message=form.cleaned_data["message"],
                    from_email=None,
                    recipient_list=[recipient.email],
                )
            self.message_user(request, f"Email enviado a {recipients.count()} usuario(s).")
            return redirect("admin:accounts_user_changelist")

        context = {
            **self.admin_site.each_context(request),
            "title": "Enviar email a usuarios",
            "form": form,
            "recipients": recipients,
            "ids": ids,
            "opts": self.model._meta,
        }
        return render(request, "admin/accounts/user/send_email.html", context)


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


@admin.register(GoogleCalendarConnection)
class GoogleCalendarConnectionAdmin(admin.ModelAdmin):
    list_display = ("user", "connected_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("refresh_token", "access_token", "access_token_expires_at", "connected_at")
