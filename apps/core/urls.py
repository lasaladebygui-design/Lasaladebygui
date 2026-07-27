from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("donaciones/", views.donations, name="donations"),
    path("contacto/", views.contact, name="contact"),
    path("tema/reset/", views.reset_theme, name="reset-theme"),
    path("tema/<slug:slug>/", views.set_theme, name="set-theme"),
    path("juegos/", views.games_hub, name="games"),
    path("juegos/frases/", views.quote_game, name="quote-game"),
]
