from django.conf import settings
from django.core.management.base import BaseCommand

from apps.movies.models import Movie
from apps.movies.services import MovieAPIError, tmdb_get_details


class Command(BaseCommand):
    help = (
        "Rellena la recaudación (TMDb) de las películas ya guardadas que todavía no "
        "la tienen — necesaria para el juego 'Cuál recaudó más'. Solo películas, "
        "TMDb no tiene ese dato para series. Segura de repetir: no vuelve a pedir "
        "los datos de una película que ya tiene recaudación conocida."
    )

    def handle(self, *args, **options):
        if not settings.TMDB_API_KEY:
            self.stderr.write(self.style.ERROR("Falta TMDB_API_KEY en el .env."))
            return

        movies = Movie.objects.filter(media_type=Movie.MediaType.MOVIE, revenue__isnull=True)
        updated, skipped = 0, 0
        for movie in movies:
            try:
                details = tmdb_get_details(movie.tmdb_id, media_type=Movie.MediaType.MOVIE)
            except MovieAPIError as exc:
                self.stderr.write(self.style.WARNING(f"Se omite «{movie.title}»: {exc}"))
                continue
            revenue = details.get("revenue")
            if not revenue:
                skipped += 1
                continue
            movie.revenue = revenue
            movie.save(update_fields=["revenue"])
            updated += 1
            self.stdout.write(f"  + {movie.title} ({movie.year}) — ${revenue:,}")

        self.stdout.write(self.style.SUCCESS(
            f"Recaudación actualizada: {updated} películas, {skipped} sin dato en TMDb."
        ))
