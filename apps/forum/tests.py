from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import PushSubscription, User

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

    def test_doble_borrado_gestor_elimina_definitivamente(self):
        self.comment.is_deleted = True
        self.comment.save()

        self._login(self.gestor)
        response = self.client.post(reverse("forum:comment-delete", args=[self.comment.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ThreadComment.objects.filter(pk=self.comment.pk).exists())

    def test_autor_no_puede_hacer_el_doble_borrado(self):
        self.comment.is_deleted = True
        self.comment.save()

        self._login(self.lector)
        response = self.client.post(reverse("forum:comment-delete", args=[self.comment.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ThreadComment.objects.filter(pk=self.comment.pk).exists())

    def test_comentario_no_borrado_no_se_elimina_definitivamente_por_gestor(self):
        # El primer "borrar" de un Gestor sobre un comentario vivo sigue
        # siendo el borrado blando, no el definitivo.
        self._login(self.gestor)
        self.client.post(reverse("forum:comment-delete", args=[self.comment.pk]))
        self.assertTrue(ThreadComment.objects.filter(pk=self.comment.pk).exists())
        self.comment.refresh_from_db()
        self.assertTrue(self.comment.is_deleted)


@override_settings(VAPID_PUBLIC_KEY="clave-publica", VAPID_PRIVATE_KEY="clave-privada")
class ForumReplyPushTests(TestCase):
    def setUp(self):
        self.author = make_user("autor_hilo_push@test.local", User.Role.LECTOR)
        self.replier = make_user("respondedor_push@test.local", User.Role.LECTOR)
        self.thread = Thread.objects.create(title="Hilo con push", body="mensaje", author=self.author)
        PushSubscription.objects.create(user=self.author, endpoint="https://push.example/hilo", p256dh="p", auth="a")
        self.client.login(username=self.replier.email, password="Testpass123!")

    @patch("apps.forum.views.send_push_to_user")
    def test_responder_al_hilo_notifica_al_autor_del_hilo(self, mock_send):
        self.client.post(reverse("forum:detail", args=[self.thread.pk]), {"body": "respuesta"})
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.args[0], self.author)

    @patch("apps.forum.views.send_push_to_user")
    def test_responder_a_un_comentario_notifica_al_autor_de_ese_comentario_no_al_del_hilo(self, mock_send):
        comment = ThreadComment.objects.create(thread=self.thread, author=self.author, body="raíz")
        other = make_user("otro_comentarista_push@test.local", User.Role.LECTOR)
        PushSubscription.objects.create(user=other, endpoint="https://push.example/comentario", p256dh="p", auth="a")
        child = ThreadComment.objects.create(thread=self.thread, author=other, parent=comment, body="respuesta hija")

        self.client.post(
            reverse("forum:detail", args=[self.thread.pk]), {"body": "otra respuesta", "parent_id": child.pk}
        )
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.args[0], other)

    @patch("apps.forum.views.send_push_to_user")
    def test_no_se_notifica_a_si_mismo(self, mock_send):
        self.client.logout()
        self.client.login(username=self.author.email, password="Testpass123!")
        self.client.post(reverse("forum:detail", args=[self.thread.pk]), {"body": "me respondo a mi hilo"})
        mock_send.assert_not_called()
