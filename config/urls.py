"""URLs raíz de La Sala de Bygui."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as serve_static

from apps.core.views import theme_css

urlpatterns = [
    path("admin/", admin.site.urls),
    path("theme.css", theme_css, name="theme-css"),
    path("cuenta/", include("apps.accounts.urls")),
    path("articulos/", include("apps.articles.urls")),
    path("foro/", include("apps.forum.urls")),
    path("peliculas/", include("apps.movies.urls")),
    path("top-secret/", include("apps.secret.urls")),
    path("social/", include("apps.social.urls")),
    path("ckeditor5/", include("django_ckeditor_5.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Django's `static()` helper (usado arriba solo para STATIC_URL en local) es un
# no-op si DEBUG=False, así que en producción no bastaría para servir MEDIA_URL:
# whitenoise solo sirve STATIC_ROOT, no hay ningún backend de almacenamiento
# externo configurado (ver README, sección de despliegue) y sin esta ruta las
# imágenes subidas (avatares, portadas, fotos del tablón) devolvían 404 tanto
# en local como en Render. No es lo ideal para un sitio de tráfico alto, pero
# es la opción más simple mientras no haya S3/Cloudinary de por medio.
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve_static, {"document_root": settings.MEDIA_ROOT}),
]
