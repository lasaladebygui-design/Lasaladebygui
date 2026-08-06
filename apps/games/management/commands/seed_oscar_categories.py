from django.core.management.base import BaseCommand

from apps.games.models import OscarCategory

CATEGORIES = [
    "Mejor película",
    "Mejor serie",
    "Mejor director/a",
    "Mejor actor",
    "Mejor actriz",
    "Mejor guion",
    "Mejor banda sonora",
]


class Command(BaseCommand):
    help = "Carga las categorías iniciales de 'Candidatos al Oscar'. Seguro de ejecutar también contra producción."

    def handle(self, *args, **options):
        created_count = 0
        for order, name in enumerate(CATEGORIES):
            _, created = OscarCategory.objects.get_or_create(name=name, defaults={"order": order})
            if created:
                created_count += 1
        self.stdout.write(self.style.SUCCESS(
            f"Seed de categorías de Oscar completado: {created_count} nuevas, {len(CATEGORIES) - created_count} ya existían."
        ))
