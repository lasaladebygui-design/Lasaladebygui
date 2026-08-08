from django.conf import settings
from django.core.management.base import BaseCommand

from apps.games.models import PersonalityAnswer, PersonalityCharacter, PersonalityQuestion
from apps.movies.services import MovieAPIError, tmdb_search_person

# Foto de perfil de quien interpretó a cada personaje (TMDb no tiene fotos
# de personajes de ficción, así que se usa la del actor/actriz real). Nikki
# Freeman se queda fuera a propósito: sin certeza fiable del reparto, mejor
# sin foto que con una equivocada — se puede añadir a mano desde el admin.
ACTOR_FOR_CHARACTER = {
    "Jinx": "Ella Purnell",
    "Joker": "Heath Ledger",
    "Michael Corleone": "Al Pacino",
    "Harley Quinn": "Margot Robbie",
    "V": "Hugo Weaving",
    "Katniss Everdeen": "Jennifer Lawrence",
    "Steve Rogers (Capitán América)": "Chris Evans",
    "Mia Dolan": "Emma Stone",
    "Sam Wheat": "Patrick Swayze",
    "Elle Woods": "Reese Witherspoon",
    "Miranda Priestly": "Meryl Streep",
}

# 12 personajes de cine (y uno de serie/videojuego a propósito: Jinx) que
# cubren registros bien distintos — no solo acción: también romance,
# comedia y drama. Cada tupla es (nombre, película/serie, descripción).
CHARACTERS = [
    ("Jinx", "Arcane", "🔫 Caos con purpurina. Vives con el acelerador a fondo, sin frenos, y lo que a otros les da miedo a ti te da energía. Detrás de la broma casi siempre hay algo roto que nunca terminó de curar — pero eso no te va a detener."),
    ("Joker", "El caballero oscuro", "🃏 No juegas según las reglas de nadie, ni siquiera las tuyas. El caos no te asusta, te parece la única verdad honesta en un mundo que finge tener orden."),
    ("Michael Corleone", "El padrino", "🕴️ Frío cuando hace falta, paciente siempre. No actúas por rabia, actúas por cálculo — y para cuando alguien se da cuenta de tu jugada, ya es tarde."),
    ("Harley Quinn", "Escuadrón Suicida", "💥 Amas con toda el alma, incluso cuando no deberías. Impredecible, leal hasta el extremo, y capaz de convertir cualquier desastre en una fiesta."),
    ("V", "V de Vendetta", "🎭 Crees en las ideas más que en ti mismo. Estás dispuesto a perderlo todo — incluso tu nombre — por algo en lo que de verdad crees."),
    ("Katniss Everdeen", "Los juegos del hambre", "🏹 No pediste ser el centro de nada, pero cuando alguien que quieres está en peligro, no hay sistema ni autoridad que te pare."),
    ("Steve Rogers (Capitán América)", "Vengadores", "🛡️ Haces lo correcto aunque signifique hacerlo solo. Tu brújula moral no negocia, ni siquiera cuando sería mucho más fácil mirar hacia otro lado."),
    ("Nikki Freeman", "Obsession", "🔪 Cuando quieres a alguien, lo quieres entero — y no llevas nada bien que se aleje. Ves la lealtad en blanco y negro: o estás conmigo del todo, o me has traicionado. Lo llamas amor; para el resto es una obsesión."),
    ("Mia Dolan", "La La Land", "🌆 Persigues lo que quieres aunque el precio sea alto y el camino solitario. Prefieres el 'y si...' de haberlo intentado a la comodidad de no haberlo hecho."),
    ("Sam Wheat", "Ghost", "👻 Sientes todo por dentro y lo dices tarde, o casi nunca. Lo que más te importa no lo gritas, lo proteges — aunque nunca llegue a enterarse del todo."),
    ("Elle Woods", "Legalmente rubia", "💗 Te subestiman constantemente y lo conviertes en tu mejor arma. Amable primero, pero no confundas eso con ser blanda — trabajas el doble y lo demuestras."),
    ("Miranda Priestly", "El diablo viste de Prada", "👠 No pides perdón por saber lo que quieres. Los resultados hablan por ti, y no tienes ningún interés en gustarle a todo el mundo."),
]

