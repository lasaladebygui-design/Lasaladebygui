"""Envío de notificaciones push (Web Push estándar, con claves VAPID) a los
dispositivos suscritos de un usuario. Si no hay claves VAPID configuradas
(VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY vacías), esto no hace nada — el sitio
sigue funcionando con normalidad, solo no llegan notificaciones."""

from django.conf import settings

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - pywebpush siempre está en requirements.txt
    webpush = None
    WebPushException = Exception


def push_enabled():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY and webpush)


def send_push_to_user(user, title, body, url="/"):
    """Manda un push a todos los dispositivos suscritos de `user`. Si algún
    endpoint ya no es válido (el usuario desinstaló/revocó permiso), se
    borra esa suscripción en vez de dejarla ahí fallando para siempre."""
    if not push_enabled():
        return

    import json

    for subscription in user.push_subscriptions.all():
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=json.dumps({"title": title, "body": body, "url": url}),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{settings.VAPID_CONTACT_EMAIL}"},
            )
        except WebPushException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in (404, 410):
                subscription.delete()


def send_push_to_users(users, title, body, url="/"):
    for user in users:
        send_push_to_user(user, title, body, url)
