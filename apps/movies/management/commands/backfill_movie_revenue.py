import time

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.movies.models import Movie
from apps.movies.services import MovieAPIError, tmdb_get_details

# Este comando se encadena en el startCommand de Render, ANTES de gunicorn
# (vía bootstrap_production) -- si TMDb va lento o no responde, cada
# película sin recaudación puede tardar mucho más que su propio timeout de
# request (reintentos de red por debajo de requests/urllib3), y con miles
# de películas eso agota con creces la ventana en la que Render espera a
# que se abra un puerto, tumbando el despliegue entero (ver incidente:
# "Port scan timeout reached" con el servicio nunca llegando a arrancar
# gunicorn). Un tope de tiempo total evita que un TMDb caído se lleve por
# delante todo el sitio -- la próxima vez que se ejecute retoma donde lo
# dejó (solo mira películas SIN recaudación, así que es idempotente).
MAX_SECONDS = 60


class Command(BaseCommand):
    help = (
        "Rellena la recaudación (TMDb) de las películas ya guardadas que todavía no "
        "la tienen — necesaria para el juego 'Cuál recaudó más'. Solo películas, "
        "TMDb no tiene ese dato para series. Segura de repetir: no vuelve a pedir "
        "los datos de una película que ya tiene recaudación conocida, y para sola "
        f"tras {MAX_SECONDS}s para no bloquear el arranque del servicio si TMDb va lento."
    )

    def handle(self, *args, **options):
        if not settings.TMDB_API_KEY:
            self.stderr.write(self.style.ERROR("Falta TMDB_API_KEY en el .env."))
            return

        movies = Movie.objects.filter(media_type=Movie.MediaType.MOVIE, revenue__isnull=True)
        started_at = time.monotonic()
        updated, skipped, timed_out = 0, 0, False
        for movie in movies:
            if time.monotonic() - started_at > MAX_SECONDS:
                timed_out = True
                break
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

        summary = f"Recaudación actualizada: {updated} películas, {skipped} sin dato en TMDb."
        if timed_out:
            summary += f" Parado tras {MAX_SECONDS}s (quedan más por revisar la próxima vez)."
        self.stdout.write(self.style.SUCCESS(summary))
