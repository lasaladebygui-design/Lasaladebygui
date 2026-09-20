from django.core.management.base import BaseCommand

from apps.games.models import MovieQuote

# Frases célebres reales de películas/series que están en tu propia lista
# guardada (Películas -> tus listas). Las opciones incorrectas también salen
# de tu lista, para que el juego se sienta hecho a medida.
#
# Solo se han incluido títulos con una frase realmente célebre y verificable
# -- la mayoría de tu lista es cine de autor/terror/anime muy concreto sin
# una línea de diálogo ampliamente reconocible, así que esta tanda es más
# corta que la genérica anterior mientras se prioriza que ninguna frase esté
# inventada. Si me dices frases concretas de otros títulos de tu lista, se
# añaden sin problema.
MOVIE_QUOTES = [
    ("Lo siento, Dave. Me temo que no puedo hacer eso.", "2001. Una odisea del espacio", "La llegada", "Dune: Parte tres"),
    ("Nada está escrito.", "Lawrence de Arabia", "Los siete samuráis", "Ran"),
    ("El mayor truco que hizo el diablo fue convencer al mundo de que no existía.", "Sospechosos habituales", "L.A. Confidential", "Heat"),
    ("Definitivamente, soy un excelente conductor.", "Rain Man", "American History X", "Smoke"),
    ("No te encariñes con nada que no puedas abandonar en treinta segundos si notas que la policía te pisa los talones.", "Heat", "Collateral", "Sospechosos habituales"),
    ("Larga vida a la nueva carne.", "Videodrome", "Suspiria", "Martyrs"),
    ("De todos los bares de todas las ciudades del mundo, entra en el mío.", "Casablanca", "Capitanes intrépidos", "Lawrence de Arabia"),
    ("Abre los ojos.", "Abre los ojos", "Vanilla Sky", "Vidas pasadas"),
    ("¡Yo no puedo evitarlo! ¡No puedo evitarlo!", "M, el vampiro de Düsseldorf", "La pasión de Juana de Arco", "Amanecer"),
    ("Al final, hemos vuelto a perder. Los que ganan son los campesinos, no nosotros.", "Los siete samuráis", "Ran", "Lawrence de Arabia"),
    ("¿Ha mejorado tu vida?", "American History X", "Rain Man", "Sleepers"),
]

# Series de tu lista con una frase realmente célebre y verificable.
SERIES_QUOTES = [
    ("Yo soy el peligro.", "Breaking Bad", "Vinland Saga", "Undone"),
    ("¡Te ordeno... que mueras!", "Code Geass: La Rebelión de Lelouch", "Vinland Saga", "To Your Eternity"),
]


class Command(BaseCommand):
    help = (
        "Sustituye TODAS las frases del juego 'Frases célebres' (Juegos) por "
        "esta tanda, sacada de tu propia lista de películas/series guardadas. "
        "Borra antes lo que hubiera (incluida cualquier frase añadida a mano "
        "desde el admin), así que es una sustitución completa, no un añadido."
    )

    def handle(self, *args, **options):
        deleted_count, _ = MovieQuote.objects.all().delete()
        self.stdout.write(self.style.WARNING(f"Borradas {deleted_count} frases anteriores."))

        created = []
        for quote, correct, wrong1, wrong2 in MOVIE_QUOTES:
            created.append(MovieQuote(
                quote=quote, media_type=MovieQuote.MediaType.MOVIE,
                correct_title=correct, wrong_title_1=wrong1, wrong_title_2=wrong2,
            ))
        for quote, correct, wrong1, wrong2 in SERIES_QUOTES:
            created.append(MovieQuote(
                quote=quote, media_type=MovieQuote.MediaType.TV,
                correct_title=correct, wrong_title_1=wrong1, wrong_title_2=wrong2,
            ))
        MovieQuote.objects.bulk_create(created)

        self.stdout.write(self.style.SUCCESS(
            f"Seed de frases célebres completado: {len(created)} frases nuevas, todas de tu lista."
        ))
