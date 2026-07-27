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
    path("dentro/tierlist/", views.tier_list, name="tier-list"),
    path("dentro/tablon/", views.photo_board, name="photo-board"),
]
