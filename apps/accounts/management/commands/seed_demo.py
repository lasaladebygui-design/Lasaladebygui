from django.core.management.base import BaseCommand

from apps.accounts.models import User

DEMO_USERS = [
    ("admin@lasaladebygui.local", "Admin1234!", User.Role.ADMIN, "admin_demo"),
    ("gestor@lasaladebygui.local", "Gestor1234!", User.Role.GESTOR, "gestor_demo"),
    ("editor@lasaladebygui.local", "Editor1234!", User.Role.EDITOR, "editor_demo"),
    ("lector@lasaladebygui.local", "Lector1234!", User.Role.LECTOR, "lector_demo"),
    ("baneado@lasaladebygui.local", "Baneado1234!", User.Role.BANEADO, "baneado_demo"),
]


class Command(BaseCommand):
    help = "Crea un usuario de ejemplo por cada rol (Admin, Gestor, Editor, Lector, Baneado)."

    def handle(self, *args, **options):
        for email, password, role, username in DEMO_USERS:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"username": username, "role": role, "email_verified": True},
            )
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Creado {email} ({role}) / contraseña: {password}"))
            else:
                self.stdout.write(f"Ya existía {email}, no se modifica.")

        self.stdout.write(self.style.SUCCESS("Seed de usuarios completado."))
