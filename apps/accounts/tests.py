import io
import re
import tempfile

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.forum.models import Thread

from .models import User

try:
    from PIL import Image
except ImportError:
    Image = None


class GestorGroupSyncTests(TestCase):
    def test_gestor_se_anade_al_grupo_con_permisos_de_foro(self):
        user = User.objects.create(email="gestor@test.local", role=User.Role.GESTOR)
        self.assertTrue(user.groups.filter(name="Gestor").exists())
        self.assertTrue(user.has_perm("forum.change_thread"))
        self.assertTrue(user.has_perm("forum.delete_threadcomment"))

    def test_no_gestor_no_esta_en_el_grupo(self):
        user = User.objects.create(email="lector@test.local", role=User.Role.LECTOR)
        self.assertFalse(user.groups.filter(name="Gestor").exists())
        self.assertFalse(user.has_perm("forum.change_thread"))

    def test_perder_el_rol_gestor_quita_del_grupo(self):
        user = User.objects.create(email="gestor2@test.local", role=User.Role.GESTOR)
        self.assertTrue(user.groups.filter(name="Gestor").exists())

        user.role = User.Role.LECTOR
        user.save()
        self.assertFalse(user.groups.filter(name="Gestor").exists())

    def test_gestor_puede_entrar_al_admin_del_foro(self):
        user = User.objects.create(email="gestor3@test.local", role=User.Role.GESTOR)
        user.set_password("Testpass123!")
        user.save()
        thread = Thread.objects.create(title="Hilo", body="cuerpo")

        self.client.login(username=user.email, password="Testpass123!")
        response = self.client.get(f"/admin/forum/thread/{thread.pk}/change/")
        self.assertEqual(response.status_code, 200)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="lector@test.local", role=User.Role.LECTOR)
        self.user.set_password("ContraseñaVieja123!")
        self.user.save()

    def test_solicitar_reset_envia_email_con_enlace(self):
        response = self.client.post(reverse("accounts:password-reset"), {"email": self.user.email})
        self.assertRedirects(response, reverse("accounts:password-reset-done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Recupera tu contraseña", mail.outbox[0].subject)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_email_inexistente_no_revela_si_existe_la_cuenta(self):
        response = self.client.post(reverse("accounts:password-reset"), {"email": "no-existe@test.local"})
        self.assertRedirects(response, reverse("accounts:password-reset-done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_flujo_completo_cambia_la_contraseña(self):
        self.client.post(reverse("accounts:password-reset"), {"email": self.user.email})
        body = mail.outbox[0].body
        match = re.search(r"/cuenta/password/reset/confirmar/([^/]+)/([^/\s]+)/", body)
        self.assertIsNotNone(match)
        uidb64, token = match.group(1), match.group(2)

        # Django exige visitar primero la URL con el token real para que la
        # vista lo intercambie por uno de sesión (así no queda en el historial).
        confirm_url = reverse("accounts:password-reset-confirm", args=[uidb64, token])
        session_response = self.client.get(confirm_url, follow=True)
        self.assertEqual(session_response.status_code, 200)
        final_url = session_response.redirect_chain[-1][0]

        response = self.client.post(final_url, {
            "new_password1": "ContraseñaNueva456!",
            "new_password2": "ContraseñaNueva456!",
        })
        self.assertRedirects(response, reverse("accounts:password-reset-complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("ContraseñaNueva456!"))
        self.assertFalse(self.user.check_password("ContraseñaVieja123!"))

    def test_baneado_no_recibe_email_de_reset(self):
        self.user.role = User.Role.BANEADO
        self.user.save()
        self.client.post(reverse("accounts:password-reset"), {"email": self.user.email})
        self.assertEqual(len(mail.outbox), 0)


def _fake_image():
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile("avatar.png", buffer.read(), content_type="image/png")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="lector@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")

    def test_guardar_frase_mitica(self):
        response = self.client.post(reverse("accounts:profile"), {
            "favorite_quote": "Hasta el infinito y más allá",
        })
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.favorite_quote, "Hasta el infinito y más allá")

    def test_la_frase_se_muestra_en_el_perfil(self):
        self.user.favorite_quote = "Que la Fuerza te acompañe"
        self.user.save()
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "Que la Fuerza te acompañe")

    def test_subir_avatar(self):
        response = self.client.post(reverse("accounts:profile"), {
            "favorite_quote": "",
            "avatar": _fake_image(),
        })
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name.startswith("avatars/"))

    def test_sin_avatar_muestra_placeholder(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "profile-avatar--placeholder")
