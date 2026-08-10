from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("avisos/", views.notifications_panel, name="notifications-panel"),
    path("donaciones/", views.donations, name="donations"),
    path("contacto/", views.contact, name="contact"),
    path("tema/reset/", views.reset_theme, name="reset-theme"),
    path("tema/<slug:slug>/", views.set_theme, name="set-theme"),
]
