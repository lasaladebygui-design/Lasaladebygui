from django.utils import timezone

SESSION_REFRESHED_ON_KEY = "_refreshed_on"


class DailySessionRefreshMiddleware:
    """Mantiene la sesión larga (SESSION_COOKIE_AGE, un año) viva mientras
    se siga usando la web, igual que hacía SESSION_SAVE_EVERY_REQUEST, pero
    reescribiéndola en la base de datos como mucho una vez al día en vez de
    en cada petición (antes eran tres viajes a Supabase -- BEGIN, UPDATE,
    COMMIT -- en casi todas las cargas de página).

    Marca la fecha del día en la propia sesión: el primer uso de cada día
    la deja modificada, y SessionMiddleware la guarda y renueva la cookie y
    su caducidad de un año. Cualquier otro cambio real en la sesión se sigue
    guardando al momento, como siempre. Solo toca sesiones que ya tienen
    algo dentro: una vacía no se guardaba antes y tampoco ahora.

    Va DESPUÉS de SessionMiddleware en settings.MIDDLEWARE, para que su
    parte de respuesta se ejecute antes que la de SessionMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        session = getattr(request, "session", None)
        # Solo si la petición ya ha leído la sesión (todas las páginas lo
        # hacen, para saber quién eres): así no se fuerza una lectura extra
        # en las que no la necesitan.
        if session is not None and session.accessed and session.session_key:
            today = timezone.localdate().isoformat()
            has_data = any(key != SESSION_REFRESHED_ON_KEY for key in session.keys())
            if has_data and session.get(SESSION_REFRESHED_ON_KEY) != today:
                session[SESSION_REFRESHED_ON_KEY] = today
        return response
