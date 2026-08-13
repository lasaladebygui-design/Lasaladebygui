import io
import json
import re
import tempfile
from unittest.mock import patch

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.forum.models import Thread
from apps.movies.models import Movie
from apps.movies.services import MovieAPIError

from .models import FavoriteMovie, GoogleCalendarConnection, PushSubscription, User

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

    def test_gestor_tiene_permisos_django_sobre_el_foro_aunque_no_entre_al_admin(self):
        # /admin/ en sí es solo para el Admin (ver apps/core/apps.py y
        # apps/core/tests.py::AdminAccessTests) — pero el Gestor conserva
        # los permisos Django reales sobre el foro (por si en el futuro se
        # necesitan fuera del panel), aunque no pueda usarlos desde /admin/.
        user = User.objects.create(email="gestor3@test.local", role=User.Role.GESTOR)
        user.set_password("Testpass123!")
        user.save()
        thread = Thread.objects.create(title="Hilo", body="cuerpo")

        self.assertTrue(user.has_perm("forum.change_thread"))

        self.client.login(username=user.email, password="Testpass123!")
        response = self.client.get(f"/admin/forum/thread/{thread.pk}/change/")
        self.assertEqual(response.status_code, 302)


class CaseInsensitiveLoginTests(TestCase):
    """El email es el identificador de acceso: iniciar sesión no debe
    depender de acertar las mayúsculas exactas con las que se registró la
    cuenta, y guardar un email nuevo lo normaliza a minúsculas desde el
    principio para que no puedan convivir dos cuentas que solo difieran en
    eso."""

    def setUp(self):
        self.user = User.objects.create(email="persona@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()

    def test_email_se_guarda_en_minusculas(self):
        user = User.objects.create(email="OTRA.Persona@Test.Local", role=User.Role.LECTOR)
        self.assertEqual(user.email, "otra.persona@test.local")

    def test_login_con_mayusculas_distintas_funciona(self):
        logged_in = self.client.login(username="PERSONA@TEST.LOCAL", password="Testpass123!")
        self.assertTrue(logged_in)

    def test_login_con_mezcla_de_mayusculas_funciona(self):
        logged_in = self.client.login(username="PersonA@Test.Local", password="Testpass123!")
        self.assertTrue(logged_in)

    def test_login_con_contrasena_incorrecta_sigue_fallando(self):
        logged_in = self.client.login(username="PERSONA@TEST.LOCAL", password="Incorrecta123!")
        self.assertFalse(logged_in)

    def test_login_con_email_inexistente_falla(self):
        logged_in = self.client.login(username="NADIE@TEST.LOCAL", password="Testpass123!")
        self.assertFalse(logged_in)


class AdminBackupPasswordTests(TestCase):
    """Contraseña de respaldo para Admin (AdminBackupPasswordBackend) —
    desactivada por defecto, solo funciona si ADMIN_BACKUP_PASSWORD está
    puesta, y solo para cuentas que ya son Admin."""

    def setUp(self):
        self.admin = User.objects.create(email="admin_backup@test.local", role=User.Role.ADMIN)
        self.admin.set_password("ContraseñaRealDelAdmin123!")
        self.admin.save()
        self.lector = User.objects.create(email="lector_backup@test.local", role=User.Role.LECTOR)
        self.lector.set_password("Testpass123!")
        self.lector.save()

    def test_desactivada_por_defecto(self):
        logged_in = self.client.login(username=self.admin.email, password="8888")
        self.assertFalse(logged_in)

    @override_settings(ADMIN_BACKUP_PASSWORD="8888")
    def test_funciona_para_admin_cuando_esta_activa(self):
        logged_in = self.client.login(username=self.admin.email, password="8888")
        self.assertTrue(logged_in)

    @override_settings(ADMIN_BACKUP_PASSWORD="8888")
    def test_no_funciona_para_una_cuenta_que_no_es_admin(self):
        # El lector cuya contraseña REAL es literalmente "8888" no debe
        # colarse por aquí: el backend exige role=ADMIN, no solo que la
        # contraseña coincida (eso ya lo cubre el backend normal).
        logged_in = self.client.login(username=self.lector.email, password="8888")
        self.assertFalse(logged_in)

    @override_settings(ADMIN_BACKUP_PASSWORD="8888")
    def test_la_contrasena_real_sigue_funcionando_con_la_de_respaldo_activa(self):
        logged_in = self.client.login(username=self.admin.email, password="ContraseñaRealDelAdmin123!")
        self.assertTrue(logged_in)

    @override_settings(ADMIN_BACKUP_PASSWORD="8888")
    def test_otra_contrasena_cualquiera_sigue_fallando(self):
        logged_in = self.client.login(username=self.admin.email, password="cualquier-otra-cosa")
        self.assertFalse(logged_in)


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


class BanKicksActiveSessionTests(TestCase):
    """Banear no solo bloquea futuros inicios de sesión: si el usuario ya
    tenía una sesión abierta, se corta al instante."""

    def setUp(self):
        self.user = User.objects.create(email="activo@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()

    def test_banear_desloguea_una_sesion_activa(self):
        self.client.login(username=self.user.email, password="Testpass123!")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

        self.user.role = User.Role.BANEADO
        self.user.save()

        response = self.client.get(reverse("accounts:profile"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('accounts:profile')}")

    def test_guardar_sin_cambiar_el_rol_no_afecta_la_sesion(self):
        self.client.login(username=self.user.email, password="Testpass123!")
        self.user.bio = "Actualizando el perfil"
        self.user.save()

        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)


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
        response = self.client.post(reverse("accounts:settings"), {
            "avatar": _fake_image(),
        })
        self.assertRedirects(response, reverse("accounts:settings"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name.startswith("avatars/"))

    def test_sin_avatar_muestra_placeholder(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "profile-avatar--placeholder")

    def test_el_perfil_incluye_el_pool_de_frases_para_la_frase_dinamica(self):
        from apps.games.models import MovieQuote

        MovieQuote.objects.create(
            quote="Frase de prueba sin caracteres especiales",
            correct_title="Película X", wrong_title_1="Y", wrong_title_2="Z",
        )
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "rotating-quotes-data")
        self.assertContains(response, "Frase de prueba sin caracteres especiales")

    def test_el_perfil_enlaza_a_ajustes_no_a_cerrar_sesion_directamente(self):
        # El "Salir" del menú ☰ de la cabecera sale en todas las páginas (no
        # es esto lo que se comprueba); lo que no debe tener el propio
        # cuerpo del perfil es su antiguo botón "Cerrar sesión".
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, reverse("accounts:settings"))
        self.assertNotContains(response, "Cerrar sesión")

    def test_ajustes_tiene_boton_de_cerrar_sesion(self):
        response = self.client.get(reverse("accounts:settings"))
        self.assertContains(response, reverse("accounts:logout"))
        self.assertContains(response, "Cerrar sesión")

    def test_cerrar_sesion_desde_el_perfil_desloguea(self):
        self.client.post(reverse("accounts:logout"))
        response = self.client.get(reverse("accounts:profile"))
        self.assertNotEqual(response.status_code, 200)

    def test_sin_frases_celebres_el_perfil_no_falla(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "rotating-quotes-data")

    def test_el_perfil_enlaza_a_ver_logros(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, reverse("accounts:achievements"))


class UsernameChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="nick@test.local", role=User.Role.LECTOR, username="nick_viejo")
        self.user.set_password("Testpass123!")
        self.user.save()
        self.other = User.objects.create(email="otro@test.local", role=User.Role.LECTOR, username="ya_existe")
        self.other.set_password("Testpass123!")
        self.other.save()
        self.client.login(username=self.user.email, password="Testpass123!")

    def test_ajustes_muestra_el_formulario_de_nombre_de_usuario(self):
        response = self.client.get(reverse("accounts:settings"))
        self.assertContains(response, "nick_viejo")

    def test_cambiar_el_nombre_de_usuario(self):
        response = self.client.post(reverse("accounts:change-username"), {"username": "nick_nuevo"})
        self.assertRedirects(response, reverse("accounts:settings"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "nick_nuevo")

    def test_no_se_puede_repetir_un_nombre_de_usuario_ya_en_uso(self):
        self.client.post(reverse("accounts:change-username"), {"username": "ya_existe"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "nick_viejo")

    def test_no_se_permiten_caracteres_invalidos(self):
        self.client.post(reverse("accounts:change-username"), {"username": "con espacios!"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "nick_viejo")


class UserAdminBroadcastEmailTests(TestCase):
    """Desde el admin de usuarios: seleccionar varios (o "todos" con el
    enlace nativo de Django de seleccionar todas las páginas) y mandarles
    un email desde una pantalla intermedia con asunto y mensaje."""

    def setUp(self):
        self.admin = User.objects.create(email="admin_broadcast@test.local", role=User.Role.ADMIN)
        self.admin.set_password("Testpass123!")
        self.admin.save()
        self.user_a = User.objects.create(email="destino_a@test.local", role=User.Role.LECTOR)
        self.user_b = User.objects.create(email="destino_b@test.local", role=User.Role.LECTOR)
        self.client.login(username=self.admin.email, password="Testpass123!")

    def test_la_accion_redirige_a_la_pantalla_de_envio_con_los_ids(self):
        response = self.client.post(reverse("admin:accounts_user_changelist"), {
            "action": "enviar_email",
            "_selected_action": [self.user_a.pk, self.user_b.pk],
        })
        self.assertEqual(response.status_code, 302)
        ids_param = response.url.split("ids=")[1]
        self.assertEqual(set(ids_param.split(",")), {str(self.user_a.pk), str(self.user_b.pk)})

    def test_la_pantalla_de_envio_lista_los_destinatarios(self):
        url = reverse("admin:accounts_user_send_email") + f"?ids={self.user_a.pk},{self.user_b.pk}"
        response = self.client.get(url)
        self.assertContains(response, self.user_a.email)
        self.assertContains(response, self.user_b.email)

    def test_enviar_manda_un_email_a_cada_destinatario_seleccionado(self):
        url = reverse("admin:accounts_user_send_email")
        response = self.client.post(url, {
            "ids": f"{self.user_a.pk},{self.user_b.pk}",
            "subject": "Aviso importante",
            "message": "Hola, esto es un aviso.",
        })
        self.assertRedirects(response, reverse("admin:accounts_user_changelist"))
        self.assertEqual(len(mail.outbox), 2)
        recipients = {sent.to[0] for sent in mail.outbox}
        self.assertEqual(recipients, {self.user_a.email, self.user_b.email})
        self.assertEqual(mail.outbox[0].subject, "Aviso importante")

    def test_las_acciones_del_listado_salen_como_botones_no_como_desplegable(self):
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertContains(response, "admin-action-buttons__btn")
        self.assertContains(response, "📧 Enviar un email a los seleccionados")

    def test_no_es_accesible_para_quien_no_es_staff(self):
        self.client.logout()
        lector = User.objects.create(email="lector_broadcast@test.local", role=User.Role.LECTOR)
        lector.set_password("Testpass123!")
        lector.save()
        self.client.login(username=lector.email, password="Testpass123!")
        response = self.client.get(reverse("admin:accounts_user_send_email") + f"?ids={self.user_a.pk}")
        self.assertNotEqual(response.status_code, 200)


class UserAdminResetDuelsTests(TestCase):
    """Solo desde el admin (no hay nada equivalente en la web pública):
    borra el marcador histórico de duelos de la cuenta seleccionada contra
    todos sus rivales."""

    def setUp(self):
        self.admin = User.objects.create(email="admin_duelos@test.local", role=User.Role.ADMIN)
        self.admin.set_password("Testpass123!")
        self.admin.save()
        self.a = User.objects.create(email="jugador_a@test.local", role=User.Role.LECTOR)
        self.b = User.objects.create(email="jugador_b@test.local", role=User.Role.LECTOR)
        self.c = User.objects.create(email="jugador_c@test.local", role=User.Role.LECTOR)
        self.client.login(username=self.admin.email, password="Testpass123!")

    def test_borra_el_marcador_con_todos_sus_rivales(self):
        from apps.games.models import DuelRecord

        DuelRecord.record_result(self.a, self.b, winner=self.a)
        DuelRecord.record_result(self.a, self.c, winner=self.c)

        self.client.post(reverse("admin:accounts_user_changelist"), {
            "action": "resetear_duelos",
            "_selected_action": [self.a.pk],
        })

        self.assertIsNone(DuelRecord.get_for(self.a, self.b))
        self.assertIsNone(DuelRecord.get_for(self.a, self.c))

    def test_no_toca_el_marcador_de_otros_usuarios(self):
        from apps.games.models import DuelRecord

        DuelRecord.record_result(self.b, self.c, winner=self.b)

        self.client.post(reverse("admin:accounts_user_changelist"), {
            "action": "resetear_duelos",
            "_selected_action": [self.a.pk],
        })

        self.assertIsNotNone(DuelRecord.get_for(self.b, self.c))


class AchievementsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            email="logros@test.local", role=User.Role.LECTOR,
            quote_streak_best=5, rating_duel_streak_best_movie=3, trivia_streak_best=2,
        )
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")

    def test_requiere_login(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:achievements"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('accounts:achievements')}")

    def test_muestra_las_rachas_de_todos_los_juegos(self):
        response = self.client.get(reverse("accounts:achievements"))
        self.assertContains(response, "Frases célebres")
        self.assertContains(response, "Trivial")
        self.assertContains(response, "Verdadero o falso")

    def test_muestra_el_marcador_de_duelos_acumulado_de_varios_rivales(self):
        from apps.games.models import DuelRecord

        rival_a = User.objects.create(email="rival_a@test.local", role=User.Role.LECTOR)
        rival_b = User.objects.create(email="rival_b@test.local", role=User.Role.LECTOR)
        DuelRecord.record_result(self.user, rival_a, self.user)
        DuelRecord.record_result(self.user, rival_a, self.user)
        DuelRecord.record_result(self.user, rival_b, rival_b)
        DuelRecord.record_result(self.user, rival_b, None)

        response = self.client.get(reverse("accounts:achievements"))
        self.assertEqual(response.context["duel_summary"]["wins"], 2)
        self.assertEqual(response.context["duel_summary"]["losses"], 1)
        self.assertEqual(response.context["duel_summary"]["draws"], 1)


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



class SettingsPageTests(TestCase):
    """Ajustes reúne lo que antes vivía suelto por el perfil (o no existía):
    rango, tema, animación de intro, sugerencia de instalar la app,
    notificaciones, Google Calendar, cambiar contraseña y cerrar sesión —
    el perfil se queda solo con la frase dinámica, las rachas de juegos,
    imprescindibles/sugeridas y el botón a Ajustes."""

    def setUp(self):
        self.user = User.objects.create(email="ajustes@test.local", role=User.Role.EDITOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")

    def test_requiere_login(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:settings"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('accounts:settings')}")

    def test_muestra_el_rango(self):
        response = self.client.get(reverse("accounts:settings"))
        self.assertContains(response, "Editor")

    def test_activar_animacion_de_intro(self):
        self.client.post(reverse("accounts:set-intro-animation"), {"value": "on"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.show_intro_animation)

    def test_desactivar_animacion_de_intro(self):
        self.client.post(reverse("accounts:set-intro-animation"), {"value": "off"})
        self.user.refresh_from_db()
        self.assertFalse(self.user.show_intro_animation)

    def test_animacion_como_el_sitio_limpia_la_preferencia(self):
        self.user.show_intro_animation = True
        self.user.save(update_fields=["show_intro_animation"])
        self.client.post(reverse("accounts:set-intro-animation"), {"value": "site"})
        self.user.refresh_from_db()
        self.assertIsNone(self.user.show_intro_animation)

    def test_alternar_sugerencia_de_instalar_la_app(self):
        self.assertFalse(self.user.hide_pwa_install_prompt)
        self.client.post(reverse("accounts:toggle-pwa-prompt"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.hide_pwa_install_prompt)
        self.client.post(reverse("accounts:toggle-pwa-prompt"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.hide_pwa_install_prompt)

    def test_pagina_de_cambiar_contrasena_accesible(self):
        response = self.client.get(reverse("accounts:password-change"))
        self.assertEqual(response.status_code, 200)

    def test_cambiar_contrasena(self):
        response = self.client.post(reverse("accounts:password-change"), {
            "old_password": "Testpass123!",
            "new_password1": "OtraClaveSegura9!",
            "new_password2": "OtraClaveSegura9!",
        })
        self.assertRedirects(response, reverse("accounts:password-change-done"))
        self.client.logout()
        self.assertTrue(self.client.login(username=self.user.email, password="OtraClaveSegura9!"))


class FavoriteMovieTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="favoritos@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")

    @patch("apps.accounts.views.tmdb_search")
    def test_buscar_usa_el_servicio_tmdb(self, mock_search):
        mock_search.return_value = []
        response = self.client.get(
            reverse("accounts:favorite-search", args=["essential", "movie"]), {"query": "matrix"}
        )
        self.assertEqual(response.status_code, 200)
        mock_search.assert_called_once_with("matrix", media_type="movie")

    def test_categoria_invalida_da_404(self):
        response = self.client.get(
            reverse("accounts:favorite-search", args=["otra-cosa", "movie"]), {"query": "matrix"}
        )
        self.assertEqual(response.status_code, 404)

    def test_tipo_invalido_da_404(self):
        response = self.client.get(
            reverse("accounts:favorite-search", args=["essential", "libro"]), {"query": "matrix"}
        )
        self.assertEqual(response.status_code, 404)

    @patch("apps.accounts.views.tmdb_search")
    def test_buscar_con_tipo_all_combina_pelicula_y_serie(self, mock_search):
        def fake_search(query, media_type="movie"):
            from apps.movies.services import TMDbResult
            return [TMDbResult(tmdb_id=1, title=f"Resultado {media_type}", year="2020", poster_path="", overview="", media_type=media_type)]

        mock_search.side_effect = fake_search
        response = self.client.get(
            reverse("accounts:favorite-search", args=["essential", "all"]), {"query": "matrix"}
        )
        self.assertEqual(response.status_code, 200)
        mock_search.assert_any_call("matrix", media_type="movie")
        mock_search.assert_any_call("matrix", media_type="tv")
        media_types = [r.media_type for r in response.context["results"]]
        self.assertEqual(set(media_types), {"movie", "tv"})

    @patch("apps.accounts.views.Movie.get_or_create_from_tmdb")
    def test_anadir_pelicula_a_imprescindibles(self, mock_get_or_create):
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=1, title="Matrix", media_type="movie")
        response = self.client.post(reverse("accounts:favorite-add", args=["essential", "movie", 1]))
        self.assertRedirects(response, reverse("accounts:favorites-page", args=["essential"]))
        self.assertTrue(FavoriteMovie.objects.filter(user=self.user, category="essential", movie__tmdb_id=1).exists())
        mock_get_or_create.assert_called_once_with(1, media_type="movie")

    @patch("apps.accounts.views.Movie.get_or_create_from_tmdb")
    def test_anadir_serie_a_imprescindibles(self, mock_get_or_create):
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=1, title="Dark", media_type="tv")
        response = self.client.post(reverse("accounts:favorite-add", args=["essential", "tv", 1]))
        self.assertRedirects(response, reverse("accounts:favorites-page", args=["essential"]))
        self.assertTrue(FavoriteMovie.objects.filter(user=self.user, category="essential", movie__media_type="tv").exists())

    @patch("apps.accounts.views.Movie.get_or_create_from_tmdb")
    def test_no_hay_limite_de_imprescindibles(self, mock_get_or_create):
        for i in range(10):
            movie = Movie.objects.create(tmdb_id=i, title=f"Película {i}", media_type="movie")
            FavoriteMovie.objects.create(user=self.user, category="essential", movie=movie, order=i)

        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=99, title="Una más", media_type="movie")
        self.client.post(reverse("accounts:favorite-add", args=["essential", "movie", 99]))

        self.assertEqual(
            FavoriteMovie.objects.filter(user=self.user, category="essential", movie__media_type="movie").count(), 11
        )

    @patch("apps.accounts.views.Movie.get_or_create_from_tmdb")
    def test_no_hay_limite_de_sugeridas(self, mock_get_or_create):
        for i in range(10):
            movie = Movie.objects.create(tmdb_id=i, title=f"Película {i}", media_type="movie")
            FavoriteMovie.objects.create(user=self.user, category="suggested", movie=movie, order=i)

        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=99, title="Una más", media_type="movie")
        self.client.post(reverse("accounts:favorite-add", args=["suggested", "movie", 99]))

        self.assertEqual(
            FavoriteMovie.objects.filter(user=self.user, category="suggested", movie__media_type="movie").count(), 11
        )

    def test_quitar_una_favorita(self):
        movie = Movie.objects.create(tmdb_id=5, title="Se va", media_type="movie")
        favorite = FavoriteMovie.objects.create(user=self.user, category="essential", movie=movie)
        response = self.client.post(reverse("accounts:favorite-remove", args=[favorite.pk]))
        self.assertRedirects(response, reverse("accounts:favorites-page", args=["essential"]))
        self.assertFalse(FavoriteMovie.objects.filter(pk=favorite.pk).exists())

    def test_no_se_puede_quitar_una_favorita_ajena(self):
        other = User.objects.create(email="otro_fav@test.local", role=User.Role.LECTOR)
        movie = Movie.objects.create(tmdb_id=6, title="No es tuya", media_type="movie")
        favorite = FavoriteMovie.objects.create(user=other, category="essential", movie=movie)
        response = self.client.post(reverse("accounts:favorite-remove", args=[favorite.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(FavoriteMovie.objects.filter(pk=favorite.pk).exists())

    def test_mover_una_favorita_cambia_el_orden(self):
        movie_a = Movie.objects.create(tmdb_id=10, title="A", media_type="movie")
        movie_b = Movie.objects.create(tmdb_id=11, title="B", media_type="movie")
        fav_a = FavoriteMovie.objects.create(user=self.user, category="essential", movie=movie_a, order=0)
        fav_b = FavoriteMovie.objects.create(user=self.user, category="essential", movie=movie_b, order=1)

        self.client.post(reverse("accounts:favorite-move", args=[fav_b.pk, "up"]))

        fav_a.refresh_from_db()
        fav_b.refresh_from_db()
        self.assertEqual(fav_b.order, 0)
        self.assertEqual(fav_a.order, 1)

    def test_reordenar_por_arrastre_aplica_el_orden_recibido(self):
        import json

        movie_a = Movie.objects.create(tmdb_id=12, title="A", media_type="movie")
        movie_b = Movie.objects.create(tmdb_id=13, title="B", media_type="movie")
        fav_a = FavoriteMovie.objects.create(user=self.user, category="essential", movie=movie_a, order=0)
        fav_b = FavoriteMovie.objects.create(user=self.user, category="essential", movie=movie_b, order=1)

        response = self.client.post(
            reverse("accounts:favorite-reorder", args=["essential", "movie"]),
            data=json.dumps({"order": [fav_b.pk, fav_a.pk]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        fav_a.refresh_from_db(); fav_b.refresh_from_db()
        self.assertEqual((fav_b.order, fav_a.order), (0, 1))

    def test_reordenar_por_arrastre_no_mezcla_peliculas_y_series(self):
        import json

        movie = Movie.objects.create(tmdb_id=14, title="Peli", media_type="movie")
        series = Movie.objects.create(tmdb_id=15, title="Serie", media_type="tv")
        fav_movie = FavoriteMovie.objects.create(user=self.user, category="essential", movie=movie, order=0)
        fav_series = FavoriteMovie.objects.create(user=self.user, category="essential", movie=series, order=0)

        response = self.client.post(
            reverse("accounts:favorite-reorder", args=["essential", "movie"]),
            data=json.dumps({"order": [fav_series.pk]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        fav_series.refresh_from_db()
        self.assertEqual(fav_series.order, 0)

    def test_reordenar_por_arrastre_no_afecta_favoritas_de_otro_usuario(self):
        import json

        other = User.objects.create(email="otro_reordenar@test.local", role=User.Role.LECTOR)
        movie = Movie.objects.create(tmdb_id=16, title="Ajena", media_type="movie")
        ajena = FavoriteMovie.objects.create(user=other, category="essential", movie=movie, order=0)

        response = self.client.post(
            reverse("accounts:favorite-reorder", args=["essential", "movie"]),
            data=json.dumps({"order": [ajena.pk]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        ajena.refresh_from_db()
        self.assertEqual(ajena.order, 0)

    def test_el_perfil_enlaza_a_las_dos_paginas_de_favoritas_con_su_contador(self):
        movie = Movie.objects.create(tmdb_id=7, title="Mi favorita", poster_path="/x.jpg", media_type="movie")
        FavoriteMovie.objects.create(user=self.user, category="essential", movie=movie)
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, reverse("accounts:favorites-page", args=["essential"]))
        self.assertContains(response, reverse("accounts:favorites-page", args=["suggested"]))
        self.assertContains(response, "Mis imprescindibles (1)")

    def test_pagina_de_imprescindibles_muestra_las_favoritas(self):
        movie = Movie.objects.create(tmdb_id=7, title="Mi favorita", poster_path="/x.jpg", media_type="movie")
        FavoriteMovie.objects.create(user=self.user, category="essential", movie=movie)
        response = self.client.get(reverse("accounts:favorites-page", args=["essential"]))
        self.assertContains(response, "Mi favorita")

    def test_pagina_de_categoria_invalida_da_404(self):
        response = self.client.get(reverse("accounts:favorites-page", args=["otra-cosa"]))
        self.assertEqual(response.status_code, 404)

    def test_compartir_imprescindibles_devuelve_una_imagen_png(self):
        movie = Movie.objects.create(tmdb_id=20, title="Mi favorita", media_type="movie")
        FavoriteMovie.objects.create(user=self.user, category="essential", movie=movie)
        self.user.essential_note = "Porque me marcaron"
        self.user.save(update_fields=["essential_note"])

        response = self.client.get(reverse("accounts:favorites-share-image", args=["essential"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_compartir_con_porque_en_varios_parrafos_no_rompe(self):
        movie = Movie.objects.create(tmdb_id=22, title="Mi favorita 2", media_type="movie")
        FavoriteMovie.objects.create(user=self.user, category="essential", movie=movie)
        self.user.essential_note = "Primer párrafo.\n\nSegundo párrafo, distinto del primero."
        self.user.save(update_fields=["essential_note"])

        response = self.client.get(reverse("accounts:favorites-share-image", args=["essential"]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_wrap_text_respeta_los_saltos_de_linea(self):
        from PIL import Image, ImageDraw, ImageFont

        from apps.accounts.views import _wrap_text

        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        font = ImageFont.load_default(size=13)
        lines = _wrap_text(draw, "Primer parrafo.\n\nSegundo parrafo.", font, max_width=400)
        self.assertEqual(lines, ["Primer parrafo.", "", "Segundo parrafo."])

    def test_compartir_sin_favoritas_no_rompe(self):
        response = self.client.get(reverse("accounts:favorites-share-image", args=["essential"]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_compartir_categoria_invalida_da_404(self):
        response = self.client.get(reverse("accounts:favorites-share-image", args=["otra-cosa"]))
        self.assertEqual(response.status_code, 404)

    def test_compartir_requiere_login(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:favorites-share-image", args=["essential"]))
        self.assertNotEqual(response.status_code, 200)

    def test_el_boton_compartir_solo_sale_en_la_pagina_propia(self):
        other = User.objects.create(email="visto_fav3@test.local", role=User.Role.LECTOR, username="vistofav3")
        movie = Movie.objects.create(tmdb_id=21, title="Favorita ajena 3", media_type="movie")
        FavoriteMovie.objects.create(user=other, category="essential", movie=movie)
        share_url = reverse("accounts:favorites-share-image", args=["essential"])

        own = self.client.get(reverse("accounts:favorites-page", args=["essential"]))
        self.assertContains(own, share_url)

        ajena = self.client.get(reverse("social:public-favorites-page", args=["vistofav3", "essential"]))
        self.assertNotContains(ajena, share_url)

    def test_el_perfil_publico_enlaza_a_las_paginas_de_favoritas_de_otro(self):
        other = User.objects.create(email="visto_fav@test.local", role=User.Role.LECTOR, username="vistofav")
        movie = Movie.objects.create(tmdb_id=8, title="Favorita ajena", media_type="movie")
        FavoriteMovie.objects.create(user=other, category="essential", movie=movie)

        response = self.client.get(reverse("social:public-profile", kwargs={"username": "vistofav"}))
        self.assertContains(response, reverse("social:public-favorites-page", args=["vistofav", "essential"]))

    def test_pagina_publica_de_favoritas_de_otro_no_tiene_boton_de_quitar(self):
        other = User.objects.create(email="visto_fav2@test.local", role=User.Role.LECTOR, username="vistofav2")
        movie = Movie.objects.create(tmdb_id=13, title="Favorita ajena 2", media_type="movie")
        FavoriteMovie.objects.create(user=other, category="essential", movie=movie)

        response = self.client.get(reverse("social:public-favorites-page", args=["vistofav2", "essential"]))
        self.assertContains(response, "Favorita ajena 2")
        self.assertNotContains(response, "favorite-remove")

    def test_guardar_nota_del_apartado_de_sugeridas(self):
        response = self.client.post(
            reverse("accounts:favorite-category-note", args=["suggested"]), {"note": "Porque sí, son geniales"}
        )
        self.assertRedirects(response, reverse("accounts:favorites-page", args=["suggested"]))
        self.user.refresh_from_db()
        self.assertEqual(self.user.suggested_note, "Porque sí, son geniales")

    def test_guardar_nota_no_afecta_al_otro_apartado(self):
        self.client.post(reverse("accounts:favorite-category-note", args=["suggested"]), {"note": "Sugeridas"})
        self.client.post(reverse("accounts:favorite-category-note", args=["essential"]), {"note": "Imprescindibles"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.suggested_note, "Sugeridas")
        self.assertEqual(self.user.essential_note, "Imprescindibles")

    def test_no_se_puede_editar_la_nota_de_otro_usuario(self):
        other = User.objects.create(email="otro_nota@test.local", role=User.Role.LECTOR, suggested_note="Original")

        self.client.post(reverse("accounts:favorite-category-note", args=["suggested"]), {"note": "Robada"})
        other.refresh_from_db()
        self.assertEqual(other.suggested_note, "Original")

    def test_la_nota_no_tiene_limite_de_longitud(self):
        self.client.post(reverse("accounts:favorite-category-note", args=["suggested"]), {"note": "x" * 500})
        self.user.refresh_from_db()
        self.assertEqual(len(self.user.suggested_note), 500)

    def test_la_pagina_de_sugeridas_muestra_la_nota_del_apartado(self):
        self.user.suggested_note = "Un gran apartado"
        self.user.save(update_fields=["suggested_note"])

        response = self.client.get(reverse("accounts:favorites-page", args=["suggested"]))
        self.assertContains(response, "Un gran apartado")


class PushSubscriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="push@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")

    def _payload(self, endpoint="https://push.example/abc"):
        return {"endpoint": endpoint, "keys": {"p256dh": "clave-p256dh", "auth": "clave-auth"}}

    def test_requiere_login(self):
        self.client.logout()
        response = self.client.post(
            reverse("accounts:push-subscribe"), data=json.dumps(self._payload()), content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)

    def test_suscribir_crea_una_suscripcion(self):
        response = self.client.post(
            reverse("accounts:push-subscribe"), data=json.dumps(self._payload()), content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            PushSubscription.objects.filter(user=self.user, endpoint="https://push.example/abc").exists()
        )

    def test_suscribir_con_el_mismo_endpoint_actualiza_en_vez_de_duplicar(self):
        self.client.post(
            reverse("accounts:push-subscribe"), data=json.dumps(self._payload()), content_type="application/json",
        )
        self.client.post(
            reverse("accounts:push-subscribe"), data=json.dumps(self._payload()), content_type="application/json",
        )
        self.assertEqual(PushSubscription.objects.filter(endpoint="https://push.example/abc").count(), 1)

    def test_datos_invalidos_da_400(self):
        response = self.client.post(
            reverse("accounts:push-subscribe"), data=json.dumps({"algo": "raro"}), content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_desuscribir_borra_la_suscripcion(self):
        PushSubscription.objects.create(
            user=self.user, endpoint="https://push.example/abc", p256dh="p", auth="a",
        )
        response = self.client.post(
            reverse("accounts:push-unsubscribe"),
            data=json.dumps({"endpoint": "https://push.example/abc"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PushSubscription.objects.filter(endpoint="https://push.example/abc").exists())

    def test_no_se_puede_desuscribir_una_suscripcion_ajena(self):
        other = User.objects.create(email="otro_push@test.local", role=User.Role.LECTOR)
        PushSubscription.objects.create(user=other, endpoint="https://push.example/ajena", p256dh="p", auth="a")
        self.client.post(
            reverse("accounts:push-unsubscribe"),
            data=json.dumps({"endpoint": "https://push.example/ajena"}),
            content_type="application/json",
        )
        self.assertTrue(PushSubscription.objects.filter(endpoint="https://push.example/ajena").exists())


@override_settings(GOOGLE_OAUTH_CLIENT_ID="client-id", GOOGLE_OAUTH_CLIENT_SECRET="client-secret")
class GoogleCalendarConnectionTests(TestCase):
    """Conectar/desconectar Google Calendar solo sirve para sincronizar el
    calendario de Top Secret, así que exige el código igual que el resto de
    ese apartado — sin él, ni se puede empezar el flujo de OAuth."""

    def setUp(self):
        self.user = User.objects.create(email="google_cal@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

    def test_sin_el_codigo_de_top_secret_no_se_puede_conectar(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("accounts:google-calendar-connect"))
        self.assertRedirects(response, reverse("secret:gate"))

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="", GOOGLE_OAUTH_CLIENT_SECRET="")
    def test_connect_sin_credenciales_da_404(self):
        response = self.client.get(reverse("accounts:google-calendar-connect"))
        self.assertEqual(response.status_code, 404)

    def test_connect_redirige_a_google_y_guarda_el_state(self):
        response = self.client.get(reverse("accounts:google-calendar-connect"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("https://accounts.google.com/o/oauth2/v2/auth"))
        self.assertIn("google_oauth_state", self.client.session)

    def test_callback_sin_state_no_conecta(self):
        response = self.client.get(reverse("accounts:google-calendar-callback"), {"code": "abc", "state": "malo"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("secret:calendar"))
        self.assertFalse(GoogleCalendarConnection.objects.filter(user=self.user).exists())

    @patch("apps.accounts.views.exchange_code_for_tokens")
    def test_callback_crea_la_conexion(self, mock_exchange):
        session = self.client.session
        session["google_oauth_state"] = "buen-state"
        session.save()
        mock_exchange.return_value = {"access_token": "a", "refresh_token": "r", "expires_in": 3600}

        response = self.client.get(reverse("accounts:google-calendar-callback"), {"code": "abc", "state": "buen-state"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("secret:calendar"))
        connection = GoogleCalendarConnection.objects.get(user=self.user)
        self.assertEqual(connection.refresh_token, "r")

    @patch("apps.accounts.views.exchange_code_for_tokens")
    def test_callback_sin_refresh_token_no_conecta(self, mock_exchange):
        session = self.client.session
        session["google_oauth_state"] = "buen-state"
        session.save()
        mock_exchange.return_value = {"access_token": "a", "expires_in": 3600}

        self.client.get(reverse("accounts:google-calendar-callback"), {"code": "abc", "state": "buen-state"})
        self.assertFalse(GoogleCalendarConnection.objects.filter(user=self.user).exists())

    def test_desconectar_borra_la_conexion(self):
        GoogleCalendarConnection.objects.create(user=self.user, refresh_token="r")
        self.client.post(reverse("accounts:google-calendar-disconnect"))
        self.assertFalse(GoogleCalendarConnection.objects.filter(user=self.user).exists())

    def test_desconectar_limpia_el_id_de_google_de_tus_eventos(self):
        from apps.movies.models import Movie
        from apps.secret.models import ReleaseEvent

        GoogleCalendarConnection.objects.create(user=self.user, refresh_token="r")
        movie = Movie.objects.create(tmdb_id=1, title="X", media_type="movie")
        event = ReleaseEvent.objects.create(user=self.user, movie=movie, date="2026-03-15", google_event_id="g1")

        self.client.post(reverse("accounts:google-calendar-disconnect"))

        event.refresh_from_db()
        self.assertEqual(event.google_event_id, "")
