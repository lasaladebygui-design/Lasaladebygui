from django.core.management.base import BaseCommand

from apps.secret.models import MovieQuote

# Tanda inicial de frases para "Frases célebres". No hay límite real: desde
# el admin (Top Secret → Frases célebres) se pueden añadir tantas como se
# quiera, en cualquier momento, sin tocar código.
MOVIE_QUOTES = [
    ("Que la Fuerza te acompañe.", "Star Wars", "Regreso al futuro", "El padrino"),
    ("Voy a hacerle una oferta que no podrá rechazar.", "El padrino", "Uno de los nuestros", "Scarface"),
    ("Hasta el infinito y más allá.", "Toy Story", "Wall-E", "Los Increíbles"),
    ("Aquí hay algo que no encaja... y ese algo soy yo.", "Reservoir Dogs", "Pulp Fiction", "Kill Bill"),
    ("Con un gran poder viene una gran responsabilidad.", "Spider-Man", "Batman Begins", "El caballero oscuro"),
    ("Soy el rey del mundo.", "Titanic", "El renacido", "Náufrago"),
    ("La vida es como una caja de bombones, nunca sabes lo que te va a tocar.", "Forrest Gump", "Big", "El curioso caso de Benjamin Button"),
    ("Hakuna Matata.", "El rey león", "Madagascar", "Tarzán"),
    ("Hasta la vista, baby.", "Terminator 2: El juicio final", "RoboCop", "Depredador"),
    ("Siempre nos quedará París.", "Casablanca", "Medianoche en París", "Vacaciones en Roma"),
    ("No hay lugar como el hogar.", "El mago de Oz", "Alicia en el país de las maravillas", "Regreso a Oz"),
    ("Vamos a necesitar un barco más grande.", "Tiburón", "Deep Blue Sea", "Mar adentro"),
    ("Adrian, ¡lo logré!", "Rocky", "Toro salvaje", "Creed"),
    ("¿Te sientes con suerte, punk?", "Harry el sucio", "Contacto en Francia", "Distrito 13: La ley de las calles"),
    ("Mi nombre es Máximo Décimo Meridio.", "Gladiator", "Troya", "300"),
    ("Hola, Clarice.", "El silencio de los corderos", "Seven", "Zodiac"),
    ("¿Por qué tan serio?", "El caballero oscuro", "Joker", "Batman Begins"),
    ("Me encanta el olor a napalm por las mañanas.", "Apocalypse Now", "La chaqueta metálica", "Platoon"),
    ("La codicia, a falta de una palabra mejor, es buena.", "Wall Street", "El lobo de Wall Street", "American Psycho"),
    ("Enséñame el dinero.", "Jerry Maguire", "Moneyball", "En busca de la felicidad"),
    ("¡Libertad!", "Braveheart", "Gladiator", "300"),
    ("No hay cuchara.", "Matrix", "Origen", "Contact"),
    ("Yo soy tu padre.", "Star Wars: El imperio contraataca", "Star Wars: Una nueva esperanza", "El retorno del Jedi"),
    ("Mi casa. Teléfono.", "E.T., el extraterrestre", "Cocoon", "Encuentros en la tercera fase"),
    ("Todos esos momentos se perderán en el tiempo, como lágrimas en la lluvia.", "Blade Runner", "Matrix", "Ghost in the Shell"),
    ("Dale cera, pule cera.", "Karate Kid", "Kickboxer", "Rocky"),
    ("¡Bienvenidos a la Tierra!", "Independence Day", "Señales", "La guerra de los mundos"),
    ("Uno para gobernarlos a todos.", "El señor de los anillos: La comunidad del anillo", "El hobbit", "Harry Potter y la piedra filosofal"),
    ("Que la suerte esté siempre de tu parte.", "Los juegos del hambre", "Battle Royale", "El corredor del laberinto"),
    ("Bienvenido a la selva.", "Jumanji", "Los Goonies", "Parque Jurásico"),
    ("¡Aquí está Johnny!", "El resplandor", "Poltergeist", "La profecía"),
    ("Volveré.", "Terminator", "Depredador", "RoboCop"),
    ("Sigue nadando.", "Buscando a Nemo", "Buscando a Dory", "Shark Tale"),
    ("Francamente, querida, me importa un bledo.", "Lo que el viento se llevó", "Casablanca", "Cantando bajo la lluvia"),
    ("¡Tú no puedes manejar la verdad!", "Algunos hombres buenos", "Doce hombres sin piedad", "Erin Brockovich"),
    ("Solo hay una regla: no se habla del Club de la Lucha.", "El club de la lucha", "American Psycho", "Seven"),
]


class Command(BaseCommand):
    help = (
        "Carga las frases de ejemplo del juego 'Frases célebres' (Top Secret → "
        "Juegos). A diferencia de seed_content, no crea usuarios de ejemplo, así "
        "que es seguro ejecutarlo también contra una base de datos de producción."
    )

    def handle(self, *args, **options):
        created_count = 0
        for quote, correct, wrong1, wrong2 in MOVIE_QUOTES:
            _, created = MovieQuote.objects.get_or_create(
                quote=quote,
                defaults={"correct_title": correct, "wrong_title_1": wrong1, "wrong_title_2": wrong2},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Frase célebre creada: «{quote}»"))
            else:
                self.stdout.write(f"Ya existía la frase «{quote}», no se modifica.")

        self.stdout.write(self.style.SUCCESS(
            f"Seed de frases célebres completado: {created_count} nuevas, {len(MOVIE_QUOTES) - created_count} ya existían."
        ))
