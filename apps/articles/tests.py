from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import PushSubscription, User

from .models import Article, Tag


def make_user(email, role):
    user = User(email=email, role=role)
    user.set_password("Testpass123!")
    user.save()
    return user


class ArticlePermissionTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@test.local", User.Role.ADMIN)
        self.gestor = make_user("gestor@test.local", User.Role.GESTOR)
        self.editor = make_user("editor@test.local", User.Role.EDITOR)
        self.other_editor = make_user("editor2@test.local", User.Role.EDITOR)
        self.lector = make_user("lector@test.local", User.Role.LECTOR)
        self.article = Article.objects.create(
            title="Artículo de prueba", body="<p>cuerpo</p>", author=self.editor
        )

    def _login(self, user):
        self.client.login(username=user.email, password="Testpass123!")

    def test_lector_no_puede_crear_articulos(self):
        self._login(self.lector)
        response = self.client.get(reverse("articles:create"))
        self.assertEqual(response.status_code, 404)

    def test_editor_puede_crear_articulos(self):
        self._login(self.editor)
        response = self.client.get(reverse("articles:create"))
        self.assertEqual(response.status_code, 200)

    def test_editor_no_puede_editar_articulo_ajeno(self):
        self._login(self.other_editor)
        response = self.client.get(reverse("articles:update", args=[self.article.slug]))
        self.assertEqual(response.status_code, 404)

    def test_editor_puede_editar_su_propio_articulo(self):
        self._login(self.editor)
        response = self.client.get(reverse("articles:update", args=[self.article.slug]))
        self.assertEqual(response.status_code, 200)

    def test_gestor_puede_editar_articulo_ajeno(self):
        self._login(self.gestor)
        response = self.client.get(reverse("articles:update", args=[self.article.slug]))
        self.assertEqual(response.status_code, 200)

    def test_anonimo_no_ve_formulario_de_comentario(self):
        response = self.client.get(reverse("articles:detail", args=[self.article.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["comment_form"])

    def test_lector_puede_comentar(self):
        self._login(self.lector)
        response = self.client.post(
            reverse("articles:detail", args=[self.article.slug]), {"body": "Muy bueno"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.article.comments.count(), 1)


class ArticleDeleteTagCleanupTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin_tags@test.local", User.Role.ADMIN)
        self.only_tag = Tag.objects.create(name="Solo en este")
        self.shared_tag = Tag.objects.create(name="Compartido")
        self.article = Article.objects.create(title="Se borra", body="<p>x</p>", author=self.admin)
        self.article.tags.set([self.only_tag, self.shared_tag])
        self.other_article = Article.objects.create(title="Se queda", body="<p>y</p>", author=self.admin)
        self.other_article.tags.set([self.shared_tag])
        self.client.login(username=self.admin.email, password="Testpass123!")

    def test_borrar_articulo_borra_el_tag_que_ya_no_usa_nadie(self):
        self.client.post(reverse("articles:delete", args=[self.article.slug]))
        self.assertFalse(Tag.objects.filter(pk=self.only_tag.pk).exists())

    def test_borrar_articulo_no_borra_un_tag_compartido(self):
        self.client.post(reverse("articles:delete", args=[self.article.slug]))
        self.assertTrue(Tag.objects.filter(pk=self.shared_tag.pk).exists())
        self.assertIn(self.shared_tag, self.other_article.tags.all())


class LatestArticlesLinkTests(TestCase):
    def test_la_ficha_enlaza_a_los_cinco_ultimos_sin_incluirse_a_si_misma(self):
        author = make_user("autor_ultimos@test.local", User.Role.EDITOR)
        articles = [Article.objects.create(title=f"Artículo {i}", body="x", author=author) for i in range(7)]
        current = articles[0]

        response = self.client.get(reverse("articles:detail", args=[current.slug]))
        latest = list(response.context["latest_articles"])

        self.assertEqual(len(latest), 5)
        self.assertNotIn(current, latest)


@override_settings(VAPID_PUBLIC_KEY="clave-publica", VAPID_PRIVATE_KEY="clave-privada")
class NewArticlePushTests(TestCase):
    def setUp(self):
        self.author = make_user("autor_push@test.local", User.Role.EDITOR)
        self.subscriber = make_user("suscriptor_push@test.local", User.Role.LECTOR)
        PushSubscription.objects.create(user=self.subscriber, endpoint="https://push.example/a", p256dh="p", auth="a")
        self.client.login(username=self.author.email, password="Testpass123!")

    @patch("apps.articles.views.send_push_to_users")
    def test_publicar_articulo_notifica_a_los_suscritos(self, mock_send):
        self.client.post(reverse("articles:create"), {
            "title": "Recién publicado", "body": "<p>cuerpo</p>", "tags_input": "",
        })
        mock_send.assert_called_once()
        subscribers = list(mock_send.call_args.args[0])
        self.assertIn(self.subscriber, subscribers)
        self.assertNotIn(self.author, subscribers)
