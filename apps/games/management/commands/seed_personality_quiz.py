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

# Cada pregunta: (texto, [(texto_respuesta, nombre_personaje), x4]). Mezcla
# a propósito dilemas "locos" (fantásticos, imposibles: viajar en el
# tiempo, un genio, zombis) con dilemas "cotidianos" (una cola del
# supermercado, un compañero de trabajo, un coche mal aparcado) — la
# respuesta que elijas revela tu forma de ser tanto en lo absurdo como en
# lo del día a día, no solo en la gran escena de acción.
QUESTIONS = [
    ("Te despiertas con la capacidad de leer la mente de cualquiera que mires, pero solo te dura un día. ¿Qué haces con ese poder?", [
        ("Me planto delante de la persona que quiero y miro. Necesito saberlo ya", "Nikki Freeman"),
        ("Averiguo quién me la está jugando antes de que sea tarde", "Michael Corleone"),
        ("Voy gritando en voz alta lo que piensa cada uno. El caos que se arma vale la pena", "Joker"),
        ("Busco a quien lo está pasando mal en silencio y no lo dice", "Katniss Everdeen"),
    ]),
    ("Llevas media hora en la cola del supermercado y alguien se cuela justo delante de ti sin pedir perdón. ¿Qué haces?", [
        ("Se lo digo delante de todos, sin bajar la voz", "Miranda Priestly"),
        ("Lo dejo pasar. No merece la pena", "Sam Wheat"),
        ("Se lo digo con una sonrisa tan amable que no sabe si lo he insultado o no", "Elle Woods"),
        ("Me cuelo yo en otra fila, más rápido que ellos", "Harley Quinn"),
    ]),
    ("Un genio te concede cualquier deseo, pero el precio es que otra persona pierde exactamente lo mismo que tú ganas. ¿Qué pides?", [
        ("Pido que esa persona sea mía para siempre. Que pague quien tenga que pagar", "Nikki Freeman"),
        ("No pido nada. Ningún deseo vale hacerle eso a otro", "Steve Rogers (Capitán América)"),
        ("Pido ir siempre un paso por delante. El precio es cosa suya", "Michael Corleone"),
        ("Pido que nada de lo que construya se derrumbe nunca. Lo demás no es asunto mío", "Miranda Priestly"),
    ]),
    ("En una reunión importante, un compañero presenta como suya una idea que era completamente tuya. ¿Qué haces?", [
        ("Lo dejo pasar por ahora. No vuelve a pasarme", "Michael Corleone"),
        ("Lo corto ahí mismo, delante de todos", "Katniss Everdeen"),
        ("Aprieto el doble. La próxima idea no me la va a poder tocar nadie", "Elle Woods"),
        ("Convierto la reunión en un caos tan grande que hasta se olvidan de la idea", "Jinx"),
    ]),
    ("Descubres que puedes viajar en el tiempo, pero solo una vez, y sin posibilidad de volver a este presente. ¿Qué haces?", [
        ("No lo uso. No cambiaría nada de lo que me hizo ser quien soy", "V"),
        ("Vuelvo al momento que más lo necesité, aunque pierda todo lo demás", "Sam Wheat"),
        ("Arreglo el único error que de verdad me pesa. Lo demás lo reconstruyo, más fuerte", "Miranda Priestly"),
        ("Salto sin pensarlo. La aventura es la aventura, esté donde esté", "Harley Quinn"),
    ]),
    ("Un amigo te pide que le cubras con una mentira que sabes que puede acabar mal para los dos. ¿Qué haces?", [
        ("Le cubro sin dudarlo. La lealtad va antes que las consecuencias", "Harley Quinn"),
        ("Le digo que no, y le explico por qué", "Steve Rogers (Capitán América)"),
        ("Le cubro... y de paso lo lío todavía más. Por diversión", "Jinx"),
        ("Le pido la verdad entera antes de decidir nada", "Katniss Everdeen"),
    ]),
    ("Te ofrecen la inmortalidad, pero verás morir, uno a uno, a todos los que quieres. ¿Aceptas?", [
        ("La rechazo. Prefiero poco tiempo con ellos que una eternidad sin ellos", "Sam Wheat"),
        ("La acepto, y uso cada segundo extra para proteger a los que me quedan", "Steve Rogers (Capitán América)"),
        ("La rechazo. Ninguna ambición vale ese precio", "V"),
        ("La acepto sin pensarlo. Lo que dure el resto no es mi problema", "Joker"),
    ]),
    ("El wifi se cae justo antes de la videollamada más importante de tu año. ¿Qué haces?", [
        ("Improviso algo que nadie esperaba y me acabo robando la reunión igual", "Harley Quinn"),
        ("Me río del caos. Si no me río, me hundo", "Jinx"),
        ("Aprovecho el silencio para pensar mejor lo que quiero decir", "Mia Dolan"),
        ("Ya tenía un plan B. Siempre lo tengo", "Michael Corleone"),
    ]),
    ("Un meteorito va a caer sobre tu ciudad en 24 horas y solo hay sitio para salvar a un puñado de personas. ¿A quién salvas?", [
        ("A quien lo esté pasando mal en silencio, aunque nadie más se haya fijado", "Katniss Everdeen"),
        ("A quien de verdad me importa. Antes que a nadie más", "Sam Wheat"),
        ("A quien crea capaz de reconstruir algo después de esto", "Miranda Priestly"),
        ("Monto un último espectáculo con quien quede. Si se acaba el mundo, que sea memorable", "Jinx"),
    ]),
    ("Alguien aparca fatal y te bloquea la salida justo cuando llevas prisa de verdad. ¿Qué haces?", [
        ("Le dejo una nota que le va a arruinar el día entero", "Miranda Priestly"),
        ("Busco al dueño y se lo digo clarísimo, sin gritar", "Elle Woods"),
        ("Convierto la espera en el mejor rato posible. Ya no hay prisa que valga", "Harley Quinn"),
        ("Llamo a la grúa sin remordimiento ninguno", "Katniss Everdeen"),
    ]),
    ("Te despiertas un día en el cuerpo de un completo desconocido, sin ninguna explicación. ¿Qué haces?", [
        ("Averiguo todo lo que pueda de su vida antes de que note nadie que algo va mal", "Michael Corleone"),
        ("Aprovecho para vivir un día completamente distinto, sin miedo a nada", "Jinx"),
        ("Busco la forma de volver a mi cuerpo. Esto no es lo mío", "V"),
        ("Lo tomo como una oportunidad de empezar de cero, sin cargar con nada de antes", "Mia Dolan"),
    ]),
    ("Tu jefe te pide que mientas a un cliente para cerrar una venta importante. ¿Qué haces?", [
        ("Me niego, aunque me cueste el puesto", "Steve Rogers (Capitán América)"),
        ("Busco la forma de cerrar la venta sin mentir. Se puede ganar bien", "Elle Woods"),
        ("Miento sin pestañear. Solo van a recordar el resultado", "Miranda Priestly"),
        ("Se lo aviso al cliente en cuanto puedo", "Katniss Everdeen"),
    ]),
    ("Un virus convierte a media ciudad en zombis pacíficos que solo buscan compañía, sin hacer daño a nadie. ¿Qué haces?", [
        ("Me hago amigo de uno. ¿Por qué no? El mundo ya era raro antes de esto", "Harley Quinn"),
        ("Organizo a todos los que quedan para proteger tanto a los normales como a los zombis", "V"),
        ("Aprovecho el caos para desaparecer sin que nadie lo note", "Joker"),
        ("Lo documento todo, por si hace falta contarlo después", "Mia Dolan"),
    ]),
    ("Descubres que tu pareja te ha mentido sobre algo pequeño, pero llevaba haciéndolo años. ¿Qué haces?", [
        ("Pregunto directamente. Prefiero la verdad incómoda a la duda", "Nikki Freeman"),
        ("Me lo guardo dentro y lo proceso solo, aunque me lleve semanas", "Sam Wheat"),
        ("No lo perdono ni lo olvido. A partir de ahora miro todo distinto", "Miranda Priestly"),
        ("Decido que lo pequeño no borra lo grande, y sigo", "Elle Woods"),
    ]),
    ("Te ofrecen rehacer tu vida entera desde cero, con todo lo que siempre quisiste, pero olvidando a todos los que quieres ahora. ¿Aceptas?", [
        ("La rechazo sin pensarlo. Ninguna vida perfecta merece perder a quien quiero", "Nikki Freeman"),
        ("La rechazo. No cambiaría nada de lo que me hizo ser quien soy", "V"),
        ("La acepto. Empezar de cero sin cargar con nada suena a libertad", "Mia Dolan"),
        ("Me río de la propuesta. ¿Para qué querría yo una vida \"perfecta\"?", "Jinx"),
    ]),
    ("Encuentras una cartera con bastante dinero en la calle, sin ningún nombre ni forma de devolverla. ¿Qué haces?", [
        ("La entrego sin pensarlo. No es mía", "Elle Woods"),
        ("Me la quedo. Si el universo me la pone delante, es mía", "Joker"),
        ("Me la quedo, pero uso parte para ayudar a quien de verdad lo necesite", "Harley Quinn"),
        ("La entrego. Pero me quedo con el dato de quién la perdió", "Michael Corleone"),
    ]),
    ("Un accidente te transporta a un mundo paralelo donde todos tus seres queridos existen, pero ninguno te reconoce. ¿Qué haces?", [
        ("Me quedo cerca de ellos igual, en silencio, aunque no sepan quién soy", "Nikki Freeman"),
        ("Busco desesperadamente la forma de volver a mi mundo", "Steve Rogers (Capitán América)"),
        ("Aprovecho para reinventarme del todo. Nadie me dice quién se supone que soy", "Mia Dolan"),
        ("Convierto esto en la aventura más loca de mi vida", "Joker"),
    ]),
    ("Si mañana desaparece de golpe todo lo que has construido hasta ahora, ¿qué haces?", [
        ("Empiezo de cero, sin mirar atrás", "Mia Dolan"),
        ("Lo reconstruyo exactamente igual. Más fuerte que antes", "Miranda Priestly"),
        ("Me río. Total, nada dura para siempre", "Jinx"),
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
