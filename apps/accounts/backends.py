from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Permite autenticar usuarios inactivos (baneados) para que el
    formulario de login pueda mostrar el mensaje específico de baneo,
    en lugar del genérico "credenciales incorrectas" de Django."""

    def user_can_authenticate(self, user):
        return True
