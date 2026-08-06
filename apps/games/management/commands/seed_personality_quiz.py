from django.core.management.base import BaseCommand

from apps.games.models import PersonalityAnswer, PersonalityCharacter, PersonalityQuestion

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
    ("Tony Stark (Iron Man)", "Iron Man", "⚙️ Escondes lo que sientes detrás de una broma y una solución brillante. Te importa mucho más de lo que admites, y se nota sobre todo cuando crees que nadie mira."),
    ("Mia Dolan", "La La Land", "🌆 Persigues lo que quieres aunque el precio sea alto y el camino solitario. Prefieres el 'y si...' de haberlo intentado a la comodidad de no haberlo hecho."),
    ("Sam Wheat", "Ghost", "👻 Sientes todo por dentro y lo dices tarde, o casi nunca. Lo que más te importa no lo gritas, lo proteges — aunque nunca llegue a enterarse del todo."),
    ("Elle Woods", "Legalmente rubia", "💗 Te subestiman constantemente y lo conviertes en tu mejor arma. Amable primero, pero no confundas eso con ser blanda — trabajas el doble y lo demuestras."),
    ("Miranda Priestly", "El diablo viste de Prada", "👠 No pides perdón por saber lo que quieres. Los resultados hablan por ti, y no tienes ningún interés en gustarle a todo el mundo."),
]