# Cada pregunta: (texto, [(texto_respuesta, nombre_personaje), x4]). En vez
# de dilemas de la vida real, cada una plantea una decisión propia de una
# escena de película (atracos, batallas, juicios, dobles vidas...) — la
# respuesta que elijas es la que tomaría tu personaje en esa misma escena.
QUESTIONS = [
    ("Un atraco perfecto se tuerce en el último segundo y un miembro del equipo se queda atrás. ¿Qué haces?", [
        ("Vuelvo a por él aunque ponga en peligro todo el golpe", "Steve Rogers (Capitán América)"),
        ("Sigo con el plan tal y como estaba pensado, sin rodeos", "Michael Corleone"),
        ("Convierto el caos en la mejor parte del plan — nunca sale como se espera, y mejor así", "Jinx"),
        ("Le prendo fuego a todo el botín y me voy andando; ver arder algo bonito no tiene precio", "Joker"),
    ]),
    ("Te ofrecen dirigir el negocio familiar, pero significa dejar atrás tu propia vida para siempre. ¿Qué haces?", [
        ("Lo acepto sin dudar, la familia va antes que cualquier otra cosa", "Michael Corleone"),
        ("Lo rechazo — mi vida y mis sueños no se negocian con nadie", "Mia Dolan"),
        ("Lo acepto solo si la persona que quiero viene conmigo, no pienso elegir", "Nikki Freeman"),
        ("Pido tiempo — algo así no se decide con prisas", "Sam Wheat"),
    ]),
    ("El edificio se derrumba y solo da tiempo a salvar a una persona o completar la misión de semanas. ¿Qué haces?", [
        ("Salvo a la persona, siempre, sin pensarlo dos veces", "Steve Rogers (Capitán América)"),
        ("Completo la misión — hay cosas más grandes en juego que una sola vida", "Miranda Priestly"),
        ("Salvo a la persona Y encuentro la forma de salvar también la misión — no pienso elegir", "Nikki Freeman"),
        ("Dejo que decida el caos del momento — hay una belleza rara en perderlo todo de golpe", "Jinx"),
    ]),
    ("Estás infiltrado en la organización que llevas años intentando derribar, y te ofrecen un ascenso dentro de ella. ¿Qué haces?", [
        ("Lo acepto — cuanto más arriba llegue, más daño puedo hacerles desde dentro", "Katniss Everdeen"),
        ("Lo acepto y disfruto cada segundo del juego de dobles vidas", "Joker"),
        ("Lo acepto, es la jugada perfecta — nadie lo va a ver venir", "Michael Corleone"),
        ("Lo rechazo — mi lucha no necesita un cargo dentro de su sistema, necesita destruirlo entero", "V"),
    ]),
    ("En medio de una batalla campal, tu bando está a punto de perder. ¿Qué haces?", [
        ("Doy la cara al frente, aunque sea yo solo contra todos", "Steve Rogers (Capitán América)"),
        ("Lidero una última carga imposible, dando igual las probabilidades", "V"),
        ("Cambio de bando en el peor momento posible, solo por ver las caras", "Joker"),
        ("Convierto la derrota en el espectáculo más loco que se ha visto nunca", "Jinx"),
    ]),
    ("Descubres que la persona de la que te has enamorado en el trabajo esconde un secreto peligroso. ¿Qué haces?", [
        ("Me da igual el secreto, no pienso alejarme de esa persona jamás", "Nikki Freeman"),
        ("Lo guardo para mí y la protejo en silencio, aunque nunca llegue a saberlo", "Sam Wheat"),
        ("Se lo pregunto directamente, prefiero la verdad incómoda a la duda", "Katniss Everdeen"),
        ("Guardo el secreto — puede que me haga falta usarlo algún día", "Michael Corleone"),
    ]),
    ("Un rival profesional que te ha subestimado toda la vida te reta en público a demostrar quién vale más. ¿Qué haces?", [
        ("Le devuelvo la humillación con resultados, no con palabras", "Elle Woods"),
        ("Acepto el reto y me aseguro de que todos vean cómo pierde", "Miranda Priestly"),
        ("Convierto el reto en un caos tan grande que hasta se olvida de por qué empezó", "Harley Quinn"),
        ("Paso de él — no tengo nada que demostrarle a nadie", "V"),
    ]),
    ("Estás en el juicio que va a decidir tu futuro, y tienes la última palabra ante el jurado. ¿Qué dices?", [
        ("La verdad completa, aunque me condene a mí", "Katniss Everdeen"),
        ("Justo lo que hace falta para ganar el caso, ni una palabra de más", "Miranda Priestly"),
        ("Uso mi discurso para desmontar a todo el sistema desde dentro", "V"),
        ("Convierto mi defensa en el momento más memorable de la sala — que rían o que lloren, pero que no lo olviden", "Jinx"),
    ]),
    ("Un amigo cercano te pide que le ayudes a hacer algo que sabes que va a acabar mal para los dos. ¿Qué haces?", [
        ("Le ayudo de todas formas — la lealtad va antes que las consecuencias", "Harley Quinn"),
        ("Le digo que no, y le explico exactamente por qué", "Steve Rogers (Capitán América)"),
        ("Le ayudo, pero me aseguro de que me deba una grande", "Michael Corleone"),
        ("Le ayudo... y lo convierto en algo todavía más grande de lo que pedía", "Jinx"),
    ]),
    ("Todo sale mal en el peor segundo posible del momento más importante de tu vida (una boda, una final, un estreno). ¿Qué haces?", [
        ("Improviso algo que nadie esperaba y me lo paso mejor así", "Harley Quinn"),
        ("Sigo hasta el final aunque salga imperfecto, no pienso rendirme", "Mia Dolan"),
        ("Me río del desastre — si no me río, me hundo", "Jinx"),
        ("Lo convierto en parte del espectáculo, como si lo hubiera planeado así desde el principio", "Miranda Priestly"),
    ]),
    ("Alguien de tu propio equipo te traiciona en mitad de la misión más importante. ¿Cómo respondes?", [
        ("Corto por lo sano, sin venganza ni dramas, y sigo adelante", "Katniss Everdeen"),
        ("Nunca lo olvido, y algún día se lo hago pagar con calma", "Michael Corleone"),
        ("Le doy una segunda oportunidad, aunque sé que no debería", "Harley Quinn"),
        ("Lo convierto en un juego para ver qué más es capaz de hacer", "Joker"),
    ]),
    ("Tienes en las manos el plan perfecto para conseguir todo lo que siempre quisiste, pero el camino no es del todo limpio. ¿Qué haces?", [
        ("Lo rechazo, prefiero llegar despacio pero limpio", "Elle Woods"),
        ("Lo cojo sin dudar — los resultados hablan por sí solos", "Michael Corleone"),
        ("Lo cojo sin pensarlo dos veces — si de verdad quiero algo, no me importa cómo conseguirlo", "Nikki Freeman"),
        ("Lo rechazo, y de paso aviso a quien debería saberlo", "Katniss Everdeen"),
    ]),
    ("En la última escena de tu propia historia, ¿qué final eliges?", [
        ("El agridulce, el que deja algo pendiente", "Mia Dolan"),
        ("El feliz, aunque sea poco realista — me lo he ganado", "Elle Woods"),
        ("El que hace que el amor gane pase lo que pase, aunque tenga que imponerse", "Nikki Freeman"),
        ("El que hace que alguien lo sacrifique todo por una idea", "V"),
    ]),
    ("Diriges la reunión más tensa del año y algo sale terriblemente mal en directo delante de todos. ¿Qué haces?", [
        ("Mantengo la calma como si nada — el pánico no ayuda a nadie", "Steve Rogers (Capitán América)"),
        ("Subo la energía de la sala hasta que se olvidan de que algo iba mal", "Jinx"),
        ("Sigo trabajando el doble para arreglarlo, aunque todavía nadie lo note", "Elle Woods"),
        ("Tomo la decisión más dura sin pestañear — ya lidiaré con las quejas después", "Miranda Priestly"),
    ]),
    ("Descubres que podrías cambiar tu propio pasado, pero eso borraría a la persona en la que te has convertido. ¿Qué haces?", [
        ("Lo dejo tal cual — no cambiaría nada de lo que me ha hecho quien soy", "V"),
        ("Lo cambiaría todo con tal de recuperar a quien más quiero", "Sam Wheat"),
        ("Lo dejo tal cual, y reconstruyo lo que se rompa por el camino, más fuerte que antes", "Miranda Priestly"),
        ("Me da igual el pasado — lo único que importa es la próxima jugada", "Michael Corleone"),
    ]),
    ("En la persecución más importante de tu vida, tienes que elegir entre atrapar al culpable o salvar a un inocente en peligro. ¿Qué haces?", [
        ("Salvo al inocente, siempre — el culpable puede esperar", "Steve Rogers (Capitán América)"),
        ("Atrapo al culpable — es la única forma de que esto no vuelva a pasar", "Katniss Everdeen"),
        ("Encuentro la forma de hacer las dos cosas, cueste lo que cueste", "Nikki Freeman"),
        ("Uso el caos del momento a mi favor y desaparezco con lo que necesito", "Joker"),
    ]),
    ("Un mentor al que admirabas se revela como alguien completamente distinto a quien creías. ¿Qué haces?", [
        ("Le doy la espalda sin mirar atrás — la decepción no admite segundas partes", "Katniss Everdeen"),
        ("Sigo cerca, en silencio, procesándolo por dentro", "Sam Wheat"),
        ("Lo uso para aprender exactamente cómo NO quiero acabar siendo", "Elle Woods"),
        ("Me da igual quién sea de verdad — sigo el plan que ya tenía, con o sin él", "Michael Corleone"),
    ]),
    ("Si mañana desaparece de golpe todo lo que has construido hasta ahora, ¿qué haces?", [
        ("Empiezo de cero, sin mirar atrás", "Mia Dolan"),
        ("Lo reconstruyo exactamente igual, más fuerte que antes", "Miranda Priestly"),
        ("Me río, total, nada dura para siempre", "Jinx"),
        ("Busco a quien de verdad me importa antes que nada", "Sam Wheat"),
    ]),
]


