from unittest.mock import patch

from django.core import mail
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import PushSubscription, User

from .models import Article, ArticleIdea, Tag


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


class PrivateArticleTests(TestCase):
    """Un artículo privado solo lo ven Gestor y Admin — ni en el listado, ni
    en su ficha directa, ni en la home, ni en "últimos artículos" de otra
    ficha. Solo Gestor/Admin puede marcarlo como privado."""

    def setUp(self):
        self.admin = make_user("admin_priv@test.local", User.Role.ADMIN)
        self.gestor = make_user("gestor_priv@test.local", User.Role.GESTOR)
        self.editor = make_user("editor_priv@test.local", User.Role.EDITOR)
        self.lector = make_user("lector_priv@test.local", User.Role.LECTOR)
        self.private_article = Article.objects.create(
            title="Solo para el equipo", body="<p>secreto</p>", author=self.gestor, is_private=True,
        )
        self.public_article = Article.objects.create(
            title="Para todos", body="<p>público</p>", author=self.gestor,
        )

    def _login(self, user):
        self.client.login(username=user.email, password="Testpass123!")

    def test_anonimo_no_ve_el_articulo_privado_en_el_listado(self):
        response = self.client.get(reverse("articles:list"))
        self.assertNotContains(response, "Solo para el equipo")
        self.assertContains(response, "Para todos")

    def test_anonimo_no_puede_abrir_el_articulo_privado_directamente(self):
        response = self.client.get(reverse("articles:detail", args=[self.private_article.slug]))
        self.assertEqual(response.status_code, 404)

    def test_lector_no_ve_el_articulo_privado(self):
        self._login(self.lector)
        response = self.client.get(reverse("articles:list"))
        self.assertNotContains(response, "Solo para el equipo")

    def test_gestor_ve_el_articulo_privado(self):
        self._login(self.gestor)
        response = self.client.get(reverse("articles:list"))
        self.assertContains(response, "Solo para el equipo")

    def test_admin_puede_abrir_el_articulo_privado(self):
        self._login(self.admin)
        response = self.client.get(reverse("articles:detail", args=[self.private_article.slug]))
        self.assertEqual(response.status_code, 200)

    def test_no_aparece_en_la_home(self):
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "Solo para el equipo")

    def test_no_aparece_en_ultimos_articulos_de_otra_ficha(self):
        response = self.client.get(reverse("articles:detail", args=[self.public_article.slug]))
        self.assertNotContains(response, "Solo para el equipo")

    def test_editor_no_ve_el_campo_privado_en_el_formulario(self):
        self._login(self.editor)
        response = self.client.get(reverse("articles:create"))
        self.assertNotIn("is_private", response.context["form"].fields)

    def test_gestor_si_ve_el_campo_privado_en_el_formulario(self):
        self._login(self.gestor)
        response = self.client.get(reverse("articles:create"))
        self.assertIn("is_private", response.context["form"].fields)

    def test_editor_no_puede_marcar_su_articulo_como_privado_aunque_lo_intente(self):
        self._login(self.editor)
        response = self.client.post(reverse("articles:create"), {
            "title": "Intento de privado", "body": "<p>x</p>", "tags_input": "", "is_private": "on",
        })
        self.assertEqual(response.status_code, 302)
        article = Article.objects.get(title="Intento de privado")
        self.assertFalse(article.is_private)

    def test_gestor_puede_marcar_como_privado_al_crear(self):
        self._login(self.gestor)
        self.client.post(reverse("articles:create"), {
            "title": "Nuevo privado", "body": "<p>x</p>", "tags_input": "", "is_private": "on",
        })
        article = Article.objects.get(title="Nuevo privado")
        self.assertTrue(article.is_private)


