from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Actualización diaria del catálogo: añade los estrenos nuevos de TMDb "
        "(sync_new_releases) y renueva las notas IMDb con más de un mes "
        "(refresh_imdb_ratings). La lanza sola la web una vez al día — ver "
        "apps/movies/maintenance.py."
    )

    def handle(self, *args, **options):
        # Cuota de OMDb: 1.000 peticiones/día. Hasta 60 por las fichas nuevas y
        # 800 por las renovadas deja unas 140 para lo que se pide desde la web
        # (fichas que se abren, tarjetas sin nota). 800 al día rellena en unos
        # días las fichas que aún no tienen nota y luego renueva cada una más
        # o menos una vez al mes aunque el catálogo crezca.
        call_command("sync_new_releases", limit=60)
        call_command("refresh_imdb_ratings", limit=800)
