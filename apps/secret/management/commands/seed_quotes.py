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

    # Segunda tanda: para que repetir la misma frase sea casi imposible sin
    # perder la premisa del juego (frases realmente famosas, no rellenar por rellenar).
    ("¿Me estás hablando a mí?", "Taxi Driver", "El padrino", "Uno de los nuestros"),
    ("Houston, tenemos un problema.", "Apolo 13", "Interestelar", "Gravedad"),
    ("Soy Iron Man.", "Iron Man", "Los Vengadores", "Capitán América: El primer vengador"),
    ("¡Esto. Es. Esparta!", "300", "Troya", "Gladiator"),
    ("Yippee-ki-yay, hijo de perra.", "Duro de matar", "Arma letal", "Speed: máxima potencia"),
    ("Alégrame el día.", "Impacto súbito", "Harry el sucio", "El fugitivo"),
    ("Larga vida y prosperidad.", "Star Trek", "Star Wars: Una nueva esperanza", "Interestelar"),
    ("Pude haber sido un contendiente, en vez de un don nadie.", "La ley del silencio", "Toro salvaje", "Rocky"),
    ("Inconcebible.", "La princesa prometida", "Ella", "Encantada"),
    ("Nunca te enfrentes a un siciliano cuando la muerte está en juego.", "La princesa prometida", "El príncipe de Zamunda", "Descubriendo Nunca Jamás"),
    ("Wingardium leviosa.", "Harry Potter y la piedra filosofal", "Harry Potter y la cámara secreta", "Las crónicas de Narnia: El león, la bruja y el armario"),
    ("Después de todo este tiempo... ¿Siempre?", "Harry Potter y las reliquias de la muerte: Parte 2", "Harry Potter y el prisionero de Azkaban", "Harry Potter y el cáliz de fuego"),
    ("Vosotros no pasaréis.", "El señor de los anillos: La comunidad del anillo", "El hobbit: Un viaje inesperado", "Harry Potter y el cáliz de fuego"),
    ("Un mago nunca llega tarde, Frodo Bolsón. Ni pronto. Llega precisamente cuando se lo propone.", "El señor de los anillos: La comunidad del anillo", "El hobbit: Un viaje inesperado", "El señor de los anillos: Las dos torres"),
    ("Uno no puede simplemente entrar en Mordor.", "El señor de los anillos: La comunidad del anillo", "El señor de los anillos: El retorno del rey", "El hobbit: La batalla de los cinco ejércitos"),
    ("El miedo es el camino hacia el lado oscuro.", "Star Wars: La amenaza fantasma", "Star Wars: El ataque de los clones", "Star Wars: La venganza de los Sith"),
    ("Hazlo, o no lo hagas, pero no lo intentes.", "Star Wars: El imperio contraataca", "Star Wars: Una nueva esperanza", "Star Wars: El retorno del Jedi"),
    ("Simba, todo lo que toca la luz es nuestro reino.", "El rey león", "Madagascar", "Tarzán"),
    ("Ohana significa familia. Familia significa que nadie se queda atrás, ni es olvidado.", "Lilo & Stitch", "Los Increíbles", "Up"),
    ("Hay una gran diferencia entre conocer el camino y andar el camino.", "Matrix", "Origen", "El show de Truman"),
    ("Necesito armas. Muchas armas.", "Matrix", "Matrix Reloaded", "Equilibrium"),
    ("Redrum.", "El resplandor", "Poltergeist", "El exorcista"),
    ("Están aquí.", "Poltergeist", "El resplandor", "La profecía"),
    ("¿Quieres jugar a un juego?", "El juego del miedo", "Destino final", "Actividad paranormal"),
    ("Marty, tenemos que regresar... ¡al futuro!", "Regreso al futuro", "Regreso al futuro: Parte II", "Los Goonies"),
    ("La vida se abre camino.", "Parque Jurásico", "El mundo perdido: Jurassic Park", "Jurassic World"),
    ("Bienvenidos a Jurassic Park.", "Parque Jurásico", "Jurassic World", "King Kong"),
    ("Yo soy Groot.", "Guardianes de la Galaxia", "Los Vengadores", "Iron Man"),
    ("Vengadores... reunidos.", "Vengadores: Infinity War", "Los Vengadores", "Vengadores: Endgame"),
    ("Haz lo que sea necesario.", "Vengadores: Endgame", "Vengadores: Infinity War", "Capitán América: Civil War"),
    ("Yo soy inevitable.", "Vengadores: Endgame", "Vengadores: Infinity War", "Doctor Strange"),
    ("Ya sabes cómo silbar, ¿verdad? Solo tienes que juntar los labios... y soplar.", "Tener y no tener", "Casablanca", "La reina africana"),
    ("Que la Fuerza esté contigo, siempre... para todos nosotros.", "Star Wars: El ascenso de Skywalker", "Star Wars: El retorno del Jedi", "Star Wars: Los últimos Jedi"),
    ("En un mundo antiguo... nace una leyenda.", "Conan el bárbaro", "300", "Troya"),
    ("Yo veo gente muerta.", "El sexto sentido", "Los otros", "Actividad paranormal"),
    ("La verdad está ahí fuera.", "Contact", "Interestelar", "Encuentros en la tercera fase"),
    ("Un pequeño paso para el hombre, un gran salto para la humanidad.", "Apolo 13", "Interestelar", "El primer hombre"),
    ("No llores porque se terminó, sonríe porque sucedió.", "El diario de Noa", "Titanic", "Bajo la misma estrella"),
    ("El amor significa nunca tener que decir lo siento.", "Love Story", "El diario de Noa", "Titanic"),
    ("Si lo construyes, él vendrá.", "Campo de sueños", "El indomable Will Hunting", "Forrest Gump"),
    ("Algunos hombres solo quieren ver arder el mundo.", "El caballero oscuro", "Batman Begins", "Joker"),
    ("O mueres como un héroe, o vives lo suficiente para verte convertido en villano.", "El caballero oscuro", "Batman Begins", "El caballero oscuro: La leyenda renace"),
    ("Ríndete, Dorothy.", "El mago de Oz", "Hocus Pocus", "Blancanieves y los siete enanitos"),
    ("Elemental, querido Watson.", "Sherlock Holmes", "El nombre de la rosa", "Los crímenes de la calle Morgue"),
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