class ArticleListSearchAndScrollTests(TestCase):
    """Búsqueda por palabras (título/texto) y scroll infinito (un sensor
    HTMX que pide la siguiente página al entrar en pantalla, en vez de la
    paginación con números)."""

    def setUp(self):
        self.author = make_user("autor_busqueda@test.local", User.Role.EDITOR)
        self.matching = Article.objects.create(
            title="Todo sobre Matrix", body="<p>una reseña cualquiera</p>", author=self.author,
        )
        self.matching_by_body = Article.objects.create(
            title="Reseña genérica", body="<p>hablamos de Matrix Reloaded aquí</p>", author=self.author,
        )
        self.not_matching = Article.objects.create(
            title="Sobre otra película", body="<p>nada que ver</p>", author=self.author,
        )

    def test_busca_por_titulo(self):
        response = self.client.get(reverse("articles:list"), {"q": "Matrix"})
        self.assertContains(response, "Todo sobre Matrix")
        self.assertContains(response, "Reseña genérica")
        self.assertNotContains(response, "Sobre otra película")

    def test_sin_resultados_muestra_aviso(self):
        response = self.client.get(reverse("articles:list"), {"q": "esto no existe en ningún artículo"})
        self.assertContains(response, "Sin resultados")

    def test_peticion_htmx_devuelve_solo_el_fragmento(self):
        response = self.client.get(reverse("articles:list"), HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(response, "articles/_article_cards.html")
        self.assertNotContains(response, "<h1>Artículos</h1>")

    def test_hay_sensor_de_scroll_si_queda_otra_pagina(self):
        for i in range(10):
            Article.objects.create(title=f"Extra {i}", body="<p>x</p>", author=self.author)
        response = self.client.get(reverse("articles:list"))
        self.assertContains(response, "article-grid__sentinel")
        self.assertContains(response, "hx-trigger=\"revealed\"")

    def test_no_hay_sensor_en_la_ultima_pagina(self):
        response = self.client.get(reverse("articles:list"))
        self.assertNotContains(response, "article-grid__sentinel")

    def test_el_sensor_conserva_la_busqueda_y_la_lista(self):
        tag = Tag.objects.create(name="Acción", slug="accion")
        self.matching.tags.add(tag)
        for i in range(10):
            article = Article.objects.create(title=f"Matrix extra {i}", body="<p>x</p>", author=self.author)
            article.tags.add(tag)
        response = self.client.get(reverse("articles:list"), {"q": "Matrix", "tag": "accion"})
        self.assertContains(response, "tag=accion")
        self.assertContains(response, "q=Matrix")


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


class ArticleBulkDeleteTests(TestCase):
    """Selección múltiple para borrar varios artículos de golpe desde el
    listado — el checkbox de cada tarjeta solo sale si puedes borrar ESE
    artículo en concreto (misma regla que el borrado individual)."""

    def setUp(self):
        self.gestor = make_user("gestor_bulk@test.local", User.Role.GESTOR)
        self.editor = make_user("editor_bulk@test.local", User.Role.EDITOR)
        self.other_editor = make_user("editor_bulk2@test.local", User.Role.EDITOR)
        self.own_article = Article.objects.create(title="Mío", body="<p>x</p>", author=self.editor)
        self.other_article = Article.objects.create(title="Ajeno", body="<p>y</p>", author=self.other_editor)

    def _login(self, user):
        self.client.login(username=user.email, password="Testpass123!")

    def test_el_editor_solo_ve_el_checkbox_en_sus_propios_articulos(self):
        self._login(self.editor)
        response = self.client.get(reverse("articles:list"))
        self.assertContains(response, f'value="{self.own_article.slug}"')
        self.assertNotContains(response, f'value="{self.other_article.slug}"')

    def test_el_gestor_ve_el_checkbox_en_todos(self):
        self._login(self.gestor)
        response = self.client.get(reverse("articles:list"))
        self.assertContains(response, f'value="{self.own_article.slug}"')
        self.assertContains(response, f'value="{self.other_article.slug}"')

    def test_el_gestor_puede_borrar_varios_de_golpe(self):
        self._login(self.gestor)
        self.client.post(reverse("articles:bulk-delete"), {
            "slugs": [self.own_article.slug, self.other_article.slug],
        })
        self.assertFalse(Article.objects.filter(pk=self.own_article.pk).exists())
        self.assertFalse(Article.objects.filter(pk=self.other_article.pk).exists())

    def test_el_editor_no_puede_borrar_el_articulo_ajeno_aunque_lo_incluya_a_mano(self):
        self._login(self.editor)
        self.client.post(reverse("articles:bulk-delete"), {
            "slugs": [self.own_article.slug, self.other_article.slug],
        })
        self.assertFalse(Article.objects.filter(pk=self.own_article.pk).exists())
        self.assertTrue(Article.objects.filter(pk=self.other_article.pk).exists())

    def test_borrar_varios_limpia_los_tags_huerfanos(self):
        tag = Tag.objects.create(name="Solo aquí")
        self.own_article.tags.add(tag)
        self._login(self.editor)
        self.client.post(reverse("articles:bulk-delete"), {"slugs": [self.own_article.slug]})
        self.assertFalse(Tag.objects.filter(pk=tag.pk).exists())

    def test_anonimo_no_ve_checkbox_ni_puede_borrar(self):
        response = self.client.get(reverse("articles:list"))
        self.assertNotContains(response, 'class="article-card__select"')
        self.client.post(reverse("articles:bulk-delete"), {"slugs": [self.own_article.slug]})
        self.assertTrue(Article.objects.filter(pk=self.own_article.pk).exists())


class ArticleBulkFeatureTests(TestCase):
    """Marcar en tanda cuáles salen en el carrusel destacado — reutiliza
    la misma selección de checkboxes que borrar, pero solo para Admin
    (ni siquiera Gestor, es una decisión de portada)."""

    def setUp(self):
        self.admin = make_user("admin_bulk_feat@test.local", User.Role.ADMIN)
        self.gestor = make_user("gestor_bulk_feat@test.local", User.Role.GESTOR)
        self.a = Article.objects.create(title="Uno", body="<p>x</p>")
        self.b = Article.objects.create(title="Dos", body="<p>y</p>")

    def _login(self, user):
        self.client.login(username=user.email, password="Testpass123!")

    def test_el_admin_ve_el_boton_de_destacar(self):
        self._login(self.admin)
        response = self.client.get(reverse("articles:list"))
        self.assertContains(response, "bulk-feature-button")

    def test_el_gestor_no_ve_el_boton_de_destacar(self):
        self._login(self.gestor)
        response = self.client.get(reverse("articles:list"))
        self.assertNotContains(response, "bulk-feature-button")

    def test_el_admin_puede_marcar_varios_de_golpe(self):
        self._login(self.admin)
        self.client.post(reverse("articles:bulk-feature"), {"slugs": [self.a.slug, self.b.slug]})
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertTrue(self.a.is_featured)
        self.assertTrue(self.b.is_featured)

    def test_el_gestor_no_puede_marcar_aunque_lo_intente_a_mano(self):
        self._login(self.gestor)
        response = self.client.post(reverse("articles:bulk-feature"), {"slugs": [self.a.slug]})
        self.assertEqual(response.status_code, 404)
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_featured)

    def test_anonimo_no_puede_marcar(self):
        response = self.client.post(reverse("articles:bulk-feature"), {"slugs": [self.a.slug]})
        self.assertNotEqual(response.status_code, 200)
        self.a.refresh_from_db()
        self.assertFalse(self.a.is_featured)


