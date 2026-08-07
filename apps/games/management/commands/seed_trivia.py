from django.core.management.base import BaseCommand

from apps.games.models import TriviaQuestion, TrueFalseStatement

# Tanda inicial para Trivial, Emoji, Malas descripciones y Cuál tiene al
# actor/actriz. Cada tupla es (prompt, correcta, incorrecta_1, incorrecta_2,
# media_type) — igual que seed_quotes.py, sin límite real: desde el admin
# (Juegos → Preguntas de trivia) se pueden añadir tantas como se quiera.
TRIVIA_QUESTIONS = [
    ("¿Quién dirigió 'Origen' (Inception)?", "Christopher Nolan", "Steven Spielberg", "Denis Villeneuve", "movie"),
    ("¿En qué año se estrenó 'Star Wars: Una nueva esperanza'?", "1977", "1980", "1983", "movie"),
    ("¿Qué actor interpreta a Tony Stark / Iron Man?", "Robert Downey Jr.", "Chris Evans", "Chris Hemsworth", "movie"),
    ("¿Quién compuso la banda sonora de 'El padrino'?", "Nino Rota", "John Williams", "Ennio Morricone", "movie"),
    ("¿Qué estudio de animación hizo 'Toy Story'?", "Pixar", "DreamWorks", "Illumination", "movie"),
    ("¿Qué actriz interpreta a Hermione Granger?", "Emma Watson", "Emma Stone", "Emma Roberts", "movie"),
    ("¿En qué ciudad ficticia vive Batman?", "Gotham", "Metrópolis", "Central City", "movie"),
    ("¿Quién dirigió 'Pulp Fiction'?", "Quentin Tarantino", "Martin Scorsese", "David Fincher", "movie"),
    ("¿En qué saga es Frodo Bolsón el protagonista?", "El señor de los anillos", "Las crónicas de Narnia", "Harry Potter", "movie"),
    ("¿Cuál es el nombre real de Iron Man?", "Tony Stark", "Bruce Wayne", "Peter Parker", "movie"),
    ("¿Qué actor interpreta al Joker en 'Joker' (2019)?", "Joaquin Phoenix", "Heath Ledger", "Jared Leto", "movie"),
    ("¿En qué planeta se ambienta 'Dune'?", "Arrakis", "Pandora", "Tatooine", "movie"),
    ("¿Quién dirigió 'Titanic'?", "James Cameron", "Steven Spielberg", "Ridley Scott", "movie"),
    ("¿Qué actriz interpreta a Katniss en 'Los juegos del hambre'?", "Jennifer Lawrence", "Emma Stone", "Kristen Stewart", "movie"),
    ("¿En qué ciudad se ambienta principalmente 'Breaking Bad'?", "Albuquerque", "Denver", "Phoenix", "tv"),
    ("¿Cuántas temporadas tiene 'Juego de Tronos'?", "8", "7", "6", "tv"),
    ("¿Qué actor interpreta a Walter White en 'Breaking Bad'?", "Bryan Cranston", "Aaron Paul", "Giancarlo Esposito", "tv"),

    # 🎬 Películas
    ("¿En qué año se estrenó 'El padrino'?", "1972", "1974", "1969", "movie"),
    ("¿Cuál es la película más taquillera de la historia (sin ajustar por inflación)?", "Avatar", "Vengadores: Endgame", "Titanic", "movie"),
    ("¿A qué trilogía pertenece 'Las dos torres'?", "El señor de los anillos", "El hobbit", "Star Wars", "movie"),
    ("¿Cuál fue la primera película de Pixar?", "Toy Story", "Bichos", "Monstruos, S.A.", "movie"),
    ("¿Qué película ganó el primer Óscar a Mejor Película de la historia?", "Alas (Wings)", "Cavalcade", "Amanecer", "movie"),

    # 🎭 Actores y actrices
    ("¿Qué actriz ha ganado más premios Óscar a Mejor Actriz (4 en total)?", "Katharine Hepburn", "Meryl Streep", "Bette Davis", "movie"),
    ("¿Qué actriz tiene más nominaciones al Óscar de la historia?", "Meryl Streep", "Katharine Hepburn", "Judi Dench", "movie"),
    ("¿Qué actor interpreta a Jack Sparrow en 'Piratas del Caribe'?", "Johnny Depp", "Orlando Bloom", "Geoffrey Rush", "movie"),
    ("¿Qué actriz interpreta a la joven Furiosa en 'Furiosa: De la saga Mad Max'?", "Anya Taylor-Joy", "Charlize Theron", "Margot Robbie", "movie"),
    ("¿Qué actor ganó el Óscar a Mejor Actor por 'El renacido'?", "Leonardo DiCaprio", "Matt Damon", "Bryan Cranston", "movie"),

    # 🎥 Directores
    ("¿Quién dirigió 'Tiburón' (Jaws)?", "Steven Spielberg", "George Lucas", "Ridley Scott", "movie"),
    ("¿Quién dirigió la trilogía original de 'El señor de los anillos'?", "Peter Jackson", "Guillermo del Toro", "James Cameron", "movie"),
    ("¿Qué director es conocido por sus planos simétricos y películas como 'El gran hotel Budapest'?", "Wes Anderson", "Tim Burton", "Wong Kar-wai", "movie"),
    ("¿Quién dirigió 'Parásitos'?", "Bong Joon-ho", "Park Chan-wook", "Kim Ki-duk", "movie"),
    ("¿Quién fue la primera mujer en ganar el Óscar a Mejor Director/a?", "Kathryn Bigelow", "Sofia Coppola", "Greta Gerwig", "movie"),

    # 🎼 Bandas sonoras
    ("¿Quién compuso la banda sonora de 'Star Wars'?", "John Williams", "Hans Zimmer", "Danny Elfman", "movie"),
    ("¿Quién compuso la banda sonora de 'El rey león' (1994)?", "Hans Zimmer", "Alan Menken", "John Williams", "movie"),
    ("¿Quién compuso la banda sonora de 'Interestelar'?", "Hans Zimmer", "John Williams", "Thomas Newman", "movie"),
    ("¿Qué compositor firma la música de la mayoría de películas de Christopher Nolan?", "Hans Zimmer", "John Williams", "Alexandre Desplat", "movie"),
    ("¿Quién compuso la banda sonora de 'Cadena perpetua'?", "Thomas Newman", "Hans Zimmer", "James Horner", "movie"),

    # 🏆 Premios
    ("¿Cómo se llaman los premios de cine más importantes de España?", "Goya", "Feroz", "Fotogramas de Plata", "movie"),
    ("¿En qué país se celebra el Festival de Cannes?", "Francia", "Italia", "España", "movie"),
    ("¿Qué festival de cine entrega la Palma de Oro?", "Cannes", "Venecia", "Berlín", "movie"),
    ("¿Qué festival de cine entrega el León de Oro?", "Venecia", "Cannes", "Berlín", "movie"),
    ("¿Qué festival de cine entrega el Oso de Oro?", "Berlín", "Venecia", "Cannes", "movie"),

    # 📅 Años de estreno
    ("¿En qué año se estrenó la primera película de Harry Potter?", "2001", "1999", "2003", "movie"),
    ("¿En qué año se estrenó 'Matrix'?", "1999", "1997", "2001", "movie"),
    ("¿En qué año se estrenó 'Parque Jurásico'?", "1993", "1991", "1995", "movie"),
    ("¿En qué año se estrenó 'Toy Story', la primera película de Pixar?", "1995", "1993", "1997", "movie"),
    ("¿En qué año se estrenó 'El rey león' original?", "1994", "1992", "1996", "movie"),

    # 🌍 Cine por países
    ("¿De qué país es originaria la industria de cine conocida como 'Bollywood'?", "India", "Pakistán", "Bangladés", "movie"),
    ("¿De qué país es 'Parásitos', ganadora del Óscar a Mejor Película en 2020?", "Corea del Sur", "Japón", "China", "movie"),
    ("¿De qué país es el director Pedro Almodóvar?", "España", "México", "Argentina", "movie"),
    ("¿De qué país son los estudios de animación como Ghibli?", "Japón", "Corea del Sur", "China", "movie"),
    ("¿De qué país es 'Amélie'?", "Francia", "Bélgica", "Italia", "movie"),

    # 📺 Series
    ("¿En qué plataforma se estrenó originalmente 'Stranger Things'?", "Netflix", "HBO Max", "Amazon Prime Video", "tv"),
    ("¿Cuántas temporadas tiene 'Breaking Bad'?", "5", "6", "4", "tv"),
    ("¿En qué ciudad se ambienta 'Friends'?", "Nueva York", "Los Ángeles", "Chicago", "tv"),
    ("¿Qué actor interpreta a Jon Nieve en 'Juego de Tronos'?", "Kit Harington", "Richard Madden", "Alfie Allen", "tv"),
    ("¿En qué década se ambienta 'Stranger Things'?", "Los 80", "Los 90", "Los 70", "tv"),
]

