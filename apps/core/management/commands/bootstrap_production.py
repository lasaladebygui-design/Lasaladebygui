import os

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    """Paso de arranque seguro de ejecutar en cada despliegue (se encadena
    en el startCommand de render.yaml, después de migrate). No requiere
    Shell: todo se activa o desactiva con variables de entorno desde el
    panel de Render.

    - Si DJANGO_SUPERUSER_EMAIL y DJANGO_SUPERUSER_PASSWORD están definidas
      y todavía no existe ningún Admin, crea uno. Si ya existe un Admin, no
      hace nada (seguro de dejar puesto para siempre).
    - Si RUN_SEED_MOVIES=true, puebla el catálogo de películas y de series
      desde TMDb/OMDb (equivalente a `seed_movies` + `seed_series`). Conviene
      quitar esta variable después del primer despliegue para no repetir las
      llamadas a las APIs en cada arranque.
    - Si RUN_SEED_QUOTES=true, carga las frases de ejemplo del juego "Frases
      célebres" (equivalente a `seed_quotes`). Es idempotente (no duplica si
      ya existen), así que es seguro dejarla activada si prefieres no volver
      a tocar las variables de entorno.
    - El resto de contenido de ejemplo de Juegos (Trivial/Emoji/Malas
      descripciones/Actor/Verdadero o falso, Candidatos al Oscar y Qué
      personaje eres) se carga siempre, sin variable de entorno: a
      diferencia de las películas, no hace falta pedir permiso para
      llamar a una API cara — son idempotentes y baratas, así que no tiene
      sentido dejar esos juegos vacíos en producción esperando a que
      alguien se acuerde de activar un flag.
    """

    help = "Bootstrap de producción: primer Admin y/o contenido de ejemplo, vía variables de entorno."

    def handle(self, *args, **options):
        self._ensure_admin()
        self._maybe_seed_movies()
        self._maybe_seed_quotes()
        self._seed_games_content()

    def _ensure_admin(self):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not email or not password:
            return

        if User.objects.filter(role=User.Role.ADMIN).exists():
            self.stdout.write("Ya existe un Admin: no se crea ninguno nuevo.")
            return

        user, _ = User.objects.get_or_create(
            email=email, defaults={"role": User.Role.ADMIN, "email_verified": True}
        )
        user.role = User.Role.ADMIN
        user.email_verified = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Admin creado: {email}"))

    def _maybe_seed_movies(self):
        if os.environ.get("RUN_SEED_MOVIES", "").lower() in ("1", "true", "yes"):
            call_command("seed_movies")
            call_command("seed_series")

    def _maybe_seed_quotes(self):
        if os.environ.get("RUN_SEED_QUOTES", "").lower() in ("1", "true", "yes"):
            call_command("seed_quotes")

    def _seed_games_content(self):
        call_command("seed_trivia")
        call_command("seed_oscar_categories")
        call_command("seed_personality_quiz")