class ArticleAdminTests(TestCase):
    """Formulario de artículo en el admin: el autor se rellena solo con
    quien ha iniciado sesión (se puede cambiar a mano), y tags/autor usan
    un buscador en vivo en vez del widget de doble columna con flechas."""

    def setUp(self):
        self.admin = make_user("admin_articulos@test.local", User.Role.ADMIN)
        self.client.login(username=self.admin.email, password="Testpass123!")

    def test_el_formulario_de_alta_rellena_el_autor_con_quien_ha_iniciado_sesion(self):
        response = self.client.get(reverse("admin:articles_article_add"))
        self.assertEqual(response.context["adminform"].form.initial.get("author"), self.admin.pk)

    def test_tags_usa_autocomplete_no_el_widget_de_doble_columna(self):
        response = self.client.get(reverse("admin:articles_article_add"))
        self.assertNotContains(response, "selector-available")
        self.assertContains(response, 'data-field-name="tags"')

    def test_el_formulario_de_edicion_carga_bien_con_portada(self):
        # Regresión: el widget de miniatura de la portada vive en un
        # template propio (apps/articles/templates/...) porque el motor
        # de formularios de Django no mira los DIRS del proyecto, solo
        # las carpetas templates/ de cada app — si el template no está en
        # el sitio correcto, esto da TemplateDoesNotExist.
        article = Article.objects.create(title="Con portada", body="x", author=self.admin)
        article.cover.save("portada.jpg", ContentFile(b"contenido-falso"), save=True)
        response = self.client.get(reverse("admin:articles_article_change", args=[article.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quitar imagen actual")

    def test_el_formulario_de_alta_no_ofrece_quitar_una_portada_que_no_existe(self):
        response = self.client.get(reverse("admin:articles_article_add"))
        self.assertNotContains(response, "Quitar imagen actual")

    def test_destacado_es_editable_desde_la_lista(self):
        article = Article.objects.create(title="Editable en lista", body="x", author=self.admin)
        response = self.client.post(reverse("admin:articles_article_changelist"), {
            "_selected_action": [article.pk],
            "action": "",
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "1",
            "form-0-id": article.pk, "form-0-is_featured": "on",
            "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertTrue(article.is_featured)


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


class NewArticleEmailTests(TestCase):
    """Al publicar un artículo (no privado) se avisa por email a todos los
    usuarios que no lo hayan desactivado en Ajustes — no solo con push."""

    def setUp(self):
        self.author = make_user("autor_email@test.local", User.Role.EDITOR)
        self.reader = make_user("lector_email@test.local", User.Role.LECTOR)
        self.opted_out = make_user("sin_avisos_email@test.local", User.Role.LECTOR)
        self.opted_out.email_notify_new_articles = False
        self.opted_out.save()
        self.client.login(username=self.author.email, password="Testpass123!")

    def test_publicar_articulo_avisa_por_email_a_quien_no_lo_ha_desactivado(self):
        self.client.post(reverse("articles:create"), {
            "title": "Con aviso por email", "body": "<p>cuerpo</p>", "tags_input": "",
        })
        recipients = {sent.to[0] for sent in mail.outbox}
        self.assertIn(self.reader.email, recipients)
        self.assertNotIn(self.opted_out.email, recipients)
        self.assertNotIn(self.author.email, recipients)

    def test_el_email_incluye_el_titulo_y_el_enlace(self):
        response = self.client.post(reverse("articles:create"), {
            "title": "Con aviso por email", "body": "<p>cuerpo</p>", "tags_input": "",
        }, follow=True)
        article = Article.objects.get(title="Con aviso por email")
        sent_to_reader = next(sent for sent in mail.outbox if sent.to == [self.reader.email])
        self.assertIn(article.title, sent_to_reader.subject)
        self.assertIn(article.get_absolute_url(), sent_to_reader.body)

    def test_un_articulo_privado_no_manda_email(self):
        gestor = make_user("gestor_email@test.local", User.Role.GESTOR)
        self.client.login(username=gestor.email, password="Testpass123!")
        self.client.post(reverse("articles:create"), {
            "title": "Privado sin avisos", "body": "<p>x</p>", "tags_input": "", "is_private": "on",
        })
        self.assertEqual(len(mail.outbox), 0)

    @patch("apps.articles.views.send_mail", side_effect=OSError("SMTP caído"))
    def test_un_fallo_de_smtp_no_rompe_la_publicacion(self, mock_send_mail):
        # Si el servidor de email falla (SMTP caído, credenciales mal
        # puestas...), publicar el artículo tiene que seguir funcionando —
        # el artículo ya está guardado antes de intentar avisar a nadie.
        response = self.client.post(reverse("articles:create"), {
            "title": "Publicado pese al fallo de email", "body": "<p>cuerpo</p>", "tags_input": "",
        })
        article = Article.objects.get(title="Publicado pese al fallo de email")
        self.assertRedirects(response, article.get_absolute_url())


class ArticleIdeaAdminTests(TestCase):
    """Cuaderno de ideas para futuros artículos, desde el admin."""

    def setUp(self):
        self.admin = make_user("admin_ideas@test.local", User.Role.ADMIN)
        self.client.login(username=self.admin.email, password="Testpass123!")

    def test_crear_una_idea_apunta_quien_la_escribio(self):
        self.client.post(reverse("admin:articles_articleidea_add"), {
            "text": "Las mejores escenas de persecución de los 80", "notes": "", "is_done": "",
        })
        idea = ArticleIdea.objects.get(text="Las mejores escenas de persecución de los 80")
        self.assertEqual(idea.created_by, self.admin)
        self.assertFalse(idea.is_done)

    def test_se_puede_marcar_como_ya_escrita_desde_el_listado(self):
        idea = ArticleIdea.objects.create(text="Ranking de finales de saga", created_by=self.admin)
        response = self.client.get(reverse("admin:articles_articleidea_changelist"))
        self.assertContains(response, "Ranking de finales de saga")
        self.assertContains(response, 'name="form-0-is_done"')
