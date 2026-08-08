from django.urls import path

from . import views

app_name = "articles"

urlpatterns = [
    path("", views.article_list, name="list"),
    path("nuevo/", views.article_create, name="create"),
    path("borrar-varios/", views.article_bulk_delete, name="bulk-delete"),
    path("<slug:slug>/", views.article_detail, name="detail"),
    path("<slug:slug>/editar/", views.article_update, name="update"),
    path("<slug:slug>/eliminar/", views.article_delete, name="delete"),
]
