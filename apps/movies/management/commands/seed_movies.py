import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.movies.models import Movie
from apps.movies.services import TMDB_BASE_URL, REQUEST_TIMEOUT, MovieAPIError


class Command(BaseCommand):
    help = (
        "Puebla el catálogo de películas (necesario para el Modo 1 de la ruleta, "
        "que filtra por rango de nota IMDb) a partir de TMDb, resolviendo la nota "
        "IMDb de cada una vía OMDb. Combina listados de populares/mejor valoradas "
        "con búsquedas 'discover' por franja de nota para que el catálogo cubra "
        "todo el rango 1-10, no solo las películas mejor valoradas."
    )

    # Además de "popular"/"top_rated" (que solo traen películas bien valoradas),
    # recorremos /discover/movie por franjas de nota de TMDb para que el
    # catálogo tenga también películas flojas/mediocres — si no, rangos bajos
    # de la ruleta (Modo 1) se quedan sin ninguna candidata.
    DISCOVER_BUCKETS = [
        {"vote_average.lte": 4, "vote_count.gte": 100, "sort_by": "vote_count.desc"},
        {"vote_average.gte": 4, "vote_average.lte": 6, "vote_count.gte": 200, "sort_by": "popularity.desc"},
        {"vote_average.gte": 6, "vote_average.lte": 7.5, "vote_count.gte": 200, "sort_by": "popularity.desc"},
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--pages", type=int, default=2,
            help="Páginas de TMDb a recorrer por listado/franja (20 películas por página). Por defecto: 2.",
        )

    def _fetch_page(self, endpoint, page, extra_params=None):
        params = {"api_key": settings.TMDB_API_KEY, "language": "es-ES", "page": page}
        params.update(extra_params or {})
        url = f"{TMDB_BASE_URL}/discover/movie" if endpoint == "discover" else f"{TMDB_BASE_URL}/movie/{endpoint}"
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

        self.stdout.write(f"{len(tmdb_ids)} películas candidatas encontradas en TMDb. Resolviendo nota IMDb…")

        created, skipped = 0, 0
        for tmdb_id in tmdb_ids:
            if Movie.objects.filter(tmdb_id=tmdb_id).exists():
                skipped += 1
                continue
            try:
                movie = Movie.get_or_create_from_tmdb(tmdb_id)
            except MovieAPIError as exc:
                self.stderr.write(self.style.WARNING(f"Se omite tmdb_id={tmdb_id}: {exc}"))
                continue
            created += 1
            rating = movie.imdb_rating if movie.imdb_rating is not None else "sin nota"
            self.stdout.write(f"  + {movie.title} ({movie.year}) — IMDb {rating}")

        self.stdout.write(self.style.SUCCESS(
            f"Catálogo actualizado: {created} películas nuevas, {skipped} ya existían."
        ))