# Cada emoji separado por un espacio: el juego los revela de uno en uno, no
# todos a la vez (ver apps/games/views.py, emoji_game).
EMOJI_QUESTIONS = [
    ("🦁 👑", "El rey león", "Madagascar", "Kung Fu Panda", "movie"),
    ("🕷️ 🧑", "Spider-Man", "Venom", "Los 4 Fantásticos", "movie"),
    ("🧊 👸 ❄️", "Frozen: El reino del hielo", "Blancanieves y los siete enanitos", "La sirenita", "movie"),
    ("🦈 🌊", "Tiburón", "Deep Blue Sea", "Piraña 3D", "movie"),
    ("🚢 🧊 💔", "Titanic", "Náufrago", "Poseidón", "movie"),
    ("🧙‍♂️ 💍", "El señor de los anillos", "Harry Potter", "Merlín", "movie"),
    ("🕶️ 💊 💊", "Matrix", "Origen", "El show de Truman", "movie"),
    ("🦖 🏝️", "Parque Jurásico", "King Kong", "Godzilla", "movie"),
    ("👻 🚫 👻", "Los Cazafantasmas", "Casper", "Poltergeist", "movie"),
    ("🐟 🔍", "Buscando a Nemo", "Buscando a Dory", "Shark Tale", "movie"),
    ("🍫 🏭", "Charlie y la fábrica de chocolate", "Los Croods", "Ratatouille", "movie"),
    ("🤖 ❤️ 🌱", "Wall-E", "Big Hero 6", "Terminator", "movie"),
    ("🧑‍🚀 🌽 🚀", "Interestelar", "Marte (The Martian)", "Gravedad", "movie"),
    ("🧪 🧢 🔵", "Breaking Bad", "Ozark", "The Wire", "tv"),
    ("🐉 🔥 👑", "Juego de Tronos", "La Casa del Dragón", "Vikingos", "tv"),
    ("💰 🎭 🔴", "La Casa de Papel", "Sky Rojo", "Élite", "tv"),
]

