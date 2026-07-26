from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

from .models import Article


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
