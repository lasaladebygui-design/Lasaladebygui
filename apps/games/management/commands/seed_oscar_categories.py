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
        updated_count = 0
        for order, (name, candidate_type) in enumerate(CATEGORIES):
            category, created = OscarCategory.objects.get_or_create(
                name=name, defaults={"order": order, "candidate_type": candidate_type},
            )
            if created:
                created_count += 1
            elif category.candidate_type != candidate_type or category.order != order:
                # get_or_create solo aplica "defaults" al crear: categorías
                # sembradas por una versión anterior de este comando (antes
                # de que existiera candidate_type, cuando todo se quedaba en
                # "movie" por defecto) se quedaban con el tipo equivocado
                # para siempre — de ahí que "Mejor actor"/etc. no dejaran
                # proponer personas ni mostrar su foto.
                category.candidate_type = candidate_type
                category.order = order
                category.save(update_fields=["candidate_type", "order"])
                updated_count += 1

        valid_names = [name for name, _ in CATEGORIES]
        stale = OscarCategory.objects.exclude(name__in=valid_names)
        removed_count = stale.count()
        stale.delete()

        self.stdout.write(self.style.SUCCESS(
            f"Seed de categorías de Oscar completado: {created_count} nuevas, "
            f"{updated_count} corregidas, {removed_count} obsoletas eliminadas."
        ))
