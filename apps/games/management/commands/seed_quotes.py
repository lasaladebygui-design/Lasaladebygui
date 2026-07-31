from django.core.management.base import BaseCommand

from apps.games.models import MovieQuote

# Tanda inicial de frases para "Frases célebres". No hay límite real: desde
# el admin (Top Secret → Frases célebres) se pueden añadir tantas como se
# quiera, en cualquier momento, sin tocar código.
MOVIE_QUOTES = [
    ("Que la Fuerza te acompañe.", "Star Wars", "Regreso al futuro", "El padrino"),
    ("Voy a hacerle una oferta que no podrá rechazar.", "El padrino", "Uno de los nuestros", "Scarface"),
    ("Hasta el infinito y más allá.", "Toy Story", "Wall-E", "Los Increíbles"),
    ("De todos los bares de todas las ciudades del mundo, entra en el mío.", "Casablanca", "El sueño eterno", "La ventana indiscreta"),
    ("Con un gran poder viene una gran responsabilidad.", "Spider-Man", "Batman Begins", "El caballero oscuro"),
    ("¡Yo soy el rey del mundo!", "Titanic", "El renacido", "Náufrago"),
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
    ("¡Tú no puedes soportar la verdad!", "Algunos hombres buenos", "Doce hombres sin piedad", "Erin Brockovich"),
    ("La primera regla del Club de la Lucha es que no se habla del Club de la Lucha.", "El club de la lucha", "American Psycho", "Seven"),

    # Segunda tanda: para que repetir la misma frase sea casi imposible sin
    # perder la premisa del juego (frases realmente famosas, no rellenar por rellenar).
    ("¿Me estás hablando a mí?", "Taxi Driver", "El padrino", "Uno de los nuestros"),
    ("Houston, tenemos un problema.", "Apolo 13", "Interestelar", "Gravedad"),
    ("Yo soy Iron Man.", "Iron Man", "Los Vengadores", "Capitán América: El primer vengador"),
    ("¡Esto. Es. Esparta!", "300", "Troya", "Gladiator"),
    ("Si sangra, podemos matarlo.", "Depredador", "Terminator", "Arma letal"),
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
    ("Vengadores... reunidos.", "Vengadores: Endgame", "Los Vengadores", "Vengadores: Infinity War"),
    ("Perfectamente equilibrado, como todo debería estar.", "Vengadores: Infinity War", "Vengadores: Endgame", "Doctor Strange"),
    ("Yo soy inevitable.", "Vengadores: Endgame", "Vengadores: Infinity War", "Doctor Strange"),
    ("Ya sabes cómo silbar, ¿verdad? Solo tienes que juntar los labios... y soplar.", "Tener y no tener", "Casablanca", "La reina africana"),
    ("Que la Fuerza esté contigo. Siempre.", "Star Wars: El ascenso de Skywalker", "Star Wars: El retorno del Jedi", "Star Wars: Los últimos Jedi"),
    ("Son más que reglas, son más bien... pautas.", "Piratas del Caribe: La maldición de la Perla Negra", "Piratas del Caribe: El cofre del hombre muerto", "Piratas del Caribe: En el fin del mundo"),
    ("Yo veo gente muerta.", "El sexto sentido", "Los otros", "Actividad paranormal"),
    ("Aquí abajo, todos flotan.", "Eso", "El resplandor", "Actividad paranormal"),
    ("Fracasar no es una opción.", "Apolo 13", "Interestelar", "El primer hombre"),
    ("Si tú eres un pájaro, yo también soy un pájaro.", "El diario de Noa", "Titanic", "Bajo la misma estrella"),
    ("El amor significa nunca tener que decir lo siento.", "Love Story", "El diario de Noa", "Titanic"),
    ("Si lo construyes, él vendrá.", "Campo de sueños", "El indomable Will Hunting", "Forrest Gump"),
    ("Algunos hombres solo quieren ver arder el mundo.", "El caballero oscuro", "Batman Begins", "Joker"),
    ("O mueres como un héroe, o vives lo suficiente para verte convertido en villano.", "El caballero oscuro", "Batman Begins", "El caballero oscuro: La leyenda renace"),
    ("Ríndete, Dorothy.", "El mago de Oz", "Hocus Pocus", "Blancanieves y los siete enanitos"),
    ("¿Por qué nos caemos? Para aprender a levantarnos.", "Batman Begins", "El caballero oscuro", "El caballero oscuro: La leyenda renace"),

    # Tercera tanda: ampliando el catálogo con otro medio centenar de frases
    # igual de reconocibles, sin repetir ninguna de las anteriores.
    ("Ayúdame, Obi-Wan Kenobi. Eres mi única esperanza.", "Star Wars: Una nueva esperanza", "Star Wars: El imperio contraataca", "Star Wars: El retorno del Jedi"),
    ("Mantén cerca a tus amigos, pero aún más cerca a tus enemigos.", "El padrino: Parte II", "El padrino", "Uno de los nuestros"),
    ("¿No estáis entretenidos?", "Gladiator", "Troya", "300"),
    ("Dibújame como una de tus chicas francesas.", "Titanic", "El renacido", "Náufrago"),
    ("Ven conmigo si quieres vivir.", "Terminator 2: El juicio final", "Terminator", "RoboCop"),
    ("O te ocupas de vivir, o te ocupas de morir.", "Cadena perpetua", "El indomable Will Hunting", "American History X"),
    ("Tonto es el que hace tonterías.", "Forrest Gump", "Big", "El curioso caso de Benjamin Button"),
    ("¿Carreteras? A donde vamos, no necesitamos carreteras.", "Regreso al futuro", "Regreso al futuro: Parte II", "Los Goonies"),
    ("Elige la vida.", "Trainspotting", "El club de la lucha", "Réquiem por un sueño"),
    ("¡Saluda a mi amiguito!", "Scarface", "El padrino", "Uno de los nuestros"),
    ("Nadie mete a Baby en un rincón.", "Dirty Dancing", "Grease", "Flashdance"),
    ("Antes pensaba que mi vida era una tragedia, pero ahora me doy cuenta de que es una comedia.", "Joker", "El caballero oscuro", "Batman Begins"),
    ("Si todos son especiales... entonces nadie lo será.", "Los Increíbles", "Big Hero 6", "Zootrópolis"),
    ("Los ogros son como las cebollas: tienen capas.", "Shrek", "Shrek 2", "El gato con botas"),
    ("Suéltalo, suéltalo.", "Frozen: El reino del hielo", "Enredados", "Vaiana"),
    ("¿Por qué siempre se acaba el ron?", "Piratas del Caribe: La maldición de la Perla Negra", "Piratas del Caribe: El cofre del hombre muerto", "Piratas del Caribe: En el fin del mundo"),
    ("No existe el bien ni el mal, solo el poder, y quienes son demasiado débiles para buscarlo.", "Harry Potter y la piedra filosofal", "Harry Potter y la cámara secreta", "Harry Potter y el prisionero de Azkaban"),
    ("No todo el que vaga está perdido.", "El señor de los anillos: La comunidad del anillo", "El hobbit: Un viaje inesperado", "El señor de los anillos: Las dos torres"),
    ("Tenemos que ir más profundo.", "Origen", "Matrix", "El show de Truman"),
    ("Buenos días. Y por si no os vuelvo a ver... ¡buenas tardes, buenas noches y buenas noches!", "El show de Truman", "Origen", "Múltiple"),
    ("¿Te hago gracia? ¿Gracia cómo? ¿Como un payaso, te divierto?", "Uno de los nuestros", "El padrino", "Scarface"),
    ("Un gran error. Grande. Enorme.", "Pretty Woman", "Dirty Dancing", "Cuando Harry encontró a Sally"),
    ("Yo quiero lo que está tomando ella.", "Cuando Harry encontró a Sally", "Pretty Woman", "Algo pasa con Mary"),
    ("¡Esta noche cenaremos en el infierno!", "300", "Troya", "Gladiator"),
    ("No es culpa tuya.", "El indomable Will Hunting", "Cadena perpetua", "American History X"),
    ("Y entonces el león se enamoró del cordero.", "Crepúsculo", "Luna nueva", "Amanecer"),
    ("Véndeme este bolígrafo.", "El lobo de Wall Street", "Wall Street", "Wall Street: El dinero nunca duerme"),
    ("Cualquiera puede ser lo que quiera.", "Zootrópolis", "Los Increíbles", "Vaiana"),
    ("¡Hay una serpiente en mi bota!", "Toy Story", "Toy Story 2", "Cars"),
    ("El amor es lo único que trasciende el tiempo y el espacio.", "Interestelar", "Contact", "Origen"),
    ("¡Wilson! ¡Lo siento mucho, Wilson!", "Náufrago", "El renacido", "Vidas al límite"),
    ("Cueste lo que cueste.", "Vengadores: Endgame", "Vengadores: Infinity War", "Capitán América: Civil War"),
    ("¡Wakanda por siempre!", "Black Panther", "Vengadores: Infinity War", "Doctor Strange"),
    ("El miedo es el asesino de la mente.", "Dune", "Interestelar", "Blade Runner 2049"),
    ("Le llaman Baba Yaga.", "John Wick", "Kill Bill", "Sicario"),
    ("¡Qué día tan maravilloso!", "Mad Max: Furia en la carretera", "Mad Max", "Waterworld"),

    # Cuarta tanda: animación, terror, western y un poco de todo, sin
    # repetir ninguna de las anteriores.
    ("No hay ningún ingrediente secreto.", "Kung Fu Panda", "Mulán", "Los Increíbles"),
    ("Cualquiera puede cocinar.", "Ratatouille", "Kung Fu Panda", "Wall-E"),
    ("No se habla de Bruno.", "Encanto", "Vaiana", "Coco"),
    ("El océano me eligió por una razón.", "Vaiana", "Frozen: El reino del hielo", "Encanto"),
    ("Gracias por la aventura. Ahora ve a tener una nueva.", "Up", "Del revés", "Coco"),
    ("Un mundo ideal, nada que ocultar.", "Aladdín", "La Bella y la Bestia", "Pocahontas"),
    ("Espejito, espejito mágico, ¿quién es la más bella del reino?", "Blancanieves y los siete enanitos", "La bella durmiente", "Cenicienta"),
    ("Quiero ser parte de ese mundo.", "La sirenita", "Pocahontas", "Vaiana"),
    ("Basta un poco de polvo de hada y un pensamiento feliz.", "Peter Pan", "Alicia en el país de las maravillas", "La sirenita"),
    ("Todos estamos locos aquí.", "Alicia en el país de las maravillas", "El mago de Oz", "Coraline"),
    ("¿Cuál es tu película de miedo favorita?", "Scream", "Destino final", "Actividad paranormal"),
    ("Uno, dos, Freddy viene a por ti.", "Pesadilla en Elm Street", "Viernes 13", "La matanza de Texas"),
    ("Hola, soy Chucky. ¿Quieres jugar?", "Chucky, el muñeco diabólico", "El juego del miedo", "Annabelle"),
    ("Sé lo que hicisteis el último verano.", "Sé lo que hicisteis el último verano", "Scream", "Destino final"),
    ("Regla número dos: doble tiro.", "Zombieland", "Guerra Mundial Z", "Resident Evil"),
    ("¿A quién vas a llamar? ¡Cazafantasmas!", "Los Cazafantasmas", "Los Goonies", "Gremlins"),
    ("Los Goonies nunca mueren.", "Los Goonies", "Cazafantasmas", "E.T., el extraterrestre"),
    ("Hay dos tipos de personas en este mundo, amigo: los que tienen un revólver cargado y los que cavan. Tú cavas.", "El bueno, el feo y el malo", "Por un puñado de dólares", "Río Bravo"),
    ("Todos nos lo merecemos, chico.", "Sin perdón", "El bueno, el feo y el malo", "Tombstone"),
    ("La D es muda.", "Django desencadenado", "Grindhouse", "Kill Bill"),
    ("¡Buenos días, princesa!", "La vida es bella", "Cadena perpetua", "El discurso del rey"),
    ("Olvídalo, Jake. Es Chinatown.", "Chinatown", "L.A. Confidential", "El padrino"),
    ("Nadie es perfecto.", "Con faldas y a lo loco", "Cantando bajo la lluvia", "El apartamento"),
    ("Solo canto bajo la lluvia.", "Cantando bajo la lluvia", "Con faldas y a lo loco", "Chicago"),
    ("Esa es solo tu opinión, tío.", "El gran Lebowski", "Snatch: cerdos y diamantes", "Old School: universidad de nada"),
    ("Al fin y al cabo, solo soy una chica, delante de un chico, pidiéndole que la quiera.", "Notting Hill", "Love Actually", "Cuatro bodas y un funeral"),
    ("Estas son algunas de mis cosas favoritas.", "Sonrisas y lágrimas", "Mary Poppins", "Chitty Chitty Bang Bang"),
    ("Un poco de azúcar ayuda a que la medicina baje mejor.", "Mary Poppins", "Sonrisas y lágrimas", "El regreso de Mary Poppins"),
]


