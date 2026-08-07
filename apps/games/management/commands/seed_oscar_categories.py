from django.core.management.base import BaseCommand

from apps.games.models import OscarCategory

# Categorías reales de los Premios de la Academia (las más conocidas — no
# las ~23 completas, para que la lista sea manejable). "movie" = se propone
# una película del catálogo; "person" = se propone una persona (actor/
# actriz, director/a...), buscada y con foto vía TMDb.
CATEGORIES = [
    ("Mejor película", "movie"),
    ("Mejor director/a", "person"),
    ("Mejor actor", "person"),
    ("Mejor actriz", "person"),
    ("Mejor actor de reparto", "person"),
    ("Mejor actriz de reparto", "person"),
    ("Mejor guion original", "movie"),
    ("Mejor guion adaptado", "movie"),
    ("Mejor película internacional", "movie"),
    ("Mejor película de animación", "movie"),
    ("Mejor documental", "movie"),
    ("Mejor banda sonora original", "movie"),
    ("Mejor canción original", "movie"),
    ("Mejor fotografía", "movie"),
    ("Mejor montaje", "movie"),
    ("Mejor diseño de vestuario", "movie"),
    ("Mejores efectos visuales", "movie"),
]


class Command(BaseCommand):
    help = "Carga las categorías reales de los Oscar en 'Candidatos al Oscar'. Seguro de ejecutar también contra producción."

    def handle(self, *args, **options):
        created_count = 0
        for order, (name, candidate_type) in enumerate(CATEGORIES):
            _, created = OscarCategory.objects.get_or_create(
                name=name, defaults={"order": order, "candidate_type": candidate_type},
            )
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(
            f"Seed de categorías de Oscar completado: {created_count} nuevas, {len(CATEGORIES) - created_count} ya existían."
        ))