class Command(BaseCommand):
    help = (
        "Carga los personajes y preguntas de 'Qué personaje eres'. Seguro de "
        "ejecutar también contra producción — no crea usuarios de ejemplo."
    )

    def _backfill_images(self, characters_by_name):
        if not settings.TMDB_API_KEY:
            return 0
        updated = 0
        for name, actor_name in ACTOR_FOR_CHARACTER.items():
            character = characters_by_name[name]
            if character.image_url:
                continue
            try:
                results = tmdb_search_person(actor_name)
            except MovieAPIError:
                continue
            if results and results[0].profile_url:
                character.image_url = results[0].profile_url
                character.save(update_fields=["image_url"])
                updated += 1
        return updated

    def handle(self, *args, **options):
        characters_by_name = {}
        created_characters = 0
        for order, (name, source, description) in enumerate(CHARACTERS):
            character, created = PersonalityCharacter.objects.get_or_create(
                name=name, defaults={"source": source, "description": description, "order": order},
            )
            characters_by_name[name] = character
            if created:
                created_characters += 1

        # Poda personajes de repartos anteriores (p. ej. Tony Stark antes de
        # cambiarlo por Nikki Freeman): si no, se quedan huérfanos en la
        # base de datos y sus respuestas viejas siguen apareciendo como
        # opción de más en la pregunta donde estaban, junto a la nueva.
        removed_characters = PersonalityCharacter.objects.exclude(name__in=characters_by_name.keys())
        removed_characters_count = removed_characters.count()
        removed_characters.delete()

        created_questions = 0
        created_answers = 0
        for order, (text, answers) in enumerate(QUESTIONS):
            question, created = PersonalityQuestion.objects.get_or_create(text=text, defaults={"order": order})
            if created:
                created_questions += 1
            elif question.order != order:
                question.order = order
                question.save(update_fields=["order"])
            valid_answer_texts = set()
            for answer_order, (answer_text, character_name) in enumerate(answers):
                valid_answer_texts.add(answer_text)
                _, answer_created = PersonalityAnswer.objects.get_or_create(
                    question=question, text=answer_text,
                    defaults={"character": characters_by_name[character_name], "order": answer_order},
                )
                if answer_created:
                    created_answers += 1
            # Poda respuestas de versiones anteriores de esta misma pregunta
            # (mismo motivo: si no, se acumulan opciones de más).
            question.answers.exclude(text__in=valid_answer_texts).delete()

        # Poda preguntas de versiones anteriores del cuestionario (p. ej. al
        # reescribir todo el texto de las 18 preguntas a decisiones de
        # película): si no, las viejas se quedan sueltas en la base de datos
        # y el test acaba con 36 preguntas en vez de 18.
        valid_question_texts = {text for text, _ in QUESTIONS}
        removed_questions = PersonalityQuestion.objects.exclude(text__in=valid_question_texts)
        removed_questions_count = removed_questions.count()
        removed_questions.delete()

        images_updated = self._backfill_images(characters_by_name)

        self.stdout.write(self.style.SUCCESS(
            f"Seed de 'Qué personaje eres' completado: {created_characters} personajes, "
            f"{created_questions} preguntas, {created_answers} respuestas nuevas, "
            f"{removed_characters_count} personajes obsoletos podados, "
            f"{removed_questions_count} preguntas obsoletas podadas y "
            f"{images_updated} fotos de personajes actualizadas (el resto ya existía)."
        ))
