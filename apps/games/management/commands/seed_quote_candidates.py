from django.core.management.base import BaseCommand

from apps.games.models import MovieQuote, QuoteCandidate

# Primera tanda de candidatas para el panel de curación (Juegos > Frases
# célebres > 🎬 Curar frases célebres), sacada de los títulos mejor
# valorados de tu lista de Top Secret. Cada opción es una frase real y
# verificada (nunca inventada) con sus propias dos opciones incorrectas,
# elegidas para que encajen en tono/tema y el acierto no sea obvio.
#
# Ejecutar de nuevo este comando con más tandas añadidas aquí abajo es
# seguro: get_or_create por título evita duplicar candidatas ya generadas
# (aunque ya estén resueltas/descartadas, no se tocan sus opciones).
BATCH_1 = [
    ("Arcane", MovieQuote.MediaType.TV, "10.0", [
        {"quote": "Zaun no necesita un héroe. Necesita un monstruo.", "wrong1": "The Boys", "wrong2": "Gotham"},
        {"quote": "No necesitas que te salven. Necesitas poder.", "wrong1": "Gotham", "wrong2": "Castlevania"},
        {"quote": "Renuncié a la esperanza a cambio de poder. Y no me arrepiento.", "wrong1": "The Boys", "wrong2": "Watchmen"},
        {"quote": "¡Sorpresa, cabrones!", "wrong1": "The Boys", "wrong2": "Peaky Blinders"},
    ]),
    ("La La Land", MovieQuote.MediaType.MOVIE, "9.7", [
        {"quote": "Aquí va por los que sueñan, aunque parezcan un poco locos.", "wrong1": "El Gran Showman", "wrong2": "Cantando bajo la lluvia"},
        {"quote": "Siempre serás la mujer que amé.", "wrong1": "El Diario de Noa", "wrong2": "La Peor Persona del Mundo"},
    ]),
    ("El Conde de Montecristo", MovieQuote.MediaType.MOVIE, "9.5", [
        {"quote": "Toda la sabiduría humana está contenida en estas dos palabras: esperar y confiar.", "wrong1": "Cadena Perpetua", "wrong2": "Gladiator"},
    ]),
    ("Gran Torino", MovieQuote.MediaType.MOVIE, "9.3", [
        {"quote": "Sal de mi jardín.", "wrong1": "Million Dollar Baby", "wrong2": "Cadena Perpetua"},
    ]),
    ("Your Name", MovieQuote.MediaType.MOVIE, "9.1", [
        {"quote": "¿Cuál era tu nombre?", "wrong1": "5 Cm Per Second", "wrong2": "Weathering With You"},
    ]),
    ("Batman (El Caballero Oscuro)", MovieQuote.MediaType.MOVIE, "9.0", [
        {"quote": "¿Por qué tan serio?", "wrong1": "The Batman", "wrong2": "Batman: The Dark Knight Rises"},
        {"quote": "O mueres como un héroe, o vives lo suficiente para verte convertido en villano.", "wrong1": "Batman Begins", "wrong2": "The Batman"},
    ]),
    ("Batman Begins", MovieQuote.MediaType.MOVIE, "7.3", [
        {"quote": "No es quien soy por dentro, sino lo que hago lo que me define.", "wrong1": "Batman (El Caballero Oscuro)", "wrong2": "The Batman"},
    ]),
    ("Hasta El Último Hombre", MovieQuote.MediaType.MOVIE, "8.7", [
        {"quote": "Señor, ayúdame a salvar uno más.", "wrong1": "Malditos Bastardos", "wrong2": "12 Años De Esclavitud"},
    ]),
    ("El Sexto Sentido", MovieQuote.MediaType.MOVIE, "8.6", [
        {"quote": "Veo gente muerta.", "wrong1": "Los Otros", "wrong2": "El Resplandor"},
    ]),
    ("Kill Bill: The Whole Bloody Affair", MovieQuote.MediaType.MOVIE, "8.6", [
        {"quote": "Cinco Puntos, la Técnica del Corazón Explosivo.", "wrong1": "Kill Bill: Volumen 1", "wrong2": "Kill Bill: Volumen 2"},
        {"quote": "Esa mujer merece su venganza, y nosotros merecemos morir.", "wrong1": "Kill Bill: Volumen 1", "wrong2": "Kill Bill: Volumen 2"},
    ]),
    ("Oldboy", MovieQuote.MediaType.MOVIE, "8.6", [
        {"quote": "Ríete y el mundo reirá contigo. Llora y llorarás solo.", "wrong1": "Sospechosos Habituales", "wrong2": "El Cuervo (De Brandon Lee)"},
        {"quote": "Aunque sea un monstruo, ¿no tengo derecho a vivir?", "wrong1": "El Cuervo (De Brandon Lee)", "wrong2": "Infiltrados"},
    ]),
    ("Donnie Darko", MovieQuote.MediaType.MOVIE, "8.5", [
        {"quote": "28 días, 6 horas, 42 minutos, 12 segundos. Ese será el fin del mundo.", "wrong1": "28 Años Después", "wrong2": "28 Semanas Despues"},
    ]),
    ("Star Wars: Episodio III - La Venganza De Los Sith", MovieQuote.MediaType.MOVIE, "8.5", [
        {"quote": "¡Desde mi punto de vista, los Jedi son malvados!", "wrong1": "Star Wars: Episodio IV - Una Nueva Esperanza", "wrong2": "Star Wars: Episodio VI - El Retorno Del Jedi"},
        {"quote": "¡Tú eras el elegido!", "wrong1": "Star Wars: Episodio IV - Una Nueva Esperanza", "wrong2": "Star Wars: Episodio VI - El Retorno Del Jedi"},
    ]),
    ("V De Vendeta", MovieQuote.MediaType.MOVIE, "8.4", [
        {"quote": "Recuerda, recuerda el cinco de noviembre.", "wrong1": "300", "wrong2": "Watchmen"},
        {"quote": "Las ideas son a prueba de balas.", "wrong1": "Watchmen", "wrong2": "La Liga De Los Hombres Extraordinarios"},
    ]),
    ("Marvel: Avengers: Endgame", MovieQuote.MediaType.MOVIE, "8.4", [
        {"quote": "Cueste lo que cueste.", "wrong1": "Marvel: Avengers: Infinity War", "wrong2": "Marvel: Captain America: Civil War"},
        {"quote": "Yo soy Iron Man.", "wrong1": "Marvel: Iron Man 1", "wrong2": "Marvel: Avengers: Infinity War"},
    ]),
    ("Star Wars: The Clone Wars", MovieQuote.MediaType.TV, "8.4", [
        {"quote": "Buenos soldados siguen órdenes.", "wrong1": "Star Wars: Rebels", "wrong2": "Star Wars: Cronicas Del Imperio"},
    ]),
    ("Constantine", MovieQuote.MediaType.MOVIE, "8.3", [
        {"quote": "Yo ya he estado en el infierno. Una vez.", "wrong1": "El Abogado Del Diablo", "wrong2": "Ghost Rider"},
    ]),
    ("Gladiator", MovieQuote.MediaType.MOVIE, "8.3", [
        {"quote": "Mi nombre es Máximo Décimo Meridio.", "wrong1": "Troya", "wrong2": "300"},
        {"quote": "En esta vida o en la próxima, te prometo que te veré.", "wrong1": "Troya", "wrong2": "300"},
        {"quote": "¿No estáis entretenidos?", "wrong1": "300", "wrong2": "Troya"},
    ]),
    ("Cadena Perpetua", MovieQuote.MediaType.MOVIE, "8.3", [
        {"quote": "O te ocupas de vivir, o te ocupas de morir.", "wrong1": "El Conde de Montecristo", "wrong2": "El Club De La Lucha"},
        {"quote": "La esperanza es buena, quizá lo mejor, y ninguna cosa buena muere jamás.", "wrong1": "El Conde de Montecristo", "wrong2": "La Milla Verde"},
    ]),
]


class Command(BaseCommand):
    help = "Genera candidatas de frases célebres para curar desde el admin (Juegos > Frases célebres > Curar)."

    def handle(self, *args, **options):
        created = 0
        for title, media_type, rating, options in BATCH_1:
            obj, was_created = QuoteCandidate.objects.get_or_create(
                title=title,
                defaults={"media_type": media_type, "source_rating": rating, "options": options},
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"Candidata creada: {title} ({len(options)} opciones)"))
            else:
                self.stdout.write(f"Ya existía candidata para «{title}», no se toca.")

        self.stdout.write(self.style.SUCCESS(f"Listo: {created} candidatas nuevas de {len(BATCH_1)} en esta tanda."))
