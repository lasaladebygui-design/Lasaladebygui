from django.urls import path

from . import views

app_name = "secret"

urlpatterns = [
    path("", views.gate, name="gate"),
    path("cerrar/", views.lock, name="lock"),
    path("dentro/", views.home, name="home"),
    path("dentro/numero/", views.by_number, name="by-number"),
    path("dentro/nota/", views.by_rating, name="by-rating"),
    path("dentro/lista/", views.full_list, name="list"),
    path("dentro/otros/", views.other, name="other"),
    path("dentro/tierlist/", views.tier_list, name="tier-list"),
    path("dentro/tierlist/buscar/", views.tier_list_search, name="tier-list-search"),
    path("dentro/tierlist/anadir/<int:tmdb_id>/", views.tier_list_add, name="tier-list-add"),
    path("dentro/tierlist/<int:pk>/mover/", views.tier_list_move, name="tier-list-move"),
    path("dentro/tierlist/reiniciar/", views.tier_list_reset, name="tier-list-reset"),
    path("dentro/tierlist/niveles/anadir/", views.tier_level_create, name="tier-level-create"),
    path("dentro/tierlist/niveles/<int:pk>/editar/", views.tier_level_update, name="tier-level-update"),
    path("dentro/tierlist/niveles/<int:pk>/borrar/", views.tier_level_delete, name="tier-level-delete"),
    path("dentro/tablon/", views.photo_board, name="photo-board"),
]