BAD_DESCRIPTION_QUESTIONS = [
    ("Un pez payaso muy nervioso cruza medio océano porque su hijo se ha perdido.", "Buscando a Nemo", "Buscando a Dory", "La vida de Pi", "movie"),
    ("Un tiburón gigante le arruina el verano a todo un pueblo de playa.", "Tiburón", "Piraña 3D", "Deep Blue Sea", "movie"),
    ("Un niño con gafas descubre que es mago y va a un colegio raro con escaleras que se mueven solas.", "Harry Potter y la piedra filosofal", "Las crónicas de Narnia: El león, la bruja y el armario", "Percy Jackson y el ladrón del rayo", "movie"),
    ("Un barco enorme que 'ni Dios podía hundir' choca contra un cubito de hielo gigante.", "Titanic", "Poseidón", "Náufrago", "movie"),
    ("Un robot solitario limpia basura durante 700 años hasta que se enamora de otro robot más moderno que él.", "Wall-E", "Big Hero 6", "Terminator 2: El juicio final", "movie"),
    ("Un hobbit muy bajito tiene que caminar kilómetros y kilómetros para tirar un anillo a un volcán.", "El señor de los anillos: La comunidad del anillo", "El hobbit: Un viaje inesperado", "Harry Potter y las reliquias de la muerte: Parte 2", "movie"),
    ("Un león bebé se va de casa por un malentendido familiar y vuelve de adulto para recuperar su trono.", "El rey león", "Madagascar", "Tarzán", "movie"),
    ("Un empresario se disfraza de murciélago por las noches para pegar a delincuentes en su ciudad.", "Batman Begins", "El caballero oscuro", "Watchmen", "movie"),
    ("Unos cuantos superhéroes se juntan para pelear contra un señor morado que quiere chasquear los dedos.", "Vengadores: Infinity War", "Vengadores: Endgame", "Los Vengadores", "movie"),
    ("Un arqueólogo con sombrero y látigo se pasa la película esquivando trampas y nazis por reliquias antiguas.", "En busca del arca perdida", "El código Da Vinci", "La momia", "movie"),
    ("Un payaso con el maquillaje muy corrido decide que la ciudad se merece un poco de caos.", "El caballero oscuro", "Joker", "It", "movie"),
    ("Una familia de superhéroes intenta llevar una vida normal en los suburbios sin que nadie note sus poderes.", "Los Increíbles", "Big Hero 6", "Sky High: Escuela de Superhéroes", "movie"),
    ("Un profesor de química se pone a cocinar algo que no es precisamente para el instituto.", "Breaking Bad", "Ozark", "Weeds", "tv"),
    ("Un grupo de ladrones con monos rojos y máscaras de un pintor español se atrincheran en la Fábrica de Moneda y Timbre.", "La Casa de Papel", "Sky Rojo", "Vis a vis", "tv"),
    ("Varias familias nobles se pelean por una silla hecha de espadas mientras se acerca un invierno muy largo.", "Juego de Tronos", "La Casa del Dragón", "Vikingos", "tv"),
]

