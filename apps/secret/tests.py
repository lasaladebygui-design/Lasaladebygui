import io
import tempfile
from datetime import date
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import GoogleCalendarConnection, PushSubscription, User
from apps.movies.models import CalendarDayNote, Movie, ReleaseEvent, ReleaseEventGoogleLink
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
        self.a = SecretMovie.objects.create(title="Reservoir Dogs", personal_rating="9.0")
        self.b = SecretMovie.objects.create(title="Kill Bill", personal_rating="8.5")

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

    def test_lista_completa_filtra_por_genero(self):
        terror = Genre.objects.create(name="Terror")
        self.a.genres.add(terror)

        response = self.client.get(reverse("secret:list"), {"genre": terror.slug})
        self.assertEqual(list(response.context["movies"]), [self.a])

    def test_lista_completa_filtra_por_nota(self):
        response = self.client.get(reverse("secret:list"), {"rating": "8.5"})
        self.assertEqual(list(response.context["movies"]), [self.b])

    def test_lista_completa_combina_genero_y_nota(self):
        terror = Genre.objects.create(name="Terror")
        self.a.genres.add(terror)
        self.b.genres.add(terror)

        response = self.client.get(reverse("secret:list"), {"genre": terror.slug, "rating": "9.0"})
        self.assertEqual(list(response.context["movies"]), [self.a])

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


class SecretMovieAutoNumberingTests(TestCase):
    """El número ya no se elige a mano: es la posición al ordenar por nota
    (de mayor a menor), recalculada sola en cada guardado/borrado."""

    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})

    def test_la_mejor_nota_es_el_numero_uno(self):
        peor = SecretMovie.objects.create(title="Peor", personal_rating="6.0")
        mejor = SecretMovie.objects.create(title="Mejor", personal_rating="9.0")
        self.assertEqual(mejor.number, 1)
        peor.refresh_from_db()
        self.assertEqual(peor.number, 2)

    def test_anadir_una_mejor_desplaza_a_las_demas(self):
        SecretMovie.objects.create(title="A", personal_rating="9.0")
        b = SecretMovie.objects.create(title="B", personal_rating="8.0")
        nueva = SecretMovie.objects.create(title="Nueva", personal_rating="9.5")
        self.assertEqual(nueva.number, 1)
        b.refresh_from_db()
        self.assertEqual(b.number, 3)

    def test_cambiar_la_nota_reordena(self):
        a = SecretMovie.objects.create(title="A", personal_rating="9.0")
        b = SecretMovie.objects.create(title="B", personal_rating="8.0")
        self.assertEqual(a.number, 1)
        self.assertEqual(b.number, 2)

        b.personal_rating = "9.5"
        b.save()
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(b.number, 1)
        self.assertEqual(a.number, 2)

    def test_borrar_una_recoloca_a_las_siguientes(self):
        a = SecretMovie.objects.create(title="A", personal_rating="9.0")
        b = SecretMovie.objects.create(title="B", personal_rating="8.0")
        a.delete()
        b.refresh_from_db()
        self.assertEqual(b.number, 1)

    def test_misma_nota_desempata_por_tie_break(self):
        a = SecretMovie.objects.create(title="A", personal_rating="9.0", tie_break=1)
        b = SecretMovie.objects.create(title="B", personal_rating="9.0", tie_break=0)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(b.number, 1)
        self.assertEqual(a.number, 2)

    def test_cambiar_el_tie_break_reordena_el_empate(self):
        a = SecretMovie.objects.create(title="A", personal_rating="9.0", tie_break=0)
        b = SecretMovie.objects.create(title="B", personal_rating="9.0", tie_break=1)
        a.refresh_from_db()
        self.assertEqual(a.number, 1)

        a.tie_break = 5
        a.save()
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(b.number, 1)
        self.assertEqual(a.number, 2)

    def test_la_lista_completa_sale_ordenada_por_nota_sin_filtrar(self):
        SecretMovie.objects.create(title="Floja", personal_rating="5.0")
        SecretMovie.objects.create(title="Buenisima", personal_rating="9.5")
        SecretMovie.objects.create(title="Normal", personal_rating="7.0")

        response = self.client.get(reverse("secret:list"))
        titles = [m.title for m in response.context["movies"]]
        self.assertEqual(titles, ["Buenisima", "Normal", "Floja"])

    def test_selector_numerico_refleja_la_posicion_por_nota(self):
        SecretMovie.objects.create(title="Floja", personal_rating="5.0")
        buenisima = SecretMovie.objects.create(title="Buenisima", personal_rating="9.5")

        response = self.client.get(reverse("secret:by-number"), {"number": 1})
        self.assertEqual(response.context["result"], buenisima)

    def test_no_editable_desde_el_formulario(self):
        from apps.secret.forms import SecretMovieForm
        self.assertNotIn("number", SecretMovieForm.base_fields)


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
        movie = SecretMovie.objects.create(title="X", personal_rating="8.0")
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


