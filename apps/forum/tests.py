from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

from .models import Thread, ThreadComment


def make_user(email, role):
    user = User(email=email, role=role)
    user.set_password("Testpass123!")
    user.save()
    return user


class ForumPermissionTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@test.local", User.Role.ADMIN)
        self.gestor = make_user("gestor@test.local", User.Role.GESTOR)
        self.lector = make_user("lector@test.local", User.Role.LECTOR)
        self.otro_lector = make_user("lector2@test.local", User.Role.LECTOR)
        self.thread = Thread.objects.create(title="Hilo de prueba", body="mensaje", author=self.lector)
        self.comment = ThreadComment.objects.create(thread=self.thread, author=self.lector, body="hola")

    def _login(self, user):
        self.client.login(username=user.email, password="Testpass123!")

    def test_cualquier_logueado_puede_abrir_hilo(self):
        self._login(self.lector)
        response = self.client.post(reverse("forum:create"), {"title": "Nuevo hilo", "body": "contenido"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Thread.objects.filter(title="Nuevo hilo").exists())

    def test_anonimo_no_puede_abrir_hilo(self):
        response = self.client.get(reverse("forum:create"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/cuenta/login/", response.url)

    def test_autor_puede_borrar_su_comentario(self):
        self._login(self.lector)
        self.client.post(reverse("forum:comment-delete", args=[self.comment.pk]))
        self.comment.refresh_from_db()
        self.assertTrue(self.comment.is_deleted)

    def test_otro_usuario_no_puede_borrar_comentario_ajeno(self):
        self._login(self.otro_lector)
        response = self.client.post(reverse("forum:comment-delete", args=[self.comment.pk]))
        self.assertEqual(response.status_code, 404)
        self.comment.refresh_from_db()
        self.assertFalse(self.comment.is_deleted)

    def test_gestor_puede_borrar_cualquier_comentario(self):
        self._login(self.gestor)
        self.client.post(reverse("forum:comment-delete", args=[self.comment.pk]))
        self.comment.refresh_from_db()
        self.assertTrue(self.comment.is_deleted)

    def test_solo_moderador_puede_cerrar_hilo(self):
        self._login(self.lector)
        response = self.client.post(reverse("forum:toggle-lock", args=[self.thread.pk]))
        self.assertEqual(response.status_code, 404)

        self._login(self.gestor)
        response = self.client.post(reverse("forum:toggle-lock", args=[self.thread.pk]))
        self.assertEqual(response.status_code, 302)
        self.thread.refresh_from_db()
        self.assertTrue(self.thread.is_locked)

    def test_no_se_puede_responder_a_hilo_cerrado(self):
        self.thread.is_locked = True
        self.thread.save()
        self._login(self.lector)
        response = self.client.post(
            reverse("forum:detail", args=[self.thread.pk]), {"body": "respuesta tardía"}
        )
        self.assertEqual(response.status_code, 403)