# Cuál tiene al actor/actriz: sin `image_url` de partida (no hay una fuente
# fiable de fotos ya alojada en el proyecto) — se puede añadir luego desde
# el admin sin tocar código.
ACTOR_QUESTIONS = [
    ("Robert Downey Jr.", "Iron Man", "Batman Begins", "El hombre de acero", "movie"),
    ("Scarlett Johansson", "Vengadores: Endgame", "Wonder Woman", "Capitana Marvel", "movie"),
    ("Leonardo DiCaprio", "Titanic", "Gladiator", "300", "movie"),
    ("Meryl Streep", "El diablo viste de Prada", "Erin Brockovich", "Kill Bill", "movie"),
    ("Tom Hanks", "Forrest Gump", "El padrino", "Rocky", "movie"),
    ("Keanu Reeves", "Matrix", "El señor de los anillos: La comunidad del anillo", "Star Wars: Una nueva esperanza", "movie"),
    ("Emma Watson", "Harry Potter y la piedra filosofal", "Crepúsculo", "Los juegos del hambre", "movie"),
    ("Morgan Freeman", "Cadena perpetua", "El indomable Will Hunting", "Forrest Gump", "movie"),
    ("Al Pacino", "El padrino", "Uno de los nuestros", "Toro salvaje", "movie"),
    ("Heath Ledger", "El caballero oscuro", "Joker", "Batman Begins", "movie"),
    ("Jennifer Lawrence", "Los juegos del hambre", "Crepúsculo", "Divergente", "movie"),
    ("Samuel L. Jackson", "Pulp Fiction", "El padrino", "Uno de los nuestros", "movie"),
    ("Margot Robbie", "El lobo de Wall Street", "Erin Brockovich", "El diablo viste de Prada", "movie"),
    ("Bryan Cranston", "Breaking Bad", "The Wire", "Ozark", "tv"),
    ("Millie Bobby Brown", "Stranger Things", "El juego del calamar", "Élite", "tv"),
    ("Emilia Clarke", "Juego de Tronos", "La Casa del Dragón", "Vikingos", "tv"),
]

