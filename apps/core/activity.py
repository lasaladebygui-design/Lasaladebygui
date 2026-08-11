"""Actividad reciente de la portada: últimos comentarios de Artículos y del
Foro, mezclados y ordenados por fecha — un vistazo rápido a qué se está
diciendo en la web, sin tener que entrar en cada apartado. Desactivable
entera desde el admin (SiteConfig.recent_activity_enabled)."""

from .models import SiteConfig


def recent_activity(user, limit=8):
    if not SiteConfig.load().recent_activity_enabled:
        return []

    from apps.articles.models import ArticleComment
    from apps.articles.permissions import can_manage_private_articles
    from apps.forum.models import ThreadComment

    items = []

    article_comments = ArticleComment.objects.select_related("author", "article").order_by("-created_at")
    if not can_manage_private_articles(user):
        article_comments = article_comments.exclude(article__is_private=True)
    for comment in article_comments[:limit]:
        items.append({
            "kind": "article_comment", "icon": "📰",
            "author": comment.author, "body": comment.body,
            "context": comment.article.title,
            "url": f"{comment.article.get_absolute_url()}#comment-{comment.pk}",
            "created_at": comment.created_at,
        })

    thread_comments = (
        ThreadComment.objects.filter(is_deleted=False)
        .select_related("author", "thread").order_by("-created_at")
    )
    for comment in thread_comments[:limit]:
        items.append({
            "kind": "thread_comment", "icon": "💬",
            "author": comment.author, "body": comment.body,
            "context": comment.thread.title,
            "url": f"{comment.thread.get_absolute_url()}#comment-{comment.pk}",
            "created_at": comment.created_at,
        })

    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items[:limit]
