from django.urls import path

from . import views

app_name = "social"

urlpatterns = [
    path("amigos/", views.friends_list, name="friends"),
    path("amigos/solicitud/<int:pk>/aceptar/", views.respond_friend_request, {"action": "accept"}, name="friend-request-accept"),
    path("amigos/solicitud/<int:pk>/rechazar/", views.respond_friend_request, {"action": "decline"}, name="friend-request-decline"),
    path("mensajes/", views.inbox, name="inbox"),
    path("mensajes/<str:username>/", views.conversation, name="conversation"),
    path("usuarios/<str:username>/", views.public_profile, name="public-profile"),
    path("usuarios/<str:username>/agregar/", views.send_friend_request, name="friend-request-send"),
    path("usuarios/<str:username>/quitar/", views.remove_friend, name="friend-remove"),
]
