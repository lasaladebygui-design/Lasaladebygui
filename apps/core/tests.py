from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.articles.models import Article
from config.storage import supabase_public_domain

from .models import SESSION_THEME_KEY, ContactLink, SiteConfig, Theme, get_effective_theme


class HomeTests(TestCase):
    def test_muestra_como_mucho_los_cinco_ultimos_articulos(self):
        for i in range(7):
            Article.objects.create(title=f"Artículo {i}", body="Cuerpo")
        response = self.client.get(reverse("core:home"))
        self.assertEqual(len(response.context["featured_articles"]), 5)

    def test_el_titulo_enlaza_al_articulo(self):
        article = Article.objects.create(title="Mi artículo de prueba", body="Cuerpo")
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, article.get_absolute_url())
        self.assertContains(response, "Mi artículo de prueba")


class ContactFormTests(TestCase):
    def test_envio_valido_llega_al_email_configurado(self):
        config = SiteConfig.load()
        config.contact_email = "contacto@lasaladebygui.local"
        config.save()

        response = self.client.post(reverse("core:contact"), {
            "name": "Ana",
            "email": "ana@example.com",
            "message": "Hola, os escribo para...",
            "website": "",
        })
        self.assertRedirects(response, reverse("core:contact"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["contacto@lasaladebygui.local"])
        self.assertEqual(mail.outbox[0].reply_to, ["ana@example.com"])

    def test_honeypot_relleno_no_envia_email(self):
        config = SiteConfig.load()
        config.contact_email = "contacto@lasaladebygui.local"
        config.save()

        response = self.client.post(reverse("core:contact"), {
            "name": "Bot",
            "email": "bot@example.com",
            "message": "comprar barato ahora",
            "website": "http://spam.example.com",
        })
        self.assertRedirects(response, reverse("core:contact"))
        self.assertEqual(len(mail.outbox), 0)


class ContactLinkTests(TestCase):
    """Enlaces de contacto alternativos (Instagram, WhatsApp...): deben
    verse en /contacto/ tanto si el email de contacto está configurado
    como si no, ya que son una vía aparte."""

    def test_se_muestran_sin_email_de_contacto_configurado(self):
        ContactLink.objects.create(
            platform=ContactLink.Platform.INSTAGRAM, label="@lasaladebygui", url="https://instagram.com/lasaladebygui",
        )
        response = self.client.get(reverse("core:contact"))
        self.assertContains(response, "@lasaladebygui")
        self.assertContains(response, "https://instagram.com/lasaladebygui")

    def test_se_muestran_con_email_de_contacto_configurado(self):
        config = SiteConfig.load()
        config.contact_email = "contacto@lasaladebygui.local"
        config.save()
        ContactLink.objects.create(
            platform=ContactLink.Platform.WHATSAPP, label="600 000 000", url="https://wa.me/34600000000",
        )
        response = self.client.get(reverse("core:contact"))
        self.assertIsNotNone(response.context["form"])
        self.assertContains(response, "https://wa.me/34600000000")

    def test_orden_respeta_el_campo_order(self):
        segundo = ContactLink.objects.create(platform=ContactLink.Platform.OTRO, label="Segundo", url="https://b.example.com", order=2)
        primero = ContactLink.objects.create(platform=ContactLink.Platform.OTRO, label="Primero", url="https://a.example.com", order=1)
        response = self.client.get(reverse("core:contact"))
        self.assertEqual(list(response.context["contact_links"]), [primero, segundo])

    def test_icono_por_defecto_para_plataforma_no_reconocida(self):
        link = ContactLink.objects.create(platform="algo-raro", label="X", url="https://example.com")
        self.assertEqual(link.icon, "🔗")

    def test_icono_de_una_plataforma_conocida(self):
        link = ContactLink(platform=ContactLink.Platform.INSTAGRAM)
        self.assertEqual(link.icon, "📷")


class DonationsPageTests(TestCase):
    def test_muestra_el_numero_de_bizum_configurado(self):
        config = SiteConfig.load()
        config.bizum_number = "600 000 000"
        config.save()
        response = self.client.get(reverse("core:donations"))
        self.assertContains(response, "600 000 000")


class IntroAnimationTests(TestCase):
    def test_se_muestra_por_defecto(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'id="intro"')

    def test_se_oculta_si_se_desactiva_desde_el_admin(self):
        config = SiteConfig.load()
        config.show_intro_animation = False
        config.save()
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, 'id="intro"')


