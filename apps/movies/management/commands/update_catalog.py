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
        # 300 por las renovadas deja de sobra para lo que se añade desde la web,
        # y 300 al día da para renovar unas 9.000 fichas al mes.
        call_command("sync_new_releases", limit=60)
        call_command("refresh_imdb_ratings", limit=300)
