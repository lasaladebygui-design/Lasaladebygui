from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Exists, F, OuterRef, Q
from django.utils import timezone

from apps.movies.models import Movie
from apps.movies.services import MovieAPIError, omdb_fetch_imdb_rating, tmdb_get_details

# El plan gratuito de OMDb da 1.000 peticiones al día. Se deja margen para
# las fichas nuevas que se añaden ese mismo día desde la web (cada una
# gasta una petición en `Movie.get_or_create_from_tmdb`).
DEFAULT_LIMIT = 900
DEFAULT_DAYS = 30
# Los estrenos suelen entrar sin nota (o sin id de IMDb en TMDb): se
# reintentan cada semana en vez de esperar un mes.
MISSING_RATING_DAYS = 7


class Command(BaseCommand):
    help = (
        "Vuelve a pedir a OMDb la nota IMDb de las películas y series del catálogo "
        f"cuya nota lleva más de {DEFAULT_DAYS} días sin comprobarse (las más antiguas "
        f"primero, como mucho {DEFAULT_LIMIT} por ejecución para no pasarse de la cuota "
        "diaria de OMDb). Solo toca las fichas que ya están en el catálogo — no descarga "
        "notas de nada más. Lo lanza a diario update_catalog: así cada ficha se "
        "renueva aproximadamente una vez al mes aunque el catálogo crezca."
    )

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Antigüedad mínima de la nota para renovarla.")
        parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Máximo de peticiones a OMDb en esta ejecución.")

    def handle(self, *args, **options):
        if not settings.OMDB_API_KEY:
            self.stderr.write(self.style.ERROR("Falta OMDB_API_KEY en el .env."))
            return

        now = timezone.now()
        cutoff = now - timedelta(days=options["days"])
        missing_cutoff = now - timedelta(days=MISSING_RATING_DAYS)
        # Primero las que están en alguna lista (Top Secret o Guardadas): con
        # miles de fichas en el catálogo y unos cientos por día, por orden de
        # alta las que de verdad se miran podían tardar semanas en tener nota.
        from apps.movies.models import SavedMovie
        from apps.secret.models import SecretMovie

        movies = (
            Movie.objects.filter(
                Q(imdb_rating_checked_at__isnull=True)
                | Q(imdb_rating_checked_at__lt=cutoff)
                | Q(imdb_rating__isnull=True, imdb_rating_checked_at__lt=missing_cutoff)
            )
            .annotate(
                in_secret=Exists(SecretMovie.objects.filter(movie=OuterRef("pk"))),
                in_saved=Exists(SavedMovie.objects.filter(movie=OuterRef("pk"))),
            )
            .order_by(
                F("in_secret").desc(), F("in_saved").desc(),
                F("imdb_rating_checked_at").asc(nulls_first=True), "pk",
            )[: options["limit"]]
        )

        changed, unchanged, stopped = 0, 0, False
        for movie in movies:
            update_fields = ["imdb_rating_checked_at"]
            movie.imdb_rating_checked_at = timezone.now()
            if not movie.imdb_id:
                imdb_id = self._imdb_id_from_tmdb(movie)
                if not imdb_id:
                    movie.save(update_fields=update_fields)
                    unchanged += 1
                    continue
                movie.imdb_id = imdb_id
                update_fields.append("imdb_id")
            try:
                rating = omdb_fetch_imdb_rating(movie.imdb_id)
            except MovieAPIError as exc:
                # Red caída o cuota agotada: seguir solo gastaría peticiones
                # en balde. Lo que falte se retoma en la siguiente ejecución.
                self.stderr.write(self.style.WARNING(f"Se para en «{movie.title}»: {exc}"))
                stopped = True
                break

            # Si OMDb ya no tiene nota se conserva la anterior en vez de
            # dejar la ficha sin nota.
            if rating is not None and movie.imdb_rating != Decimal(str(rating)):
                self.stdout.write(f"  ~ {movie.title} ({movie.year}): {movie.imdb_rating} → {rating}")
                movie.imdb_rating = Decimal(str(rating))
                update_fields.append("imdb_rating")
                changed += 1
            else:
                unchanged += 1
            movie.save(update_fields=update_fields)

        summary = f"Notas IMDb revisadas: {changed} cambiadas, {unchanged} sin cambios."
        if stopped:
            summary += " Parado antes de tiempo (se retoma en la próxima ejecución)."
        self.stdout.write(self.style.SUCCESS(summary))

    def _imdb_id_from_tmdb(self, movie):
        if not settings.TMDB_API_KEY:
            return ""
        try:
            details = tmdb_get_details(movie.tmdb_id, media_type=movie.media_type)
        except MovieAPIError:
            return ""
        return (details.get("external_ids") or {}).get("imdb_id") or ""
