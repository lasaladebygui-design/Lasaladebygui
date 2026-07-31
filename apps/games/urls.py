from django.urls import path

from . import views

app_name = "games"

urlpatterns = [
    path("", views.games_hub, name="hub"),
    path("frases/", views.quote_game, name="quote-game"),
    path("duelos/<str:username>/invitar/", views.duel_invite, name="duel-invite"),
    path("duelos/<int:pk>/", views.duel_detail, name="duel-detail"),
    path("duelos/<int:pk>/aceptar/", views.duel_accept, name="duel-accept"),
    path("duelos/<int:pk>/rechazar/", views.duel_decline, name="duel-decline"),
]
