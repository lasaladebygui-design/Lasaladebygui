import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.movies.models import Movie
from apps.movies.services import TMDB_BASE_URL, REQUEST_TIMEOUT, MovieAPIError


class Command(BaseCommand):
    help = (
        "Puebla el catálogo de series a partir de TMDb, igual que seed_movies pero "
        "para /tv/ — sin esto, 'Series' en el catálogo aparece vacío hasta que algún "
        "usuario busca y añade una serie a mano, así que el scroll infinito no tiene "
        "nada que mostrar de entrada."
    )

    DISCOVER_BUCKETS = [
        {"vote_average.lte": 4, "vote_count.gte": 50, "sort_by": "vote_count.desc"},
        {"vote_average.gte": 4, "vote_average.lte": 6, "vote_count.gte": 100, "sort_by": "popularity.desc"},
        {"vote_average.gte": 6, "vote_average.lte": 7.5, "vote_count.gte": 100, "sort_by": "popularity.desc"},
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--pages", type=int, default=2,
            help="Páginas de TMDb a recorrer por listado/franja (20 series por página). Por defecto: 2.",
        )

    def _fetch_page(self, endpoint, page, extra_params=None):
        params = {"api_key": settings.TMDB_API_KEY, "language": "es-ES", "page": page}
        params.update(extra_params or {})
        url = f"{TMDB_BASE_URL}/discover/tv" if endpoint == "discover" else f"{TMDB_BASE_URL}/tv/{endpoint}"
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json().get("results", [])

    def handle(self, *args, **options):
        if not settings.TMDB_API_KEY or not settings.OMDB_API_KEY:
            self.stderr.write(self.style.ERROR(
                "Faltan TMDB_API_KEY y/o OMDB_API_KEY en el .env. Consulta el README (sección de variables de entorno)."
            ))
            return

        pages = options["pages"]
        tmdb_ids = set()

        for endpoint in ("popular", "top_rated"):
            for page in range(1, pages + 1):
                try:
                    results = self._fetch_page(endpoint, page)
                except requests.RequestException as exc:
                    self.stderr.write(self.style.ERROR(f"Fallo al leer {endpoint} página {page}: {exc}"))
                    continue
                for item in results:
                    tmdb_ids.add(item["id"])

        for bucket in self.DISCOVER_BUCKETS:
            for page in range(1, pages + 1):
                try:
                    results = self._fetch_page("discover", page, bucket)
                except requests.RequestException as exc:
                    self.stderr.write(self.style.ERROR(f"Fallo al leer discover {bucket} página {page}: {exc}"))
                    continue
                for item in results:
                    tmdb_ids.add(item["id"])

        self.stdout.write(f"{len(tmdb_ids)} series candidatas encontradas en TMDb. Resolviendo nota IMDb…")

        created, skipped = 0, 0
        for tmdb_id in tmdb_ids:
            if Movie.objects.filter(tmdb_id=tmdb_id, media_type=Movie.MediaType.TV).exists():
                skipped += 1
                continue
            try:
                series = Movie.get_or_create_from_tmdb(tmdb_id, media_type=Movie.MediaType.TV)
            except MovieAPIError as exc:
                self.stderr.write(self.style.WARNING(f"Se omite tmdb_id={tmdb_id}: {exc}"))
                continue
            created += 1
            rating = series.imdb_rating if series.imdb_rating is not None else "sin nota"
            self.stdout.write(f"  + {series.title} ({series.year}) — IMDb {rating}")

        self.stdout.write(self.style.SUCCESS(
            f"Catálogo de series actualizado: {created} series nuevas, {skipped} ya existían."
        ))
