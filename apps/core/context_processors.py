from django.conf import settings

from .models import SiteConfig, Theme, get_effective_theme
from .notifications import unread_notifications_count


def site_context(request):
    site_config = SiteConfig.load()
    user = getattr(request, "user", None)
    show_intro_animation = site_config.show_intro_animation
    if user is not None and user.is_authenticated and user.show_intro_animation is not None:
        show_intro_animation = user.show_intro_animation

    return {
        "site_name": settings.SITE_NAME,
        "site_config": site_config,
        "site_theme": get_effective_theme(user, getattr(request, "session", None)),
        "all_themes": Theme.objects.filter(is_published=True),
        "vapid_public_key": settings.VAPID_PUBLIC_KEY,
        "show_intro_animation": show_intro_animation,
        "unread_notifications_count": unread_notifications_count(user),
    }
