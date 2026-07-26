from django.urls import path

from . import views

app_name = "forum"

urlpatterns = [
    path("", views.thread_list, name="list"),
    path("nuevo/", views.thread_create, name="create"),
    path("<int:pk>/", views.thread_detail, name="detail"),
    path("<int:pk>/cerrar/", views.thread_toggle_lock, name="toggle-lock"),
    path("<int:pk>/eliminar/", views.thread_delete, name="delete"),
    path("comentario/<int:pk>/eliminar/", views.comment_delete, name="comment-delete"),
]
