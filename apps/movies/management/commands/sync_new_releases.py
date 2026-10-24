import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.movies.models import Movie
from apps.movies.services import REQUEST_TIMEOUT, TMDB_BASE_URL, MovieAPIError

# Listados de TMDb con lo que está saliendo ahora. Las películas se miran con
# la cartelera española (region=ES); de las series, las que tienen episodios
# en emisión. "trending" añade lo que más se está viendo esta semana.
SOURCES = [
    ("movie", "movie/now_playing", {"region": "ES"}),
    ("movie", "movie/upcoming", {"region": "ES"}),
    ("movie", "trending/movie/week", {}),
    ("tv", "tv/on_the_air", {}),
    ("tv", "trending/tv/week", {}),
]


class Command(BaseCommand):
    help = (
        "Añade al catálogo las películas en cartelera y próximos estrenos, y las "
        "series en emisión, según TMDb. Solo da de alta las que aún no están (cada "
        "una gasta una petición de OMDb para la nota IMDb), como mucho --limit por "
        "ejecución. La lanza a diario update_catalog."
    )

    def add_arguments(self, parser):
        parser.add_argument("--pages", type=int, default=2, help="Páginas de cada listado (20 títulos por página).")
        parser.add_argument("--limit", type=int, default=60, help="Máximo de fichas nuevas por ejecución.")

    def _fetch(self, path, page, extra):
        params = {"api_key": settings.TMDB_API_KEY, "language": "es-ES", "page": page, **extra}
        response = requests.get(f"{TMDB_BASE_URL}/{path}", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json().get("results", [])

    def handle(self, *args, **options):
        if not settings.TMDB_API_KEY:
            self.stderr.write(self.style.ERROR("Falta TMDB_API_KEY en el .env."))
            return

        candidates = []
        for media_type, path, extra in SOURCES:
            for page in range(1, options["pages"] + 1):
                try:
                    results = self._fetch(path, page, extra)
                except requests.RequestException as exc:
                    self.stderr.write(self.style.WARNING(f"Fallo al leer {path} página {page}: {exc}"))
                    break
                candidates += [(item["id"], media_type) for item in results if item.get("id")]

        seen, created = set(), 0
        for tmdb_id, media_type in candidates:
            if created >= options["limit"]:
                break
            if (tmdb_id, media_type) in seen:
                continue
            seen.add((tmdb_id, media_type))
            if Movie.objects.filter(tmdb_id=tmdb_id, media_type=media_type).exists():
                continue
            try:
                movie = Movie.get_or_create_from_tmdb(tmdb_id, media_type=media_type)
            except MovieAPIError as exc:
                self.stderr.write(self.style.WARNING(f"Se omite {media_type} tmdb_id={tmdb_id}: {exc}"))
                continue
            created += 1
            self.stdout.write(f"  + {movie.title} ({movie.year}) {'· Serie' if movie.is_tv else ''}")

        self.stdout.write(self.style.SUCCESS(f"Estrenos: {created} fichas nuevas en el catálogo."))
