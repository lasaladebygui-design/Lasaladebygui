from django.urls import path

from . import views

app_name = "movies"

urlpatterns = [
    path("", views.movie_list, name="list"),
    path("<int:pk>/", views.movie_detail, name="detail"),
    path("<int:pk>/votar/", views.movie_vote, name="vote"),

    path("ruleta/", views.roulette_home, name="roulette-home"),

    path("ruleta/nota/", views.roulette_rating, name="roulette-rating"),
    path("ruleta/nota/reiniciar/", views.roulette_rating_reset, name="roulette-rating-reset"),

    path("ruleta/lista/", views.roulette_list, name="roulette-list"),
    path("ruleta/lista/buscar/", views.roulette_list_search, name="roulette-list-search"),
    path("ruleta/lista/anadir/<int:tmdb_id>/", views.roulette_candidate_add, name="roulette-candidate-add"),
    path("ruleta/lista/quitar/<int:pk>/", views.roulette_candidate_remove, name="roulette-candidate-remove"),
    path("ruleta/lista/girar/", views.roulette_list_draw, name="roulette-list-draw"),
    path("ruleta/lista/reiniciar/", views.roulette_list_reset, name="roulette-list-reset"),
]
