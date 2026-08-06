from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Permite autenticar usuarios inactivos (baneados) para que el
    formulario de login pueda mostrar el mensaje específico de baneo,
    en lugar del genérico "credenciales incorrectas" de Django.

    También hace el email insensible a mayúsculas/minúsculas al iniciar
    sesión: el `ModelBackend` normal de Django busca por igualdad exacta
    (`email=...`), así que "Usuario@Gmail.com" no encontraba la cuenta
    guardada como "usuario@gmail.com"."""

    def user_can_authenticate(self, user):
        return True

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None
        try:
            user = UserModel._default_manager.get(email__iexact=username)
        except UserModel.DoesNotExist:
            # Sigue haciendo el hash de la contraseña igual, para que medir
            # cuánto tarda la respuesta no sirva para averiguar si un email
            # existe o no (mismo motivo que el ModelBackend original).
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
