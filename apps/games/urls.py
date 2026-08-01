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
    path("duelos/<int:pk>/salir/", views.duel_leave, name="duel-leave"),

    path("tierlist/", views.tier_list, name="tier-list"),
    path("tierlist/buscar/", views.tier_list_search, name="tier-list-search"),
    path("tierlist/anadir/<int:tmdb_id>/", views.tier_list_add, name="tier-list-add"),
    path("tierlist/<int:pk>/mover/", views.tier_list_move, name="tier-list-move"),
    path("tierlist/reiniciar/", views.tier_list_reset, name="tier-list-reset"),
]
