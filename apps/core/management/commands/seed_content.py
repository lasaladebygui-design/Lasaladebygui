from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.articles.models import Article, Tag
from apps.forum.models import Thread, ThreadComment
from apps.secret.models import SecretMovie

ARTICLES = [
    {
        "title": "Cinema Paradiso: por qué seguimos volviendo al cine de barrio",
        "author_email": "editor@lasaladebygui.local",
        "tags": ["clásicos", "drama"],
        "body": (
            "<p>Hay películas que no envejecen porque hablan de algo que no cambia: "
            "las ganas de sentarse en la oscuridad a soñar con otra gente.</p>"
            "<p>Giuseppe Tornatore construyó una carta de amor al cine que sigue "
            "funcionando treinta años después, y hoy repasamos por qué.</p>"
        ),
    },
    {
        "title": "El regreso del cine de terror ochentero",
        "author_email": "admin@lasaladebygui.local",
        "tags": ["terror", "años 80"],
        "body": (
            "<p>Entre remakes, homenajes y sintetizadores, el terror de los 80 "
            "ha vuelto a las salas por la puerta grande.</p>"
            "<p>Repasamos las claves de esta ola nostálgica y qué títulos "
            "recientes merecen la pena.</p>"
        ),
    },
    {
        "title": "Guía rápida para perderse en el cine de animación asiático",
        "author_email": "gestor@lasaladebygui.local",
        "tags": ["animación"],
        "body": (
            "<p>Más allá de Ghibli hay todo un universo de animación que merece "
            "tu tiempo. Aquí van cinco puertas de entrada.</p>"
        ),
    },
]

THREADS = [
    {
        "title": "¿Cuál es vuestra película de culto infravalorada?",
        "author_email": "lector@lasaladebygui.local",
        "body": "Yo empiezo: creo que nadie habla lo suficiente de ciertas joyas de serie B. ¿Y vosotros?",
        "replies": [
            {
                "author_email": "editor@lasaladebygui.local",
                "body": "Para mí cualquier cosa de John Carpenter de los 80 que no sea 'La Cosa'.",
                "children": [
                    {
                        "author_email": "lector@lasaladebygui.local",
                        "body": "'Están vivos' debería ser de visionado obligatorio, totalmente de acuerdo.",
                    },
                ],
            },
            {
                "author_email": "gestor@lasaladebygui.local",
                "body": "Como moderador aprovecho para recordar: mantengamos el hilo sin spoilers sin avisar 🙂",
            },
        ],
    },
    {
        "title": "Mejores estrenos del mes",
        "author_email": "editor@lasaladebygui.local",
        "body": "Abro hilo para comentar los estrenos que no os podéis perder este mes.",
        "replies": [],
    },
]

# El número ya no se elige a mano: se recalcula solo según la nota
# (`SecretMovie._renumber_all`), así que aquí solo hace falta título/nota/
# comentario — el orden de esta lista no importa para el número final.
SECRET_MOVIES = [
    ("Reservoir Dogs", "9.0", "El origen de todo. Un atraco que nunca vemos y que no hace falta ver."),
    ("Kill Bill Vol. 1", "8.7", "Venganza, katanas y una lista con nombres tachados. Puro cine de género elevado a arte."),
    ("Jackie Brown", "8.3", "La más adulta y contenida de Tarantino. Infravalorada."),
    ("Malas tierras", "8.0", "No es suya, pero se nota en cada plano por qué la cita tanto."),
]

class Command(BaseCommand):
    help = "Crea artículos y hilos de foro de ejemplo (requiere los usuarios de seed_demo)."

    def handle(self, *args, **options):
        call_command("seed_demo")

        for data in ARTICLES:
            author = User.objects.filter(email=data["author_email"]).first()
            article, created = Article.objects.get_or_create(
                title=data["title"],
                defaults={"author": author, "body": data["body"]},
            )
            if created:
                article.tags.set([Tag.objects.get_or_create(name=name)[0] for name in data["tags"]])
                self.stdout.write(self.style.SUCCESS(f"Artículo creado: {article.title}"))
            else:
                self.stdout.write(f"Ya existía el artículo «{article.title}», no se modifica.")

        for data in THREADS:
            author = User.objects.filter(email=data["author_email"]).first()
            thread, created = Thread.objects.get_or_create(
                title=data["title"],
                defaults={"author": author, "body": data["body"]},
            )
            if not created:
                self.stdout.write(f"Ya existía el hilo «{thread.title}», no se modifica.")
                continue

            self.stdout.write(self.style.SUCCESS(f"Hilo creado: {thread.title}"))
            for reply in data["replies"]:
                reply_author = User.objects.filter(email=reply["author_email"]).first()
                comment = ThreadComment.objects.create(
                    thread=thread, author=reply_author, body=reply["body"]
                )
                for child in reply.get("children", []):
                    child_author = User.objects.filter(email=child["author_email"]).first()
                    ThreadComment.objects.create(
                        thread=thread, parent=comment, author=child_author, body=child["body"]
                    )

        for title, rating, comment in SECRET_MOVIES:
            movie, created = SecretMovie.objects.get_or_create(
                title=title,
                defaults={"personal_rating": rating, "comment": comment},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Top Secret: #{movie.number} {title}"))
            else:
                self.stdout.write(f"Ya existía la película secreta «{title}», no se modifica.")

        call_command("seed_quotes")

        self.stdout.write(self.style.SUCCESS("Seed de contenido completado."))