# Frases sembradas antes con texto incompleto o datos equivocados: en vez de
# dejarlas huérfanas en cualquier base de datos donde ya se hubieran cargado
# (incluida la de producción), este comando las corrige in situ la próxima
# vez que se ejecute, buscándolas por su texto anterior.
QUOTE_FIXES = [
    ("Soy Iron Man.", "Yo soy Iron Man."),
    ("Soy el rey del mundo.", "¡Yo soy el rey del mundo!"),
    ("¡Tú no puedes manejar la verdad!", "¡Tú no puedes soportar la verdad!"),
    ("En un mundo antiguo... nace una leyenda.", "Son más que reglas, son más bien... pautas."),
    ("La verdad está ahí fuera.", "Aquí abajo, todos flotan."),
    ("Un pequeño paso para el hombre, un gran salto para la humanidad.", "Fracasar no es una opción."),
    ("No llores porque se terminó, sonríe porque sucedió.", "Si tú eres un pájaro, yo también soy un pájaro."),
    ("Yippee-ki-yay, hijo de perra.", "Si sangra, podemos matarlo."),
    ("Aquí hay algo que no encaja... y ese algo soy yo.", "De todos los bares de todas las ciudades del mundo, entra en el mío."),
    ("Solo hay una regla: no se habla del Club de la Lucha.", "La primera regla del Club de la Lucha es que no se habla del Club de la Lucha."),
    ("Vengadores... reunidos.", "Vengadores... reunidos."),
    ("Haz lo que sea necesario.", "Perfectamente equilibrado, como todo debería estar."),
    ("Que la Fuerza esté contigo, siempre... para todos nosotros.", "Que la Fuerza esté contigo. Siempre."),
    ("Elemental, querido Watson.", "¿Por qué nos caemos? Para aprender a levantarnos."),
]


class Command(BaseCommand):
    help = (
        "Carga las frases de ejemplo del juego 'Frases célebres' (Juegos). A "
        "diferencia de seed_content, no crea usuarios de ejemplo, así que es "
        "seguro ejecutarlo también contra una base de datos de producción."
    )

    def _apply_fixes(self):
        quotes_by_new_text = {q: (c, w1, w2) for q, c, w1, w2 in MOVIE_QUOTES}
        for old_text, new_text in QUOTE_FIXES:
            correct, wrong1, wrong2 = quotes_by_new_text[new_text]
            updated = MovieQuote.objects.filter(quote=old_text).update(
                quote=new_text, correct_title=correct, wrong_title_1=wrong1, wrong_title_2=wrong2,
            )
            if updated:
                self.stdout.write(self.style.WARNING(f"Corregida: «{old_text}» -> «{new_text}»"))

    def handle(self, *args, **options):
        self._apply_fixes()

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
