"""Helpers para STORAGES en config/settings.py, separados para poder
probarlos sin tener que recargar el módulo de settings."""

from urllib.parse import urlparse

from whitenoise.storage import CompressedManifestStaticFilesStorage


class LenientManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Igual que el storage con manifiesto de whitenoise (nombre de archivo
    con hash del contenido -> WhiteNoise le pone caché de un año, que es lo
    que de verdad hace notar la recarga entre página y página) pero sin
    reventar si una referencia dentro de un CSS/JS no se puede resolver.

    django-jazzmin referencia "vendor/bootswatch" como prefijo de ruta (no
    un archivo real), y el manifiesto estricto de Django lo trata como un
    archivo que falta y lanza ValueError. `manifest_strict = False` hace que
    esa referencia concreta se deje tal cual en vez de romper el collectstatic
    entero — el resto de archivos sí se hashean y cachean a largo plazo."""

    manifest_strict = False


def supabase_public_domain(endpoint_url, bucket_name):
    """Dominio (+ ruta) para servir archivos públicos de un bucket de
    Supabase Storage, a partir de su endpoint S3-compatible.

    Marcar un bucket como "Public" en Supabase NO lo hace accesible por la
    URL del endpoint S3 (`.../storage/v1/s3/...`): esa ruta exige petición
    firmada siempre. Los archivos públicos se sirven por la URL nativa de
    Supabase, `https://<project-ref>.supabase.co/storage/v1/object/public/
    <bucket>/<ruta>`, que es justo lo que devuelve esta función (sin
    protocolo, para usarse como `custom_domain` de django-storages).
    """
    project_ref = urlparse(endpoint_url).hostname.split(".")[0]
    return f"{project_ref}.supabase.co/storage/v1/object/public/{bucket_name}"
