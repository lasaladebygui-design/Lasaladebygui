from django.conf import settings

from .models import SiteConfig, Theme, get_effective_theme


def site_context(request):
    return {
        "site_name": settings.SITE_NAME,
        "site_config": SiteConfig.load(),
        "site_theme": get_effective_theme(getattr(request, "user", None), getattr(request, "session", None)),
        "all_themes": Theme.objects.all(),
        "vapid_public_key": settings.VAPID_PUBLIC_KEY,
    }
