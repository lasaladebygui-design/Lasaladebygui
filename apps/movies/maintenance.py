"""Actualización diaria del catálogo sin cron.

El plan gratuito de Render no tiene tareas programadas ni Shell, así que
la actualización (estrenos nuevos + renovar notas IMDb, ver el comando
`update_catalog`) se dispara desde las propias visitas: el middleware mira
como mucho cada CHECK_EVERY si toca (una vez cada RUN_EVERY, registrado en
`CatalogSync`) y, si toca, la lanza en un proceso aparte para no retrasar
la respuesta. Si nadie visita la web ese día no se actualiza, pero tampoco
hace falta: lo hará en la siguiente visita.
"""

import subprocess
import sys
import threading
import time
from datetime import timedelta

from django.conf import settings

RUN_EVERY = timedelta(hours=20)
CHECK_EVERY = 10 * 60  # segundos

_lock = threading.Lock()
_next_check_at = 0.0


def maybe_start_daily_update():
    global _next_check_at
    if not settings.CATALOG_AUTO_UPDATE:
        return
    now = time.monotonic()
    with _lock:
        if now < _next_check_at:
            return
        _next_check_at = now + CHECK_EVERY

    from .models import CatalogSync

    try:
        if not CatalogSync.claim_daily_run(RUN_EVERY):
            return
    except Exception:
        # Nunca romper una página por esto (p. ej. antes de aplicar la migración).
        return

    subprocess.Popen(
        [sys.executable, str(settings.BASE_DIR / "manage.py"), "update_catalog"],
        cwd=settings.BASE_DIR,
        start_new_session=True,
    )


class DailyCatalogUpdateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        maybe_start_daily_update()
        return self.get_response(request)
