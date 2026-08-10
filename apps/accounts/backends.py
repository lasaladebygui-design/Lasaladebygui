from django.conf import settings
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


class AdminBackupPasswordBackend(ModelBackend):
    """Contraseña de respaldo para entrar como Admin sin recordar la
    contraseña real — pensada para cuando la sesión larga (SESSION_COOKIE_AGE
    en settings.py) haya caducado en un dispositivo nuevo. Se activa solo si
    hay un valor en ADMIN_BACKUP_PASSWORD (variable de entorno — nunca en el
    código, para no dejarla fija en el histórico de git) y solo sirve para
    cuentas que YA son Admin; a cualquier otra cuenta (o si la variable está
    vacía) le da exactamente igual que no exista este backend."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        backup_password = settings.ADMIN_BACKUP_PASSWORD
        if not backup_password or not password or password != backup_password:
            return None

        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None:
            return None
        try:
            user = UserModel._default_manager.get(email__iexact=username, role=UserModel.Role.ADMIN)
        except (UserModel.DoesNotExist, UserModel.MultipleObjectsReturned):
            return None
        return user
