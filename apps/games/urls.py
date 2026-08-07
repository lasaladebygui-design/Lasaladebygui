from django.urls import path

from . import views

app_name = "games"

urlpatterns = [
    path("", views.games_hub, name="hub"),
    path("frases/", views.quote_game, name="quote-game"),
    path("mejor-valorada/", views.rating_duel_game, name="rating-duel"),
    path("trivial/", views.trivia_game, name="trivia-game"),
    path("emoji/", views.emoji_game, name="emoji-game"),
    path("malas-descripciones/", views.bad_description_game, name="bad-description-game"),
    path("actor/", views.actor_game, name="actor-game"),
    path("verdadero-o-falso/", views.true_false_game, name="true-false-game"),
    path("que-personaje-eres/", views.personality_quiz, name="personality-quiz"),
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
    path("tierlist/niveles/anadir/", views.tier_level_create, name="tier-level-create"),
    path("tierlist/niveles/<int:pk>/editar/", views.tier_level_update, name="tier-level-update"),
    path("tierlist/niveles/<int:pk>/borrar/", views.tier_level_delete, name="tier-level-delete"),

    path("oscars/", views.oscar_home, name="oscars"),
    path("oscars/<int:category_id>/buscar/", views.oscar_candidate_search, name="oscar-candidate-search"),
    path("oscars/<int:category_id>/anadir/<int:tmdb_id>/", views.oscar_candidate_add, name="oscar-candidate-add"),
    path("oscars/<int:category_id>/anadir-persona/", views.oscar_candidate_add_person, name="oscar-candidate-add-person"),
    path("oscars/votar/<int:candidate_id>/", views.oscar_vote, name="oscar-vote"),
]