class CalendarTests(TestCase):
    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.movie = Movie.objects.create(tmdb_id=1, title="Estreno de prueba", media_type="movie")

    def test_requiere_haber_entrado_al_maletin(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:calendar"))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_el_input_de_buscar_manda_el_valor_como_query(self):
        # Regresión: sin name="query" en el <input>, HTMX nunca manda lo
        # escrito y el desplegable de resultados no aparece nunca, aunque
        # la búsqueda "funcione" (con query siempre vacía).
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        self.assertContains(response, 'name="query"')

    def test_muestra_eventos_del_mes_pedido(self):
        event = ReleaseEvent.objects.create(movie=self.movie, date=date(2026, 3, 15), note="Estreno")
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        self.assertEqual(response.status_code, 200)
        all_events = [e for week in response.context["weeks"] for day in week for e in day["events"]]
        self.assertEqual(all_events, [event])

    def test_muestra_la_portada_y_el_titulo_del_evento(self):
        movie = Movie.objects.create(tmdb_id=99, title="Con portada", media_type="movie", poster_path="/abc.jpg")
        ReleaseEvent.objects.create(movie=movie, date=date(2026, 3, 15))
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        self.assertContains(response, "Con portada")
        self.assertContains(response, movie.poster_url)

    def test_no_muestra_eventos_de_otro_mes(self):
        ReleaseEvent.objects.create(movie=self.movie, date=date(2026, 4, 1))
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        all_events = [e for week in response.context["weeks"] for day in week for e in day["events"]]
        self.assertEqual(all_events, [])

    def test_mes_o_year_invalido_da_404(self):
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 13})
        self.assertEqual(response.status_code, 404)

    def test_descarga_ics(self):
        event = ReleaseEvent.objects.create(movie=self.movie, date=date(2026, 3, 15), note="Estreno")
        response = self.client.get(reverse("secret:calendar-ics", args=[event.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        content = response.content.decode("utf-8")
        self.assertIn("BEGIN:VEVENT", content)
        self.assertIn("DTSTART;VALUE=DATE:20260315", content)
        self.assertIn("SUMMARY:Estreno de prueba", content)

    def test_ics_escapa_comas_en_el_titulo(self):
        movie = Movie.objects.create(tmdb_id=2, title="Uno, Dos y Tres", media_type="movie")
        event = ReleaseEvent.objects.create(movie=movie, date=date(2026, 3, 15))
        response = self.client.get(reverse("secret:calendar-ics", args=[event.pk]))
        self.assertIn("SUMMARY:Uno\\, Dos y Tres", response.content.decode("utf-8"))

    @patch("apps.secret.views.tmdb_search")
    def test_buscar_combina_peliculas_y_series(self, mock_search):
        mock_search.side_effect = lambda query, media_type="movie": []
        response = self.client.get(reverse("secret:calendar-search"), {"query": "matrix", "date": "2026-03-15"})
        self.assertEqual(response.status_code, 200)
        mock_search.assert_any_call("matrix", media_type="movie")
        mock_search.assert_any_call("matrix", media_type="tv")

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_anadir_crea_un_evento_en_la_fecha_elegida(self, mock_get_or_create):
        mock_get_or_create.return_value = self.movie
        response = self.client.post(
            reverse("secret:calendar-add", args=["movie", 1]), {"date": "2026-03-15"},
        )
        self.assertRedirects(response, reverse("secret:calendar") + "?year=2026&month=3")
        event = ReleaseEvent.objects.get()
        self.assertEqual(event.movie, self.movie)
        self.assertEqual(event.date, date(2026, 3, 15))
        mock_get_or_create.assert_called_once_with(1, media_type="movie")

    def test_anadir_con_fecha_invalida_no_crea_nada(self):
        response = self.client.post(reverse("secret:calendar-add", args=["movie", 1]), {"date": "no-es-una-fecha"})
        self.assertRedirects(response, reverse("secret:calendar"))
        self.assertFalse(ReleaseEvent.objects.exists())

    def test_quitar_borra_el_evento(self):
        event = ReleaseEvent.objects.create(movie=self.movie, date=date(2026, 3, 15))
        response = self.client.post(reverse("secret:calendar-remove", args=[event.pk]))
        self.assertRedirects(response, reverse("secret:calendar") + "?year=2026&month=3")
        self.assertFalse(ReleaseEvent.objects.filter(pk=event.pk).exists())

    @override_settings(VAPID_PUBLIC_KEY="clave-publica", VAPID_PRIVATE_KEY="clave-privada")
    @patch("apps.secret.views.send_push_to_users")
    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_anadir_evento_notifica_a_los_suscritos(self, mock_get_or_create, mock_send):
        mock_get_or_create.return_value = self.movie
        subscriber = User.objects.create(email="suscrito_calendario@test.local", role=User.Role.LECTOR)
        PushSubscription.objects.create(user=subscriber, endpoint="https://push.example/cal", p256dh="p", auth="a")

        self.client.post(reverse("secret:calendar-add", args=["movie", 1]), {"date": "2026-03-15"})

        mock_send.assert_called_once()
        subscribers = list(mock_send.call_args.args[0])
        self.assertIn(subscriber, subscribers)

    def test_guardar_comentario_de_un_dia(self):
        response = self.client.post(reverse("secret:calendar-day-note"), {"date": "2026-03-15", "note": "Vacaciones"})
        self.assertRedirects(response, reverse("secret:calendar") + "?year=2026&month=3")
        note = CalendarDayNote.objects.get(date=date(2026, 3, 15))
        self.assertEqual(note.note, "Vacaciones")

    def test_el_calendario_muestra_el_comentario_del_dia(self):
        CalendarDayNote.objects.create(date=date(2026, 3, 15), note="Vacaciones")
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        self.assertContains(response, "Vacaciones")

    def test_editar_un_comentario_existente_lo_sobreescribe(self):
        CalendarDayNote.objects.create(date=date(2026, 3, 15), note="Antiguo")
        self.client.post(reverse("secret:calendar-day-note"), {"date": "2026-03-15", "note": "Nuevo"})
        self.assertEqual(CalendarDayNote.objects.count(), 1)
        self.assertEqual(CalendarDayNote.objects.get().note, "Nuevo")

    def test_guardar_nota_vacia_borra_el_comentario(self):
        CalendarDayNote.objects.create(date=date(2026, 3, 15), note="Algo")
        self.client.post(reverse("secret:calendar-day-note"), {"date": "2026-03-15", "note": ""})
        self.assertFalse(CalendarDayNote.objects.filter(date=date(2026, 3, 15)).exists())

    def test_comentario_con_fecha_invalida_da_404(self):
        response = self.client.post(reverse("secret:calendar-day-note"), {"date": "no-es-fecha", "note": "X"})
        self.assertEqual(response.status_code, 404)

    def test_requiere_haber_entrado_al_maletin_para_comentar(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.post(reverse("secret:calendar-day-note"), {"date": "2026-03-15", "note": "X"})
        self.assertRedirects(response, reverse("secret:gate"))
        self.assertFalse(CalendarDayNote.objects.filter(date=date(2026, 3, 15)).exists())


@override_settings(GOOGLE_OAUTH_CLIENT_ID="client-id", GOOGLE_OAUTH_CLIENT_SECRET="client-secret")
class CalendarGoogleSyncTests(TestCase):
    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.movie = Movie.objects.create(tmdb_id=1, title="Estreno de prueba", media_type="movie")

    @patch("apps.secret.views.google_create_event")
    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_anadir_evento_lo_crea_en_cada_calendario_conectado(self, mock_get_or_create, mock_create_event):
        mock_get_or_create.return_value = self.movie
        mock_create_event.return_value = "google-event-id-1"
        connected_user = User.objects.create(email="conectado@test.local", role=User.Role.LECTOR)
        GoogleCalendarConnection.objects.create(user=connected_user, refresh_token="r")

        self.client.post(reverse("secret:calendar-add", args=["movie", 1]), {"date": "2026-03-15"})

        mock_create_event.assert_called_once()
        event = ReleaseEvent.objects.get()
        link = ReleaseEventGoogleLink.objects.get(release_event=event, user=connected_user)
        self.assertEqual(link.google_event_id, "google-event-id-1")

    @patch("apps.secret.views.google_create_event")
    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_sin_nadie_conectado_no_llama_a_google(self, mock_get_or_create, mock_create_event):
        mock_get_or_create.return_value = self.movie
        self.client.post(reverse("secret:calendar-add", args=["movie", 1]), {"date": "2026-03-15"})
        mock_create_event.assert_not_called()

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="", GOOGLE_OAUTH_CLIENT_SECRET="")
    @patch("apps.secret.views.google_create_event")
    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_sin_credenciales_de_google_no_llama_a_la_api(self, mock_get_or_create, mock_create_event):
        mock_get_or_create.return_value = self.movie
        connected_user = User.objects.create(email="conectado2@test.local", role=User.Role.LECTOR)
        GoogleCalendarConnection.objects.create(user=connected_user, refresh_token="r")

        self.client.post(reverse("secret:calendar-add", args=["movie", 1]), {"date": "2026-03-15"})

        mock_create_event.assert_not_called()

    @patch("apps.secret.views.google_delete_event")
    def test_quitar_evento_lo_borra_de_cada_calendario_conectado(self, mock_delete_event):
        connected_user = User.objects.create(email="conectado3@test.local", role=User.Role.LECTOR)
        GoogleCalendarConnection.objects.create(user=connected_user, refresh_token="r")
        event = ReleaseEvent.objects.create(movie=self.movie, date=date(2026, 3, 15))
        ReleaseEventGoogleLink.objects.create(release_event=event, user=connected_user, google_event_id="g1")

        self.client.post(reverse("secret:calendar-remove", args=[event.pk]))

        mock_delete_event.assert_called_once()
        self.assertEqual(mock_delete_event.call_args.args[1], "g1")

    @patch("apps.secret.views.google_delete_event")
    def test_quitar_evento_ignora_enlaces_de_usuarios_ya_desconectados(self, mock_delete_event):
        disconnected_user = User.objects.create(email="desconectado@test.local", role=User.Role.LECTOR)
        event = ReleaseEvent.objects.create(movie=self.movie, date=date(2026, 3, 15))
        ReleaseEventGoogleLink.objects.create(release_event=event, user=disconnected_user, google_event_id="g1")

        response = self.client.post(reverse("secret:calendar-remove", args=[event.pk]))

        self.assertEqual(response.status_code, 302)
        mock_delete_event.assert_not_called()

