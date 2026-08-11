"""Campanita de la cabecera: agrega en un único sitio los avisos que ya
existían repartidos por la web (mensajes sin leer, solicitudes de amistad,
artículos nuevos que no has visto) más los avisos que publique el equipo
(Announcement) — sin duplicar ningún dato, cada cosa sigue viviendo donde
ya vivía, esto solo la reúne para enseñarla junta."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .models import Announcement, SiteConfig

RECENT_ARTICLES_DAYS = 30
RECENT_PRODUCTS_DAYS = 30


def _unseen_articles(user):
    from apps.articles.models import Article, ArticleView
    from apps.articles.permissions import can_manage_private_articles

    articles = Article.objects.exclude(
        pk__in=ArticleView.objects.filter(user=user).values("article_id")
    ).exclude(author=user)
    if not can_manage_private_articles(user):
        articles = articles.filter(is_private=False)
    cutoff = timezone.now() - timedelta(days=RECENT_ARTICLES_DAYS)
    return articles.filter(created_at__gte=cutoff)


def _recent_products():
    # La tienda no tiene "visto/no visto" por usuario como los artículos
    # (no hay carrito ni cuenta de por medio para eso): se avisa de
    # cualquier artículo añadido en los últimos RECENT_PRODUCTS_DAYS días.
    from apps.shop.models import Product

    cutoff = timezone.now() - timedelta(days=RECENT_PRODUCTS_DAYS)
    return Product.objects.filter(created_at__gte=cutoff)


def unread_notifications_count(user):
    if user is None or not user.is_authenticated:
        return 0
    if not SiteConfig.load().notifications_bell_enabled:
        return 0

    from apps.social.models import FriendRequest, Message

    count = 0
    count += Message.objects.filter(recipient=user, read_at__isnull=True).count()
    count += FriendRequest.objects.filter(to_user=user, accepted=False).count()
    count += Announcement.objects.exclude(read_by=user).count()
    count += _unseen_articles(user).count()
    count += _recent_products().count()
    return count


def notifications_feed(user, limit_per_category=5):
    if user is None or not user.is_authenticated:
        return []
    if not SiteConfig.load().notifications_bell_enabled:
        return []

    from apps.social.models import FriendRequest, Message

    items = []

    unread_messages = (
        Message.objects.filter(recipient=user, read_at__isnull=True)
        .select_related("sender").order_by("-created_at")[:limit_per_category]
    )
    for msg in unread_messages:
        # Los mensajes de "Escríbenos" se autoenvían (sender == recipient,
        # ya que quien escribe no tiene por qué tener cuenta) — se avisan
        # con un texto distinto para que no diga que te has escrito a ti.
        is_contact_message = msg.sender_id == msg.recipient_id
        items.append({
            "kind": "message", "icon": "✉️" if is_contact_message else "💬",
            "text": "Nuevo mensaje por «Escríbenos»" if is_contact_message else f"{msg.sender} te ha escrito",
            "detail": msg.body[:80],
            "url": reverse("social:home") if is_contact_message else reverse("social:conversation", args=[msg.sender.username]),
            "created_at": msg.created_at,
        })

    pending_requests = (
        FriendRequest.objects.filter(to_user=user, accepted=False)
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

    announcements = Announcement.objects.exclude(read_by=user).order_by("-created_at")[:limit_per_category]
    for ann in announcements:
        items.append({
            "kind": "announcement", "icon": "📣",
            "text": ann.title,
            "detail": ann.body[:80],
            "url": ann.url,
            "created_at": ann.created_at,
        })

    for article in _unseen_articles(user).order_by("-created_at")[:limit_per_category]:
        items.append({
            "kind": "article", "icon": "📰",
            "text": f"Nuevo artículo: {article.title}",
            "detail": "",
            "url": article.get_absolute_url(),
            "created_at": article.created_at,
        })

    for product in _recent_products().order_by("-created_at")[:limit_per_category]:
        items.append({
            "kind": "product", "icon": "🛒",
            "text": f"Nuevo en la tienda: {product.name}",
            "detail": "",
            "url": reverse("shop:list"),
            "created_at": product.created_at,
        })

    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items
