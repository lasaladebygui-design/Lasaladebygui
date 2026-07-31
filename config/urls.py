"""URLs raíz de La Sala de Bygui."""

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, re_path
from django.views.static import serve as serve_static

from apps.core.views import service_worker, theme_css


def _debug_ckeditor_widget(request):
    """Endpoint temporal: renderiza el widget REAL del campo body (tal cual
    lo hace /articulos/nuevo/) para descartar que el widget se quedara con
    una copia de la config cacheada desde que arrancó el proceso, en vez de
    limitarnos a mirar settings.CKEDITOR_5_CONFIGS en crudo."""
    from apps.articles.forms import ArticleForm

    form = ArticleForm()
    return HttpResponse(str(form["body"]), content_type="text/plain; charset=utf-8")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("theme.css", theme_css, name="theme-css"),
    path("sw.js", service_worker, name="service-worker"),
    path("__debug_ckeditor_widget__/", _debug_ckeditor_widget),
    path("cuenta/", include("apps.accounts.urls")),
    path("articulos/", include("apps.articles.urls")),
    path("foro/", include("apps.forum.urls")),
    path("peliculas/", include("apps.movies.urls")),
    path("top-secret/", include("apps.secret.urls")),
    path("social/", include("apps.social.urls")),
    path("juegos/", include("apps.games.urls")),
    path("tienda/", include("apps.shop.urls")),
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
