from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"

urlpatterns = [
    path("registro/", views.register, name="register"),
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("perfil/", views.profile, name="profile"),
    path("perfil/logros/", views.achievements, name="achievements"),
    path("perfil/ajustes/", views.settings_page, name="settings"),
    path("perfil/ajustes/nombre-de-usuario/", views.change_username, name="change-username"),
    path("perfil/ajustes/animacion/", views.set_intro_animation, name="set-intro-animation"),
    path("perfil/ajustes/instalar-app/", views.toggle_pwa_prompt, name="toggle-pwa-prompt"),
    path("perfil/ajustes/avisos-articulos/", views.toggle_email_new_articles, name="toggle-email-new-articles"),
    path("perfil/favoritas/<str:category>/", views.favorites_page, name="favorites-page"),
    path("perfil/favoritas/<str:category>/<str:media_type>/buscar/", views.favorite_search, name="favorite-search"),
    path("perfil/favoritas/<str:category>/<str:media_type>/anadir/<int:tmdb_id>/", views.favorite_add, name="favorite-add"),
    path("perfil/favoritas/<int:pk>/quitar/", views.favorite_remove, name="favorite-remove"),
    path("perfil/favoritas/<int:pk>/mover/<str:direction>/", views.favorite_move, name="favorite-move"),
    path("perfil/favoritas/<str:category>/<str:media_type>/reordenar/", views.favorite_reorder, name="favorite-reorder"),
    path("perfil/favoritas/<str:category>/nota/", views.favorite_category_note, name="favorite-category-note"),
    path("notificaciones/suscribir/", views.push_subscribe, name="push-subscribe"),
    path("notificaciones/desuscribir/", views.push_unsubscribe, name="push-unsubscribe"),
    path("google-calendar/conectar/", views.google_calendar_connect, name="google-calendar-connect"),
    path("google-calendar/callback/", views.google_calendar_callback, name="google-calendar-callback"),
    path("google-calendar/desconectar/", views.google_calendar_disconnect, name="google-calendar-disconnect"),

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
    path(
        "perfil/ajustes/contrasena/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change_form.html",
            success_url=reverse_lazy("accounts:password-change-done"),
        ),
        name="password-change",
    ),
    path(
        "perfil/ajustes/contrasena/hecho/",
        auth_views.PasswordChangeDoneView.as_view(template_name="accounts/password_change_done.html"),
        name="password-change-done",
    ),
]
