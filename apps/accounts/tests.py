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
        from apps.games.models import MovieQuote

        MovieQuote.objects.create(
            quote="Frase de prueba sin caracteres especiales",
            correct_title="Película X", wrong_title_1="Y", wrong_title_2="Z",
        )
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "rotating-quotes-data")
        self.assertContains(response, "Frase de prueba sin caracteres especiales")

    def test_el_perfil_tiene_boton_de_cerrar_sesion(self):
        response = self.client.get(reverse("accounts:profile"))
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


class ProfileEmailVerificationStatusTests(TestCase):
    """El perfil debe reflejar si el email está verificado y ofrecer
    reenviar el correo — antes esto no tenía ningún hueco visible en la web,
    así que no había forma de saber si el email de verificación se había
    perdido o de pedir que se reenviara."""

    def setUp(self):
        from apps.core.models import SiteConfig

        config = SiteConfig.load()
        config.require_email_verification = True
        config.save()

        self.user = User.objects.create(email="lector@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")

    def test_muestra_aviso_y_boton_de_reenviar_si_no_esta_verificado(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "no has verificado")
        self.assertContains(response, reverse("accounts:resend-verification"))

    def test_muestra_verificado_si_ya_lo_esta(self):
        self.user.email_verified = True
        self.user.save()
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "Email verificado")
        self.assertNotContains(response, "no has verificado")

    def test_reenviar_envia_un_email(self):
        self.client.post(reverse("accounts:resend-verification"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_sin_exigir_verificacion_no_se_muestra_nada(self):
        from apps.core.models import SiteConfig

        config = SiteConfig.load()
        config.require_email_verification = False
        config.save()

        response = self.client.get(reverse("accounts:profile"))
        self.assertNotContains(response, "no has verificado")
        self.assertNotContains(response, "Email verificado")


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

    def test_guardar_nota_de_por_que_la_recomiendas(self):
        movie = Movie.objects.create(tmdb_id=9, title="Recomendada", media_type="movie")
        favorite = FavoriteMovie.objects.create(user=self.user, category="suggested", movie=movie)

        response = self.client.post(
            reverse("accounts:favorite-note", args=[favorite.pk]), {"note": "Porque sí, es genial"}
        )
        self.assertRedirects(response, reverse("accounts:favorites-page", args=["suggested"]))
        favorite.refresh_from_db()
        self.assertEqual(favorite.note, "Porque sí, es genial")

    def test_no_se_puede_editar_la_nota_de_una_favorita_ajena(self):
        other = User.objects.create(email="otro_nota@test.local", role=User.Role.LECTOR)
        movie = Movie.objects.create(tmdb_id=10, title="Ajena", media_type="movie")
        favorite = FavoriteMovie.objects.create(user=other, category="suggested", movie=movie)

        response = self.client.post(reverse("accounts:favorite-note", args=[favorite.pk]), {"note": "Robada"})
        self.assertEqual(response.status_code, 404)
        favorite.refresh_from_db()
        self.assertEqual(favorite.note, "")

    def test_la_nota_se_recorta_a_280_caracteres(self):
        movie = Movie.objects.create(tmdb_id=11, title="Larga", media_type="movie")
        favorite = FavoriteMovie.objects.create(user=self.user, category="suggested", movie=movie)

        self.client.post(reverse("accounts:favorite-note", args=[favorite.pk]), {"note": "x" * 300})
        favorite.refresh_from_db()
        self.assertEqual(len(favorite.note), 280)

    def test_la_pagina_de_sugeridas_muestra_la_nota_de_una_recomendada(self):
        movie = Movie.objects.create(tmdb_id=12, title="Con nota", media_type="movie")
        FavoriteMovie.objects.create(user=self.user, category="suggested", movie=movie, note="Un peliculón")

        response = self.client.get(reverse("accounts:favorites-page", args=["suggested"]))
        self.assertContains(response, "Un peliculón")


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
    def setUp(self):
        self.user = User.objects.create(email="google_cal@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")

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
        from apps.movies.models import Movie, ReleaseEvent

        GoogleCalendarConnection.objects.create(user=self.user, refresh_token="r")
        movie = Movie.objects.create(tmdb_id=1, title="X", media_type="movie")
        event = ReleaseEvent.objects.create(user=self.user, movie=movie, date="2026-03-15", google_event_id="g1")

        self.client.post(reverse("accounts:google-calendar-disconnect"))

        event.refresh_from_db()
        self.assertEqual(event.google_event_id, "")
