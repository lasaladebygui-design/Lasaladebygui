from django.conf import settings as django_settings


class AdminMenuOrderMiddleware:
    """Aplica el orden del menú lateral guardado a mano (AdminMenuOrder) por
    encima del orden de fábrica, antes de cada petición al admin. Jazzmin
    relee JAZZMIN_SETTINGS desde `django.conf.settings` en cada render (sin
    caché — ver jazzmin/settings.py:get_settings), así que basta con
    sobrescribir la clave en el dict ya vivo para que el sidebar cambie."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/"):
            from .models import AdminMenuOrder

            order = AdminMenuOrder.load().order
            if order:
                django_settings.JAZZMIN_SETTINGS["order_with_respect_to"] = order
            else:
                django_settings.JAZZMIN_SETTINGS["order_with_respect_to"] = django_settings.DEFAULT_ADMIN_MENU_ORDER
        return self.get_response(request)
