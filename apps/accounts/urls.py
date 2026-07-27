from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"

urlpatterns = [
    path("registro/", views.register, name="register"),
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("perfil/", views.profile, name="profile"),
    path("verificar/<uuid:token>/", views.verify_email, name="verify-email"),
    path("verificar/reenviar/", views.resend_verification, name="resend-verification"),

    path(
        "password/reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/email/password_reset_email.txt",
            subject_template_name="accounts/email/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password-reset-done"),
        ),
        name="password-reset",
    ),
    path(
        "password/reset/enviado/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password-reset-done",
    ),
    path(
        "password/reset/confirmar/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password-reset-complete"),
        ),
        name="password-reset-confirm",
    ),
    path(
        "password/reset/completado/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password-reset-complete",
    ),
]
