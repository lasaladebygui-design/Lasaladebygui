from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("registro/", views.register, name="register"),
    path("login/", views.EmailLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("perfil/", views.profile, name="profile"),
    path("verificar/<uuid:token>/", views.verify_email, name="verify-email"),
    path("verificar/reenviar/", views.resend_verification, name="resend-verification"),
]
