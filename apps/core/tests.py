from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

from .models import SiteConfig


class ContactFormTests(TestCase):
    def test_sin_email_de_contacto_configurado_no_muestra_formulario(self):
        response = self.client.get(reverse("core:contact"))
        self.assertIsNone(response.context["form"])

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
