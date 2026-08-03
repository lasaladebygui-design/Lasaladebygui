from django.urls import path

from . import views

app_name = "movies"

urlpatterns = [
    path("", views.movie_list, name="list"),
    path("mias/", views.my_movies, name="my-movies"),
    path("guardadas/", views.saved_movies, name="saved-movies"),
    path("guardadas/<int:pk>/mover/<str:direction>/", views.saved_movie_move, name="saved-movie-move"),
    path("guardadas/<int:pk>/sublista/<int:list_id>/", views.saved_movie_toggle_sublist, name="saved-movie-toggle-sublist"),
    path("guardadas/listas/anadir/", views.saved_list_create, name="saved-list-create"),
    path("guardadas/listas/<int:pk>/borrar/", views.saved_list_delete, name="saved-list-delete"),
    path("desde-tmdb/<str:media_type>/<int:tmdb_id>/", views.movie_from_tmdb, name="from-tmdb"),

    path("<int:pk>/", views.movie_detail, name="detail"),
    path("<int:pk>/votar/", views.movie_vote, name="vote"),
    path("<int:pk>/votar/quitar/", views.movie_vote_remove, name="vote-remove"),
    path("<int:pk>/guardar/", views.movie_save_toggle, name="save-toggle"),

    path("ruleta/", views.roulette_home, name="roulette-home"),

    path("ruleta/nota/", views.roulette_rating, name="roulette-rating"),
    path("ruleta/nota/reiniciar/", views.roulette_rating_reset, name="roulette-rating-reset"),

    path("ruleta/lista/", views.roulette_list, name="roulette-list"),
    path("ruleta/lista/girar/", views.roulette_list_draw, name="roulette-list-draw"),
    path("ruleta/lista/reiniciar/", views.roulette_list_reset, name="roulette-list-reset"),
]
