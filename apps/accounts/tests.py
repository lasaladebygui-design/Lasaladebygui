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


class RegisterFormTests(TestCase):
    def _post(self, **overrides):
        data = {
            "username": "cinefilo1", "email": "nuevo@test.local",
            "password1": "Testpass123!", "password2": "Testpass123!",
        }
        data.update(overrides)
        return self.client.post(reverse("accounts:register"), data)

    def test_registro_crea_el_usuario_con_el_nombre_elegido(self):
        response = self._post()
        self.assertRedirects(response, reverse("core:home"))
        user = User.objects.get(email="nuevo@test.local")
        self.assertEqual(user.username, "cinefilo1")

    def test_nombre_de_usuario_duplicado_se_rechaza(self):
        User.objects.create(email="otro@test.local", username="cinefilo1", role=User.Role.LECTOR)
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="nuevo@test.local").exists())
        self.assertContains(response, "ya está en uso")

    def test_nombre_de_usuario_con_caracteres_invalidos_se_rechaza(self):
        response = self._post(username="con espacios!")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="nuevo@test.local").exists())


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

    def test_subir_avatar(self):
        response = self.client.post(reverse("accounts:profile"), {
            "avatar": _fake_image(),
        })
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name.startswith("avatars/"))

    def test_sin_avatar_muestra_placeholder(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "profile-avatar--placeholder")

    def test_el_perfil_incluye_el_pool_de_frases_para_la_frase_dinamica(self):
        from apps.secret.models import MovieQuote

        MovieQuote.objects.create(
            quote="Frase de prueba sin caracteres especiales",
            correct_title="Película X", wrong_title_1="Y", wrong_title_2="Z",
        )
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "rotating-quotes-data")
        self.assertContains(response, "Frase de prueba sin caracteres especiales")

    def test_sin_frases_celebres_el_perfil_no_falla(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "rotating-quotes-data")


class NavPanelLinkTests(TestCase):
    """El enlace 'Panel' del desplegable es solo para el Admin — Gestor y
    Editor también son is_staff (para permisos puntuales en /admin/) pero
    no deben ver el enlace en la navegación."""

    def _login_as(self, email, role):
        user = User.objects.create(email=email, role=role)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=email, password="Testpass123!")

    def test_admin_ve_el_enlace_panel(self):
        self._login_as("admin@test.local", User.Role.ADMIN)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, ">Panel<")

    def test_gestor_no_ve_el_enlace_panel(self):
        self._login_as("gestor@test.local", User.Role.GESTOR)
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, ">Panel<")

    def test_editor_no_ve_el_enlace_panel(self):
        self._login_as("editor@test.local", User.Role.EDITOR)
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, ">Panel<")