class BootstrapProductionTests(TestCase):
    def test_sin_variables_no_hace_nada(self):
        call_command("bootstrap_production")
        self.assertFalse(User.objects.exists())

    def test_crea_admin_si_se_piden_las_variables(self):
        import os

        os.environ["DJANGO_SUPERUSER_EMAIL"] = "admin@lasaladebygui.local"
        os.environ["DJANGO_SUPERUSER_PASSWORD"] = "Testpass123!"
        try:
            call_command("bootstrap_production")
        finally:
            del os.environ["DJANGO_SUPERUSER_EMAIL"]
            del os.environ["DJANGO_SUPERUSER_PASSWORD"]

        user = User.objects.get(email="admin@lasaladebygui.local")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("Testpass123!"))

    def test_no_crea_un_segundo_admin_si_ya_existe_uno(self):
        import os

        existing = User(email="ya-existe@lasaladebygui.local", role=User.Role.ADMIN)
        existing.set_password("Otra1234!")
        existing.save()

        os.environ["DJANGO_SUPERUSER_EMAIL"] = "otro@lasaladebygui.local"
        os.environ["DJANGO_SUPERUSER_PASSWORD"] = "Testpass123!"
        try:
            call_command("bootstrap_production")
        finally:
            del os.environ["DJANGO_SUPERUSER_EMAIL"]
            del os.environ["DJANGO_SUPERUSER_PASSWORD"]

        self.assertFalse(User.objects.filter(email="otro@lasaladebygui.local").exists())

    def test_run_seed_quotes_carga_las_frases(self):
        import os

        from apps.games.models import MovieQuote

        os.environ["RUN_SEED_QUOTES"] = "true"
        try:
            call_command("bootstrap_production")
        finally:
            del os.environ["RUN_SEED_QUOTES"]

        self.assertTrue(MovieQuote.objects.exists())

    def test_sin_run_seed_quotes_no_carga_nada(self):
        from apps.games.models import MovieQuote

        call_command("bootstrap_production")
        self.assertFalse(MovieQuote.objects.exists())


class ServiceWorkerTests(TestCase):
    """El service worker se sirve en /sw.js (raíz), no bajo /static/js/: es
    lo que le da scope de todo el sitio en vez de solo /static/js/."""

    def test_se_sirve_en_la_raiz_con_scope_de_todo_el_sitio(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertIn("javascript", response["Content-Type"])


class ThemeSwitcherTests(TestCase):
    def setUp(self):
        self.noir = Theme.objects.get(slug="noir")
        self.vintage = Theme.objects.get(slug="vintage")

    def test_anonimo_cambia_tema_via_sesion(self):
        response = self.client.post(reverse("core:set-theme", args=[self.noir.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[SESSION_THEME_KEY], "noir")

        theme = get_effective_theme(None, self.client.session)
        self.assertEqual(theme, self.noir)

    def test_anonimo_ve_el_tema_en_theme_css(self):
        self.client.post(reverse("core:set-theme", args=[self.vintage.slug]))
        response = self.client.get(reverse("theme-css"))
        self.assertContains(response, self.vintage.color_bg)

    def test_usuario_logueado_guarda_en_su_cuenta_no_en_sesion(self):
        user = User.objects.create(email="lector@test.local", role=User.Role.LECTOR)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        self.client.post(reverse("core:set-theme", args=[self.noir.slug]))
        user.refresh_from_db()
        self.assertEqual(user.theme, self.noir)
        self.assertNotIn(SESSION_THEME_KEY, self.client.session)

    def test_reset_theme_quita_la_preferencia(self):
        user = User.objects.create(email="lector2@test.local", role=User.Role.LECTOR, theme=self.noir)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        self.client.post(reverse("core:reset-theme"))
        user.refresh_from_db()
        self.assertIsNone(user.theme)

    def test_theme_css_no_se_cachea_publicamente(self):
        response = self.client.get(reverse("theme-css"))
        self.assertIn("no-cache", response.headers["Cache-Control"])
        self.assertIn("private", response.headers["Cache-Control"])


class SupabasePublicDomainTests(TestCase):
    """Marcar un bucket de Supabase como 'Public' no lo hace accesible por
    la URL del endpoint S3 (esa exige petición firmada siempre) — hace
    falta la URL nativa .../storage/v1/object/public/<bucket>/... Esto
    verifica que la construimos bien a partir del endpoint S3 configurado."""

    def test_deriva_el_dominio_publico_desde_el_endpoint_s3(self):
        domain = supabase_public_domain(
            "https://xpleukpsphqwuvshyyls.storage.supabase.co/storage/v1/s3", "media",
        )
        self.assertEqual(
            domain,
            "xpleukpsphqwuvshyyls.supabase.co/storage/v1/object/public/media",
        )

    def test_usa_el_nombre_del_bucket_configurado(self):
        domain = supabase_public_domain(
            "https://otro-proyecto.storage.supabase.co/storage/v1/s3", "avatares",
        )
        self.assertIn("/object/public/avatares", domain)


class AdminAccessTests(TestCase):
    """/admin/ debe ser solo para el Admin (is_superuser) — Gestor y Editor
    son is_staff (para sus permisos puntuales dentro del propio /admin/,
    como el Gestor con el foro) pero no deben poder entrar al panel."""

    def _login_as(self, email, role):
        user = User.objects.create(email=email, role=role)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=email, password="Testpass123!")
        return user

    def test_admin_entra(self):
        self._login_as("admin@test.local", User.Role.ADMIN)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)

    def test_gestor_no_entra(self):
        self._login_as("gestor@test.local", User.Role.GESTOR)
        response = self.client.get(reverse("admin:index"))
        self.assertRedirects(response, "/admin/login/?next=/admin/", fetch_redirect_response=False)

    def test_editor_no_entra(self):
        self._login_as("editor@test.local", User.Role.EDITOR)
        response = self.client.get(reverse("admin:index"))
        self.assertRedirects(response, "/admin/login/?next=/admin/", fetch_redirect_response=False)

    def test_anonimo_no_entra(self):
        response = self.client.get(reverse("admin:index"))
        self.assertRedirects(response, "/admin/login/?next=/admin/", fetch_redirect_response=False)