TRUE_FALSE_STATEMENTS = [
    ("'Titanic' ganó 11 premios Óscar.", True),
    ("Leonardo DiCaprio ganó su primer Óscar por 'Titanic'.", False),
    ("'El padrino' está basada en una novela de Mario Puzo.", True),
    ("Pixar hizo 'Shrek'.", False),
    ("'Breaking Bad' se ambienta en Albuquerque, Nuevo México.", True),
    ("Heath Ledger ganó un Óscar póstumo por su papel del Joker.", True),
    ("'Star Wars: Una nueva esperanza' se estrenó en 1977.", True),
    ("'Parásitos' fue la primera película de habla no inglesa en ganar el Óscar a Mejor Película.", True),
    ("Walt Disney puso la voz original de Mickey Mouse.", True),
    ("'Matrix' está protagonizada por Brad Pitt.", False),
    ("'Juego de Tronos' está basada en los libros de George R. R. Martin.", True),
    ("La saga 'El señor de los anillos' transcurre en un planeta llamado Arrakis.", False),
    ("'Coco' de Pixar está ambientada en el Día de Muertos mexicano.", True),
    ("'La Casa de Papel' es una serie francesa.", False),
    ("Tom Hanks puso la voz de Woody en 'Toy Story'.", True),
    ("'El caballero oscuro' fue dirigida por Tim Burton.", False),
    ("'Stranger Things' se ambienta en los años 90.", False),
    ("Christopher Nolan dirigió 'Interestelar'.", True),
]


class Command(BaseCommand):
    help = (
        "Carga preguntas de ejemplo para Trivial, Emoji, Malas descripciones, "
        "Cuál tiene al actor/actriz y Verdadero o falso. Seguro de ejecutar "
        "también contra producción — no crea usuarios de ejemplo."
    )

    def _seed_trivia(self, category, questions):
        created_count = 0
        for prompt, correct, wrong1, wrong2, media_type in questions:
            _, created = TriviaQuestion.objects.get_or_create(
                category=category, prompt=prompt,
                defaults={
                    "media_type": media_type, "correct_answer": correct,
                    "wrong_answer_1": wrong1, "wrong_answer_2": wrong2,
                },
            )
            if created:
                created_count += 1
        return created_count

    def _seed_true_false(self):
        created_count = 0
        for statement, is_true in TRUE_FALSE_STATEMENTS:
            _, created = TrueFalseStatement.objects.get_or_create(
                statement=statement, defaults={"is_true": is_true},
            )
            if created:
                created_count += 1
        return created_count

    def handle(self, *args, **options):
        trivia_created = self._seed_trivia(TriviaQuestion.Category.TRIVIA, TRIVIA_QUESTIONS)
        emoji_created = self._seed_trivia(TriviaQuestion.Category.EMOJI, EMOJI_QUESTIONS)
        bad_description_created = self._seed_trivia(TriviaQuestion.Category.BAD_DESCRIPTION, BAD_DESCRIPTION_QUESTIONS)
        actor_created = self._seed_trivia(TriviaQuestion.Category.ACTOR, ACTOR_QUESTIONS)
        true_false_created = self._seed_true_false()

        self.stdout.write(self.style.SUCCESS(
            f"Seed de trivia completado: {trivia_created} de Trivial, {emoji_created} de Emoji, "
            f"{bad_description_created} de Malas descripciones, {actor_created} de Actor, "
            f"{true_false_created} de Verdadero o falso (el resto ya existían)."
        ))
