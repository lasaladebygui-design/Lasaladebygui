"""Campanita de la cabecera: agrega en un único sitio los avisos que ya
existían repartidos por la web (mensajes sin leer, solicitudes de amistad,
artículos nuevos que no has visto) más los avisos que publique el equipo
(Announcement) — sin duplicar ningún dato, cada cosa sigue viviendo donde
ya vivía, esto solo la reúne para enseñarla junta.

Abrir la campanita resetea el número entero de golpe (ver
`_after_last_seen` y `User.notifications_seen_at`): no hace falta entrar
uno a uno en cada aviso para que deje de contar.

`unread_notifications_count()` la llama `site_context` en CADA página (es
un context processor), así que sin caché cada navegación pagaba 5 consultas
`.count()` separadas solo para pintar el numerito de la campanita — mismo
problema que ya se documentó y resolvió para `SiteConfig.load()` en
`SingletonModel`, pero sin aplicárselo a esto. Se cachea con el mismo
patrón, por el mismo motivo (ver el docstring de `SingletonModel`): el
`cache.set` va detrás de `transaction.on_commit`, no en el momento de leer,
para que en los tests (TestCase envuelve cada test en una transacción que
se deshace al final) el `on_commit` nunca llegue a ejecutarse y por tanto
nunca quede nada cacheado de una prueba a la siguiente, ni dentro de la
misma prueba entre un `assertEqual` y el siguiente — sin este truco, los
tests que crean un mensaje/artículo/aviso y comprueban el contador varias
veces seguidas (sin pasar por `notifications_panel`) empezarían a fallar,
sirviendo un número cacheado de hace un instante en vez de recalcular."""

from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import Announcement, SiteConfig

RECENT_ARTICLES_DAYS = 30
RECENT_PRODUCTS_DAYS = 30
NOTIF_COUNT_CACHE_TTL = 20  # segundos


def _joined_cutoff(user, days):
    """El más reciente entre "hace X días" y "cuando te registraste" — así
    una cuenta nueva no ve como aviso algo publicado antes de que existiera
    (solo importa lo de después de darte de alta), y una cuenta antigua
    sigue sin ver avisos de hace más de X días."""
    recent_cutoff = timezone.now() - timedelta(days=days)
    return max(recent_cutoff, user.date_joined)


def _unseen_articles(user):
    from apps.articles.models import Article, ArticleView
    from apps.articles.permissions import can_manage_private_articles

    articles = Article.objects.exclude(
        pk__in=ArticleView.objects.filter(user=user).values("article_id")
    ).exclude(author=user)
    if not can_manage_private_articles(user):
        articles = articles.filter(is_private=False)
    return articles.filter(created_at__gte=_joined_cutoff(user, RECENT_ARTICLES_DAYS))


def _unseen_products(user):
    from apps.shop.models import Product, ProductView

    products = Product.objects.filter(is_visible=True).exclude(
        pk__in=ProductView.objects.filter(user=user).values("product_id")
    )
    return products.filter(created_at__gte=_joined_cutoff(user, RECENT_PRODUCTS_DAYS))


def _after_last_seen(queryset, user):
    """Además de "sin leer/sin visitar" tal cual ya se filtraba, ignora lo
    que ya existía la última vez que se abrió la campanita — así abrirla
    resetea el número entero de golpe, sin tener que entrar uno a uno en
    cada aviso para que deje de contar."""
    if user.notifications_seen_at:
        return queryset.filter(created_at__gt=user.notifications_seen_at)
    return queryset


def _notif_count_cache_key(user):
    return f"unread_notif_count:{user.pk}"


def invalidate_notifications_count(user):
    """Llamar justo después de tocar `notifications_seen_at` (o cualquier
    cosa que deba reflejarse ya, sin esperar al TTL) para que el próximo
    cálculo sea exacto en vez de servir el valor cacheado anterior."""
    cache.delete(_notif_count_cache_key(user))


def unread_notifications_count(user):
    if user is None or not user.is_authenticated:
        return 0
    if not SiteConfig.load().notifications_bell_enabled:
        return 0

    cache_key = _notif_count_cache_key(user)
    count = cache.get(cache_key)
    if count is not None:
        return count

    from apps.social.models import FriendRequest, Message

    count = 0
    count += _after_last_seen(Message.objects.filter(recipient=user, read_at__isnull=True), user).count()
    count += _after_last_seen(FriendRequest.objects.filter(to_user=user, accepted=False), user).count()
    count += Announcement.objects.exclude(read_by=user).filter(created_at__gte=user.date_joined).count()
    count += _after_last_seen(_unseen_articles(user), user).count()
    count += _after_last_seen(_unseen_products(user), user).count()
    transaction.on_commit(lambda: cache.set(cache_key, count, NOTIF_COUNT_CACHE_TTL))
    return count


def notifications_feed(user, limit_per_category=5):
    if user is None or not user.is_authenticated:
        return []
    if not SiteConfig.load().notifications_bell_enabled:
        return []

    from apps.social.models import FriendRequest, Message

    items = []

    unread_messages = (
        _after_last_seen(Message.objects.filter(recipient=user, read_at__isnull=True), user)
        .select_related("sender").order_by("-created_at")[:limit_per_category]
    )
    for msg in unread_messages:
        # Los mensajes de "Escríbenos" (`is_contact`) se avisan con un texto
        # distinto, pero son un `Message` normal (sender != recipient) —
        # llevan a su conversación real como cualquier otro, en vez de a
        # Social a secas.
        items.append({
            "kind": "message", "icon": "✉️" if msg.is_contact else "💬",
            "text": "Nuevo mensaje por «Escríbenos»" if msg.is_contact else f"{msg.sender} te ha escrito",
            "detail": msg.body[:80],
            "url": reverse("social:conversation", args=[msg.sender.username]),
            "created_at": msg.created_at,
        })

    pending_requests = (
        _after_last_seen(FriendRequest.objects.filter(to_user=user, accepted=False), user)
        .select_related("from_user").order_by("-created_at")[:limit_per_category]
    )
    for fr in pending_requests:
        items.append({
            "kind": "friend_request", "icon": "🧑‍🤝‍🧑",
            "text": f"{fr.from_user} quiere ser tu amigo",
            "detail": "",
            "url": reverse("social:friends"),
            "created_at": fr.created_at,
        })

    announcements = (
        Announcement.objects.exclude(read_by=user).filter(created_at__gte=user.date_joined)
        .order_by("-created_at")[:limit_per_category]
    )
    for ann in announcements:
        items.append({
            "kind": "announcement", "icon": "📣",
            "text": ann.title,
            "detail": ann.body[:80],
            "url": ann.url,
            "created_at": ann.created_at,
        })

    for article in _after_last_seen(_unseen_articles(user), user).order_by("-created_at")[:limit_per_category]:
        items.append({
            "kind": "article", "icon": "📰",
            "text": f"Nuevo artículo: {article.title}",
            "detail": "",
            "url": article.get_absolute_url(),
            "created_at": article.created_at,
        })

    for product in _after_last_seen(_unseen_products(user), user).order_by("-created_at")[:limit_per_category]:
        items.append({
            "kind": "product", "icon": "🛒",
            "text": f"Nuevo en la tienda: {product.name}",
            "detail": "",
            "url": reverse("shop:list"),
            "created_at": product.created_at,
        })

    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items
