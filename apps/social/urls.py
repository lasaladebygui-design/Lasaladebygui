from django.urls import path

from apps.accounts.views import favorites_page

from . import views

app_name = "social"

urlpatterns = [
    path("", views.social_home, name="home"),
    path("amigos/", views.friends_list, name="friends"),
    path("amigos/solicitud/<int:pk>/aceptar/", views.respond_friend_request, {"action": "accept"}, name="friend-request-accept"),
    path("amigos/solicitud/<int:pk>/rechazar/", views.respond_friend_request, {"action": "decline"}, name="friend-request-decline"),
    path("amigos/solicitud/<int:pk>/retirar/", views.withdraw_friend_request, name="friend-request-withdraw"),
    path("mensajes/<str:username>/", views.conversation, name="conversation"),
    path("mensajes/<int:pk>/editar/", views.message_edit, name="message-edit"),
    path("mensajes/<int:pk>/borrar/", views.message_delete, name="message-delete"),
    path("usuarios/<str:username>/", views.public_profile, name="public-profile"),
    path("usuarios/<str:username>/favoritas/<str:category>/", favorites_page, name="public-favorites-page"),
    path("usuarios/<str:username>/agregar/", views.send_friend_request, name="friend-request-send"),
    path("usuarios/<str:username>/quitar/", views.remove_friend, name="friend-remove"),
]
