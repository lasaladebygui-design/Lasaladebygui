import io
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.movies.models import Movie
from apps.movies.services import MovieAPIError

from .forms import SecretMovieForm
from .models import Genre, SecretMovie, SecretPhoto, TierLevel, TierListEntry, TopSecretConfig

try:
    from PIL import Image
except ImportError:
    Image = None


def _fake_image():
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2)).save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile("photo.png", buffer.read(), content_type="image/png")


class GateTests(TestCase):
    def test_codigo_por_defecto_es_8888(self):
        config = TopSecretConfig.load()
        self.assertTrue(config.check_code("8888"))
        self.assertFalse(config.check_code("0000"))

    def test_codigo_incorrecto_no_desbloquea(self):
        response = self.client.post(reverse("secret:gate"), {"code": "0000"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.session.get("top_secret_unlocked"))

    def test_codigo_correcto_desbloquea_y_redirige(self):
        response = self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.assertRedirects(response, reverse("secret:home"))
        self.assertTrue(self.client.session.get("top_secret_unlocked"))

    def test_paginas_internas_redirigen_a_la_puerta_sin_codigo(self):
        response = self.client.get(reverse("secret:home"))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_cerrar_maletin_bloquea_de_nuevo(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:home"))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_cambiar_codigo(self):
        config = TopSecretConfig.load()
        config.set_code("1234")
        config.save()
        self.assertFalse(config.check_code("8888"))
        self.assertTrue(config.check_code("1234"))


class SecretMovieViewTests(TestCase):
    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.a = SecretMovie.objects.create(number=1, title="Reservoir Dogs", personal_rating="9.0")
        self.b = SecretMovie.objects.create(number=2, title="Kill Bill", personal_rating="8.5")

    def test_selector_numerico_devuelve_la_pelicula_correcta(self):
        response = self.client.get(reverse("secret:by-number"), {"number": 1})
        self.assertEqual(response.context["result"], self.a)

    def test_buscador_por_nota_devuelve_una_del_intervalo(self):
        response = self.client.get(reverse("secret:by-rating"), {"min_rating": 8, "max_rating": 9})
        self.assertIn(response.context["result"], [self.a, self.b])

    def test_buscador_por_nota_sin_coincidencias(self):
        response = self.client.get(reverse("secret:by-rating"), {"min_rating": 1, "max_rating": 2})
        self.assertIsNone(response.context["result"])

    def test_lista_completa_incluye_todas(self):
        response = self.client.get(reverse("secret:list"))
        self.assertEqual(list(response.context["movies"]), [self.a, self.b])

    def test_buscador_por_nota_filtra_por_genero(self):
        terror = Genre.objects.create(name="Terror")
        self.a.genres.add(terror)

        response = self.client.get(reverse("secret:by-rating"), {
            "min_rating": 8, "max_rating": 9, "genre": terror.slug,
        })
        self.assertEqual(response.context["result"], self.a)

    def test_buscador_por_nota_genero_sin_coincidencias(self):
        terror = Genre.objects.create(name="Terror")
        self.a.genres.add(terror)
        comedia = Genre.objects.create(name="Comedia")

        response = self.client.get(reverse("secret:by-rating"), {
            "min_rating": 8, "max_rating": 9, "genre": comedia.slug,
        })
        self.assertIsNone(response.context["result"])


class SecretMovieFormTests(TestCase):
    def test_crea_generos_sobre_la_marcha(self):
        form = SecretMovieForm(data={
            "number": 1, "title": "Kill Bill", "personal_rating": "9.0",
            "comment": "", "genres_input": "acción, venganza, Tarantino",
        })
        self.assertTrue(form.is_valid(), form.errors)
        movie = form.save()
        self.assertEqual(
            set(movie.genres.values_list("name", flat=True)),
            {"acción", "venganza", "Tarantino"},
        )

    def test_reutiliza_generos_existentes(self):
        Genre.objects.create(name="Terror")
        form = SecretMovieForm(data={
            "number": 1, "title": "El resplandor", "personal_rating": "9.5",
            "comment": "", "genres_input": "Terror, Drama",
        })
        self.assertTrue(form.is_valid(), form.errors)
        movie = form.save()
        self.assertEqual(Genre.objects.count(), 2)
        self.assertEqual(movie.genres.count(), 2)

    def test_editar_precarga_los_generos_actuales(self):
        movie = SecretMovie.objects.create(number=1, title="X", personal_rating="8.0")
        movie.genres.add(Genre.objects.create(name="Drama"))
        form = SecretMovieForm(instance=movie)
        self.assertEqual(form.fields["genres_input"].initial, "Drama")


class TierListTests(TestCase):
    """Los niveles S/A/B/C/D que trae `seed_quotes`/las migraciones por
    defecto no son relevantes aquí: cada test parte de su propio conjunto
    de niveles para no depender de ese valor de fábrica."""

    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        TierLevel.objects.all().delete()
        self.s = TierLevel.objects.create(name="S", color="#FFD700", order=0)
        self.d = TierLevel.objects.create(name="D", color="#D98C8C", order=1)

    def test_agrupa_por_nivel(self):
        TierListEntry.objects.create(tier=self.s, title="Pulp Fiction", order=1)
        TierListEntry.objects.create(tier=self.s, title="Kill Bill", order=2)
        TierListEntry.objects.create(tier=self.d, title="Una película mala", order=1)

        response = self.client.get(reverse("secret:tier-list"))
        level_rows = dict(response.context["level_rows"])
        self.assertEqual([e.title for e in level_rows[self.s]], ["Pulp Fiction", "Kill Bill"])
        self.assertEqual([e.title for e in level_rows[self.d]], ["Una película mala"])

    def test_requiere_haber_entrado_al_maletin(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:tier-list"))
        self.assertRedirects(response, reverse("secret:gate"))

    @patch("apps.secret.views.tmdb_search")
    def test_buscar_usa_el_servicio_tmdb(self, mock_search):
        mock_search.return_value = []
        response = self.client.get(reverse("secret:tier-list-search"), {"query": "matrix"})
        self.assertEqual(response.status_code, 200)
        mock_search.assert_called_once_with("matrix")

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_anadir_desde_busqueda_cae_en_sin_clasificar(self, mock_get_or_create):
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=99, title="Nueva película")
        response = self.client.post(reverse("secret:tier-list-add", args=[99]))
        self.assertRedirects(response, reverse("secret:tier-list"))
        entry = TierListEntry.objects.get(movie__tmdb_id=99)
        self.assertIsNone(entry.tier)
        self.assertEqual(entry.title, "Nueva película")

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb", side_effect=MovieAPIError("fallo"))
    def test_error_de_tmdb_al_anadir_no_rompe_la_pagina(self, mock_get_or_create):
        response = self.client.post(reverse("secret:tier-list-add", args=[99]))
        self.assertRedirects(response, reverse("secret:tier-list"))
        self.assertFalse(TierListEntry.objects.exists())

    def test_mover_cambia_de_nivel_y_se_coloca_al_final(self):
        TierListEntry.objects.create(tier=self.d, title="Ya en D", order=1)
        entry = TierListEntry.objects.create(tier=self.s, title="Se mueve", order=1)

        response = self.client.post(reverse("secret:tier-list-move", args=[entry.pk]), {"tier": self.d.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

        entry.refresh_from_db()
        self.assertEqual(entry.tier, self.d)
        self.assertEqual(entry.order, 2)

    def test_mover_a_sin_clasificar(self):
        entry = TierListEntry.objects.create(tier=self.s, title="X", order=1)
        response = self.client.post(reverse("secret:tier-list-move", args=[entry.pk]), {"tier": ""})
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertIsNone(entry.tier)

    def test_mover_con_nivel_invalido_da_error(self):
        entry = TierListEntry.objects.create(tier=self.s, title="X", order=1)
        response = self.client.post(reverse("secret:tier-list-move", args=[entry.pk]), {"tier": "9999"})
        self.assertEqual(response.status_code, 400)
        entry.refresh_from_db()
        self.assertEqual(entry.tier, self.s)

    def test_mover_requiere_haber_entrado_al_maletin(self):
        entry = TierListEntry.objects.create(tier=self.s, title="X", order=1)
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:tier-list-move", args=[entry.pk]))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_reiniciar_vacia_toda_la_tier_list(self):
        TierListEntry.objects.create(tier=self.s, title="Uno", order=1)
        TierListEntry.objects.create(tier=None, title="Dos", order=1)
        response = self.client.post(reverse("secret:tier-list-reset"))
        self.assertRedirects(response, reverse("secret:tier-list"))
        self.assertFalse(TierListEntry.objects.exists())

    def test_reiniciar_requiere_haber_entrado_al_maletin(self):
        TierListEntry.objects.create(tier=self.s, title="Uno", order=1)
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:tier-list-reset"))
        self.assertRedirects(response, reverse("secret:gate"))
        self.assertTrue(TierListEntry.objects.exists())


class TierLevelManagementTests(TestCase):
    """Nombre, color y alta/baja de niveles se gestionan enteros desde la
    propia página del Tier List, sin pasar por el admin."""

    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        TierLevel.objects.all().delete()

    def test_anadir_nivel(self):
        response = self.client.post(reverse("secret:tier-level-create"), {"name": "Favoritas", "color": "#ABCDEF"})
        self.assertRedirects(response, reverse("secret:tier-list"))
        level = TierLevel.objects.get(name="Favoritas")
        self.assertEqual(level.color, "#ABCDEF")

    def test_nuevo_nivel_se_coloca_al_final(self):
        TierLevel.objects.create(name="S", color="#FFD700", order=0)
        self.client.post(reverse("secret:tier-level-create"), {"name": "Extra", "color": "#000000"})
        nuevo = TierLevel.objects.get(name="Extra")
        self.assertEqual(nuevo.order, 1)

    def test_editar_nivel_cambia_nombre_y_color(self):
        level = TierLevel.objects.create(name="S", color="#FFD700", order=0)
        response = self.client.post(
            reverse("secret:tier-level-update", args=[level.pk]), {"name": "Sobresaliente", "color": "#123456"},
        )
        self.assertRedirects(response, reverse("secret:tier-list"))
        level.refresh_from_db()
        self.assertEqual(level.name, "Sobresaliente")
        self.assertEqual(level.color, "#123456")

    def test_borrar_nivel_manda_sus_peliculas_a_sin_clasificar(self):
        level = TierLevel.objects.create(name="S", color="#FFD700", order=0)
        entry = TierListEntry.objects.create(tier=level, title="Se queda sin nivel", order=1)

        response = self.client.post(reverse("secret:tier-level-delete", args=[level.pk]))
        self.assertRedirects(response, reverse("secret:tier-list"))
        self.assertFalse(TierLevel.objects.filter(pk=level.pk).exists())

        entry.refresh_from_db()
        self.assertIsNone(entry.tier)

    def test_gestion_de_niveles_requiere_haber_entrado_al_maletin(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.post(reverse("secret:tier-level-create"), {"name": "X", "color": "#000000"})
        self.assertRedirects(response, reverse("secret:gate"))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PhotoBoardTests(TestCase):
    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})

    def test_requiere_haber_entrado_al_maletin(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:photo-board"))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_subir_foto_sin_cuenta(self):
        response = self.client.post(reverse("secret:photo-board"), {
            "image": _fake_image(), "description": "Una foto anónima",
        })
        self.assertRedirects(response, reverse("secret:photo-board"))
        photo = SecretPhoto.objects.get()
        self.assertEqual(photo.description, "Una foto anónima")
        self.assertIsNone(photo.uploaded_by)

    def test_subir_foto_logueado_guarda_quien_la_subio(self):
        user = User.objects.create(email="lector@test.local", role=User.Role.LECTOR)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

        self.client.post(reverse("secret:photo-board"), {
            "image": _fake_image(), "description": "Foto con autor",
        })
        photo = SecretPhoto.objects.get()
        self.assertEqual(photo.uploaded_by, user)

    def test_listado_muestra_las_fotos_subidas(self):
        SecretPhoto.objects.create(image=_fake_image(), description="Foto de prueba")
        response = self.client.get(reverse("secret:photo-board"))
        self.assertContains(response, "Foto de prueba")

    def test_sin_imagen_no_crea_la_foto(self):
        response = self.client.post(reverse("secret:photo-board"), {"description": "Sin imagen"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SecretPhoto.objects.exists())

