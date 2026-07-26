import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.movies.models import Movie
from apps.movies.services import TMDB_BASE_URL, REQUEST_TIMEOUT, MovieAPIError


class Command(BaseCommand):
    help = (
        "Puebla el catálogo de películas (necesario para el Modo 1 de la ruleta, "
        "que filtra por rango de nota IMDb) a partir de TMDb (populares y mejor "
        "valoradas) resolviendo la nota IMDb de cada una vía OMDb."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--pages", type=int, default=2,
            help="Páginas de TMDb a recorrer por listado (20 películas por página). Por defecto: 2.",
        )

    def _fetch_page(self, endpoint, page):
        response = requests.get(
            f"{TMDB_BASE_URL}/movie/{endpoint}",
            params={"api_key": settings.TMDB_API_KEY, "language": "es-ES", "page": page},
            timeout=REQUEST_TIMEOUT,
        )
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
