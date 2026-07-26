"""URLs raíz de La Sala de Bygui."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core.views import theme_css

urlpatterns = [
    path("admin/", admin.site.urls),
    path("theme.css", theme_css, name="theme-css"),
    path("cuenta/", include("apps.accounts.urls")),
    path("articulos/", include("apps.articles.urls")),
    path("foro/", include("apps.forum.urls")),
    path("peliculas/", include("apps.movies.urls")),
    path("top-secret/", include("apps.secret.urls")),
    path("ckeditor5/", include("django_ckeditor_5.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