# Cada pregunta: (texto, [(texto_respuesta, nombre_personaje), x4]). Mezcla
# de dilemas cotidianos (nada de "a quién sacrificas") y preferencias/
# reacciones, tal y como se acordó con el dueño del sitio.
QUESTIONS = [
    ("Un compañero de trabajo se lleva el mérito de algo que hiciste tú. ¿Qué haces?", [
        ("Lo dejo pasar, no merece la pena el conflicto", "Sam Wheat"),
        ("Se lo digo en privado y le doy la oportunidad de corregirlo", "Steve Rogers (Capitán América)"),
        ("Lo dejo claro delante de todos, que quede constancia", "Katniss Everdeen"),
        ("Empiezo a jugar mis cartas para que la próxima vez el mérito sea mío", "Michael Corleone"),
    ]),
    ("¿Qué es lo que más valoras en la gente que te rodea?", [
        ("Lealtad, pase lo que pase", "Harley Quinn"),
        ("Honestidad, aunque duela", "Steve Rogers (Capitán América)"),
        ("Ambición, que quieran llegar lejos", "Miranda Priestly"),
        ("Sentido del humor, que no se lo tomen todo tan en serio", "Jinx"),
    ]),
    ("Descubres un secreto que podría hacer mucho daño a alguien que quieres. ¿Qué haces?", [
        ("Me lo guardo para siempre, para protegerle", "Sam Wheat"),
        ("Se lo cuento aunque duela, prefiero la verdad", "Katniss Everdeen"),
        ("Lo uso solo si alguna vez me hace falta", "Michael Corleone"),
        ("Lo suelto en el peor momento posible, por diversión", "Joker"),
    ]),
    ("Te acaban de dar una mala noticia. ¿Cómo reaccionas?", [
        ("Me río, si no me río me hundo", "Jinx"),
        ("Me quedo en silencio, lo proceso por dentro", "Sam Wheat"),
        ("Ya estoy pensando en el siguiente movimiento", "Miranda Priestly"),
        ("Necesito desahogarme con alguien ya mismo", "Harley Quinn"),
    ]),
    ("Tienes la oportunidad de conseguir lo que siempre quisiste, pero significa dejar atrás a alguien importante. ¿Qué haces?", [
        ("Voy a por ello, es mi sueño y no pienso renunciar", "Mia Dolan"),
        ("Me quedo, las personas importan más que cualquier sueño", "Steve Rogers (Capitán América)"),
        ("Busco la manera de tenerlo todo, aunque sea complicado", "Tony Stark (Iron Man)"),
        ("Voy a por ello sin mirar atrás, sin dramas", "Miranda Priestly"),
    ]),
    ("¿Cómo prefieres pasar un fin de semana libre?", [
        ("Organizando algo espectacular, aunque sea un caos", "Jinx"),
        ("Tranquilo, con alguien especial, sin planes", "Sam Wheat"),
        ("Trabajando en algo mío, mejorando algo", "Miranda Priestly"),
        ("Al aire libre, lejos de la gente", "Katniss Everdeen"),
    ]),
    ("Un amigo te pide ayuda para algo que sabes que está mal. ¿Qué haces?", [
        ("Le ayudo de todas formas, la lealtad va primero", "Harley Quinn"),
        ("Le digo que no y le explico por qué", "Steve Rogers (Capitán América)"),
        ("Le ayudo, pero me aseguro de que me deba una", "Michael Corleone"),
        ("Le ayudo... y convierto el lío en algo aún más grande", "Jinx"),
    ]),
    ("¿Qué tipo de final de película prefieres?", [
        ("Agridulce, que se quede algo pendiente", "Mia Dolan"),
        ("Feliz, aunque sea poco realista", "Elle Woods"),
        ("Con un giro que nadie viera venir", "Tony Stark (Iron Man)"),
        ("Donde alguien lo sacrifique todo por una idea", "V"),
    ]),
    ("Estás en una discusión que sabes que vas a perder. ¿Qué haces?", [
        ("Cedo, no merece la pena discutir por orgullo", "Elle Woods"),
        ("Sigo hasta el final, aunque pierda", "V"),
        ("Cambio de tema con una broma", "Tony Stark (Iron Man)"),
        ("Dejo que crean que ganaron... por ahora", "Michael Corleone"),
    ]),
    ("¿Qué te describe mejor cuando trabajas en equipo?", [
        ("Soy quien mantiene la calma cuando todo se tuerce", "Steve Rogers (Capitán América)"),
        ("Soy quien sube la energía de todos", "Jinx"),
        ("Soy quien más curra, aunque nadie lo note", "Elle Woods"),
        ("Soy quien toma las decisiones difíciles", "Michael Corleone"),
    ]),
    ("Tienes que elegir entre decir una verdad incómoda o mantener la paz. ¿Qué eliges?", [
        ("La verdad, siempre, aunque incomode", "Katniss Everdeen"),
        ("La paz, hay batallas que no vale la pena pelear", "Sam Wheat"),
        ("La verdad, pero la digo de la forma más directa posible", "Miranda Priestly"),
        ("Ninguna de las dos, cambio las reglas del juego", "Joker"),
    ]),
    ("¿Qué te haría más ilusión conseguir?", [
        ("Que alguien crea en mí cuando nadie más lo hizo", "Elle Woods"),
        ("Cambiar algo del sistema, aunque sea pequeño", "V"),
        ("Ser imprescindible en lo mío", "Miranda Priestly"),
        ("Vivir una historia de amor que valga la pena", "Mia Dolan"),
    ]),
    ("Alguien te traiciona. ¿Cómo respondes?", [
        ("Corto por lo sano, sin venganza ni drama", "Katniss Everdeen"),
        ("Nunca lo olvido, y algún día se lo recuerdo", "Michael Corleone"),
        ("Le doy una segunda oportunidad, aunque no debería", "Harley Quinn"),
        ("Lo convierto en un juego para ver qué más hace", "Joker"),
    ]),
    ("¿Qué es lo que más miedo te da?", [
        ("Que no quede nadie que se acuerde de mí", "Sam Wheat"),
        ("Convertirme en alguien que no reconozco", "Steve Rogers (Capitán América)"),
        ("Perder el control de todo lo que he construido", "Miranda Priestly"),
        ("Que se acabe la diversión", "Jinx"),
    ]),
    ("Ves a alguien haciendo bullying a otra persona. ¿Qué haces?", [
        ("Intervengo directamente, ahí mismo", "Steve Rogers (Capitán América)"),
        ("Ayudo a la víctima después, en privado", "Elle Woods"),
        ("Me aseguro de que quien lo hizo lo pague, tarde o temprano", "Katniss Everdeen"),
        ("Convierto la situación en un espectáculo que nadie olvide", "Jinx"),
    ]),
    ("¿Qué tipo de líder serías?", [
        ("Uno que lidera con el ejemplo, sin buscar aplausos", "Steve Rogers (Capitán América)"),
        ("Uno que inspira aunque dé miedo", "V"),
        ("Uno que consigue resultados, guste o no", "Miranda Priestly"),
        ("Uno impredecible, que nadie sabe qué esperar", "Joker"),
    ]),
    ("Te ofrecen un atajo fácil para conseguir lo que quieres, pero no del todo limpio. ¿Qué haces?", [
        ("Lo rechazo, prefiero llegar despacio pero limpio", "Elle Woods"),
        ("Lo cojo, los resultados hablan por sí solos", "Michael Corleone"),
        ("Lo cojo y ya improviso sobre la marcha", "Tony Stark (Iron Man)"),
        ("Lo rechazo, y encima se lo cuento a quien deba saberlo", "Katniss Everdeen"),
    ]),
    ("Si mañana desapareciera todo lo que has construido, ¿qué harías?", [
        ("Empezar de cero, sin mirar atrás", "Mia Dolan"),
        ("Reconstruirlo exactamente igual, más fuerte", "Miranda Priestly"),
        ("Reírme, total, nada dura para siempre", "Jinx"),
        ("Buscar a quien me importa antes que nada", "Sam Wheat"),
    ]),
]


class Command(BaseCommand):
    help = (
        "Carga los personajes y preguntas de 'Qué personaje eres'. Seguro de "
        "ejecutar también contra producción — no crea usuarios de ejemplo."
    )

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

        created_questions = 0
        created_answers = 0
        for order, (text, answers) in enumerate(QUESTIONS):
            question, created = PersonalityQuestion.objects.get_or_create(text=text, defaults={"order": order})
            if created:
                created_questions += 1
            for answer_order, (answer_text, character_name) in enumerate(answers):
                _, answer_created = PersonalityAnswer.objects.get_or_create(
                    question=question, text=answer_text,
                    defaults={"character": characters_by_name[character_name], "order": answer_order},
                )
                if answer_created:
                    created_answers += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seed de 'Qué personaje eres' completado: {created_characters} personajes, "
            f"{created_questions} preguntas y {created_answers} respuestas nuevas (el resto ya existía)."
        ))
