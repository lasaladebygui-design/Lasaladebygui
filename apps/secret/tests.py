import io
import tempfile
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import GoogleCalendarConnection, User
from apps.movies.models import Movie, SavedMovie
from apps.movies.services import MovieAPIError
from apps.social.models import FriendRequest, ensure_friends, get_contact_bot_user

from .forms import SecretMovieForm
from .models import (
    CalendarDayNote,
    CalendarShareMember,
    Genre,
    PhotoBoardMember,
    RatingColorBand,
    ReleaseEvent,
    SecretListMember,
    SecretMovie,
    SecretPhoto,
    TierLevel,
    TierListEntry,
    TopSecretConfig,
    TopSecretTab,
)

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
    def setUp(self):
        # El contador de intentos fallidos vive en el caché de proceso, no
        # en la base de datos de pruebas — sin esto, tests de otras clases
        # que fallen el código a propósito dejarían "cargado" el contador
        # para los siguientes tests que se ejecuten en el mismo proceso.
        cache.clear()

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

    def test_bloquea_tras_muchos_intentos_fallidos(self):
        for _ in range(8):
            self.client.post(reverse("secret:gate"), {"code": "0000"})

        response = self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.session.get("top_secret_unlocked"))
        self.assertContains(response, "Demasiados intentos")

    def test_acertar_el_codigo_resetea_el_contador_de_intentos(self):
        for _ in range(5):
            self.client.post(reverse("secret:gate"), {"code": "0000"})
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.client.post(reverse("secret:lock"))

        response = self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.assertRedirects(response, reverse("secret:home"))

    def test_la_escena_del_maletin_empieza_cerrada(self):
        response = self.client.get(reverse("secret:gate"))
        self.assertContains(response, "open: false")

    def test_tras_un_codigo_incorrecto_la_escena_se_abre_ya(self):
        # Si el formulario vuelve con error, el panel del código debe
        # aparecer ya abierto en vez de obligar a tocar el maletín otra
        # vez para ver por qué falló.
        response = self.client.post(reverse("secret:gate"), {"code": "0000"})
        self.assertContains(response, "open: true")
        self.assertContains(response, "briefcase--shake")


class RatingColorBandTests(TestCase):
    """Los tramos de color son de número arbitrario y los decide quien
    administra (no un fijo "bueno/medio/malo") — ver rating_color en
    apps/secret/models.py."""

    def setUp(self):
        self.config = TopSecretConfig.load()
        RatingColorBand.objects.filter(config=self.config).delete()

    def test_nota_dentro_de_un_tramo_usa_su_color(self):
        RatingColorBand.objects.create(config=self.config, min_rating="1.0", max_rating="4.0", color="#FF0000", order=0)
        self.assertEqual(self.config.rating_color(2.5), "#FF0000")

    def test_nota_fuera_de_todo_tramo_usa_el_gris_por_defecto(self):
        RatingColorBand.objects.create(config=self.config, min_rating="1.0", max_rating="4.0", color="#FF0000", order=0)
        self.assertEqual(self.config.rating_color(9.0), "#9CA3AF")

    def test_tramos_solapados_gana_el_de_menor_order(self):
        RatingColorBand.objects.create(config=self.config, min_rating="5.0", max_rating="8.0", color="#00FF00", order=1)
        RatingColorBand.objects.create(config=self.config, min_rating="6.0", max_rating="10.0", color="#0000FF", order=0)
        self.assertEqual(self.config.rating_color(7.0), "#0000FF")

    def test_se_pueden_definir_tantos_tramos_como_se_quiera(self):
        RatingColorBand.objects.create(config=self.config, min_rating="0.0", max_rating="2.5", color="#111111", order=0)
        RatingColorBand.objects.create(config=self.config, min_rating="2.6", max_rating="5.0", color="#222222", order=1)
        RatingColorBand.objects.create(config=self.config, min_rating="5.1", max_rating="7.5", color="#333333", order=2)
        RatingColorBand.objects.create(config=self.config, min_rating="7.6", max_rating="10.0", color="#444444", order=3)
        self.assertEqual(self.config.rating_color(1.0), "#111111")
        self.assertEqual(self.config.rating_color(4.0), "#222222")
        self.assertEqual(self.config.rating_color(6.0), "#333333")
        self.assertEqual(self.config.rating_color(9.9), "#444444")


class SecretMovieViewTests(TestCase):
    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.a = SecretMovie.objects.create(title="Reservoir Dogs", personal_rating="9.0")
        self.b = SecretMovie.objects.create(title="Kill Bill", personal_rating="8.5")

    def test_selector_numerico_devuelve_la_pelicula_correcta(self):
        response = self.client.get(reverse("secret:by-number"), {"number": 1})
        self.assertEqual(response.context["result"], self.a)

    def test_selector_numerico_con_numero_inexistente_no_da_404(self):
        # Ahora es un campo de texto libre (antes un desplegable limitado a
        # números existentes), así que cualquier entero es válido para el
        # formulario aunque no exista ninguna película con ese número.
        response = self.client.get(reverse("secret:by-number"), {"number": 999})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["result"])
        self.assertContains(response, "No hay ninguna película con ese número.")

    def test_buscador_por_nota_devuelve_una_del_intervalo(self):
        response = self.client.get(reverse("secret:by-rating"), {"min_rating": 8, "max_rating": 9})
        self.assertIn(response.context["result"], [self.a, self.b])

    def test_buscador_por_nota_sin_coincidencias(self):
        response = self.client.get(reverse("secret:by-rating"), {"min_rating": 1, "max_rating": 2})
        self.assertIsNone(response.context["result"])

    def test_lista_completa_incluye_todas(self):
        response = self.client.get(reverse("secret:list"))
        self.assertEqual(list(response.context["movies"]), [self.a, self.b])

    def test_lista_completa_enseña_el_icono_de_guia_si_hay_texto(self):
        config = TopSecretConfig.load()
        config.rating_guide = "A partir del 8 me lo pienso dos veces."
        config.save()
        response = self.client.get(reverse("secret:list"))
        self.assertContains(response, "rating-guide__toggle")
        self.assertContains(response, "A partir del 8 me lo pienso dos veces.")

    def test_lista_completa_no_enseña_el_icono_sin_guia(self):
        config = TopSecretConfig.load()
        config.rating_guide = ""
        config.save()
        response = self.client.get(reverse("secret:list"))
        self.assertNotContains(response, "rating-guide__toggle")

    def test_lista_completa_busca_por_titulo(self):
        response = self.client.get(reverse("secret:list"), {"q": "kill"})
        self.assertEqual(list(response.context["movies"]), [self.b])

    def test_lista_completa_filtra_por_tipo_pelicula_o_serie(self):
        # Se saca de la película/serie del catálogo enlazada como portada,
        # no de una etiqueta a mano — self.a y self.b no tienen ninguna
        # enlazada, así que no salen en ninguno de los dos filtros.
        peli = Movie.objects.create(tmdb_id=1, title="Kill Bill", media_type="movie")
        serie = Movie.objects.create(tmdb_id=2, title="Dark", media_type="tv")
        self.b.movie = peli
        self.b.save()
        c = SecretMovie.objects.create(title="Dark", personal_rating="7.0", movie=serie)

        response = self.client.get(reverse("secret:list"), {"type": "movie"})
        self.assertEqual(list(response.context["movies"]), [self.b])

        response = self.client.get(reverse("secret:list"), {"type": "tv"})
        self.assertEqual(list(response.context["movies"]), [c])

    def test_ordenar_peliculas_primero_enseña_separador_entre_grupos(self):
        peli = Movie.objects.create(tmdb_id=4, title="Reservoir Dogs", media_type="movie")
        serie = Movie.objects.create(tmdb_id=5, title="Dark", media_type="tv")
        self.a.movie = peli
        self.a.save()
        c = SecretMovie.objects.create(title="Dark", personal_rating="7.0", movie=serie)

        response = self.client.get(reverse("secret:list"), {"sort": "movies_first"})
        movies = list(response.context["movies"])
        # self.a (película, con portada) primero, luego c (serie), luego
        # self.b (sin portada enlazada, va al final sin clasificar).
        self.assertEqual(movies, [self.a, c, self.b])
        by_pk = {m.pk: m for m in movies}
        self.assertEqual(getattr(by_pk[self.a.pk], "group_label", None), "🎬 Películas")
        self.assertEqual(getattr(by_pk[c.pk], "group_label", None), "📺 Series")
        self.assertEqual(getattr(by_pk[self.b.pk], "group_label", None), "❔ Sin clasificar")

    def test_orden_normal_no_tiene_separadores(self):
        response = self.client.get(reverse("secret:list"))
        movies = list(response.context["movies"])
        self.assertFalse(any(getattr(m, "group_label", None) for m in movies))

    def test_separador_no_se_repite_al_continuar_scroll_infinito_en_el_mismo_grupo(self):
        # Cada tanda del scroll infinito es una petición HTTP aparte (sin
        # memoria de la anterior) — "prev_type" es lo que le dice a la
        # siguiente tanda si sigue en el mismo grupo que la última fila de
        # la tanda anterior, para no repetir el separador de "Películas".
        peli = Movie.objects.create(tmdb_id=6, title="Reservoir Dogs", media_type="movie")
        otra_peli = Movie.objects.create(tmdb_id=7, title="Kill Bill", media_type="movie")
        self.a.movie = peli
        self.a.save()
        self.b.movie = otra_peli
        self.b.save()

        # "página 1" (solo self.a): el último tipo visto es 0 (película).
        # "página 2" pide prev_type=0, simulando que sigue en el mismo grupo.
        response = self.client.get(
            reverse("secret:list"), {"sort": "movies_first", "prev_type": "0"}, HTTP_HX_REQUEST="true",
        )
        movies = list(response.context["movies"])
        by_pk = {m.pk: m for m in movies}
        self.assertIsNone(getattr(by_pk[self.a.pk], "group_label", None))
        self.assertIsNone(getattr(by_pk[self.b.pk], "group_label", None))

    def test_cuadradito_de_visto_solo_sale_en_series(self):
        peli = Movie.objects.create(tmdb_id=8, title="Reservoir Dogs", media_type="movie")
        serie = Movie.objects.create(tmdb_id=9, title="Dark", media_type="tv")
        self.a.movie = peli
        self.a.save()
        SecretMovie.objects.create(title="Dark", personal_rating="7.0", movie=serie)

        response = self.client.get(reverse("secret:list"))
        self.assertContains(response, "secret-movie__watch-badge")
        self.assertContains(response, "secret-movie__watch-badge--not_watched")

    def test_cuadradito_de_visto_no_sale_en_peliculas_ni_sin_portada(self):
        peli = Movie.objects.create(tmdb_id=10, title="Reservoir Dogs", media_type="movie")
        self.a.movie = peli
        self.a.save()

        response = self.client.get(reverse("secret:list"))
        self.assertNotContains(response, "secret-movie__watch-badge")

    def test_click_en_el_cuadradito_va_pasando_de_estado(self):
        serie = Movie.objects.create(tmdb_id=11, title="Dark", media_type="tv")
        user = User.objects.create(email="visto_test@test.local", role=User.Role.LECTOR, username="visto_test")
        user.set_password("Testpass123!")
        user.save()
        # Propia (owner=user): siempre editable por su dueño, sin
        # depender de ningún interruptor -- distinto de la de Bygui.
        c = SecretMovie.objects.create(owner=user, title="Dark", personal_rating="7.0", movie=serie)
        self.client.login(username=user.email, password="Testpass123!")

        response = self.client.post(reverse("secret:movie-watch-cycle", args=[c.pk]))
        self.assertContains(response, "secret-movie__watch-badge--airing")
        c.refresh_from_db()
        self.assertEqual(c.series_watch_status, SecretMovie.SeriesWatchStatus.AIRING)

        response = self.client.post(reverse("secret:movie-watch-cycle", args=[c.pk]))
        self.assertContains(response, "secret-movie__watch-badge--watched")

        response = self.client.post(reverse("secret:movie-watch-cycle", args=[c.pk]))
        self.assertContains(response, "secret-movie__watch-badge--not_watched")

    def test_no_se_puede_cambiar_el_estado_sin_login(self):
        serie = Movie.objects.create(tmdb_id=12, title="Dark", media_type="tv")
        c = SecretMovie.objects.create(title="Dark", personal_rating="7.0", movie=serie)
        response = self.client.post(reverse("secret:movie-watch-cycle", args=[c.pk]))
        self.assertIn("/cuenta/login/", response.url)
        c.refresh_from_db()
        self.assertEqual(c.series_watch_status, SecretMovie.SeriesWatchStatus.NOT_WATCHED)

    def test_el_cuadradito_no_cambia_nada_si_la_portada_es_una_pelicula(self):
        peli = Movie.objects.create(tmdb_id=13, title="Reservoir Dogs", media_type="movie")
        user = User.objects.create(email="visto_test2@test.local", role=User.Role.LECTOR, username="visto_test2")
        user.set_password("Testpass123!")
        user.save()
        propia = SecretMovie.objects.create(owner=user, title="Reservoir Dogs", personal_rating="9.0", movie=peli)
        self.client.login(username=user.email, password="Testpass123!")

        response = self.client.post(reverse("secret:movie-watch-cycle", args=[propia.pk]))
        self.assertEqual(response.status_code, 200)
        propia.refresh_from_db()
        self.assertEqual(propia.series_watch_status, SecretMovie.SeriesWatchStatus.NOT_WATCHED)

    def test_no_puedes_cambiar_el_estado_de_la_lista_de_bygui_sin_ser_admin(self):
        serie = Movie.objects.create(tmdb_id=14, title="Dark", media_type="tv")
        c = SecretMovie.objects.create(title="Dark", personal_rating="7.0", movie=serie)
        user = User.objects.create(email="visto_test3@test.local", role=User.Role.LECTOR, username="visto_test3")
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        response = self.client.post(f"{reverse('secret:movie-watch-cycle', args=[c.pk])}?scope=bygui")
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.series_watch_status, SecretMovie.SeriesWatchStatus.NOT_WATCHED)

    def test_lista_completa_filtra_por_lista(self):
        terror = Genre.objects.create(name="Terror")
        self.a.genres.add(terror)

        response = self.client.get(reverse("secret:list"), {"genres": [terror.slug]})
        self.assertEqual(list(response.context["movies"]), [self.a])

    def test_lista_completa_filtra_por_varias_listas_a_la_vez(self):
        terror = Genre.objects.create(name="Terror")
        slasher = Genre.objects.create(name="Slasher")
        self.a.genres.add(terror, slasher)
        self.b.genres.add(terror)

        response = self.client.get(reverse("secret:list"), {"genres": [terror.slug, slasher.slug]})
        self.assertEqual(list(response.context["movies"]), [self.a])

    def test_lista_completa_combina_genero_y_orden(self):
        terror = Genre.objects.create(name="Terror")
        self.a.genres.add(terror)
        self.b.genres.add(terror)
        peor_de_terror = SecretMovie.objects.create(title="Peor de Terror", personal_rating="4.0")
        peor_de_terror.genres.add(terror)

        response = self.client.get(reverse("secret:list"), {"genres": [terror.slug], "sort": "asc"})
        self.assertEqual(list(response.context["movies"]), [peor_de_terror, self.b, self.a])

    def test_orden_por_defecto_es_nota_descendente(self):
        response = self.client.get(reverse("secret:list"))
        self.assertEqual(list(response.context["movies"]), [self.a, self.b])
        self.assertEqual(response.context["sort"], "desc")

    def test_ordenar_ascendente_invierte_el_orden(self):
        response = self.client.get(reverse("secret:list"), {"sort": "asc"})
        self.assertEqual(list(response.context["movies"]), [self.b, self.a])
        self.assertEqual(response.context["sort"], "asc")

    def test_ordenar_peliculas_primero_agrupa_por_tipo(self):
        pelicula = Movie.objects.create(tmdb_id=101, title="Una peli", media_type="movie")
        serie = Movie.objects.create(tmdb_id=102, title="Una serie", media_type="tv")
        peli_baja = SecretMovie.objects.create(title="Peli floja", personal_rating="5.0", movie=pelicula)
        serie_alta = SecretMovie.objects.create(title="Serie top", personal_rating="9.8", movie=serie)
        sin_enlace = SecretMovie.objects.create(title="Sin enlazar", personal_rating="7.0")

        response = self.client.get(reverse("secret:list"), {"sort": "movies_first"})
        # self.a y self.b (sin movie enlazado) del setUp también caen en
        # "sin enlazar" — solo importa que las películas vayan primero,
        # pese a tener menos nota que la serie, y que la serie no se cuele
        # antes que las películas.
        result = list(response.context["movies"])
        self.assertEqual(result[0], peli_baja)
        self.assertLess(result.index(peli_baja), result.index(serie_alta))

    def test_ordenar_series_primero_agrupa_por_tipo(self):
        pelicula = Movie.objects.create(tmdb_id=201, title="Una peli", media_type="movie")
        serie = Movie.objects.create(tmdb_id=202, title="Una serie", media_type="tv")
        peli_alta = SecretMovie.objects.create(title="Peli top", personal_rating="9.8", movie=pelicula)
        serie_baja = SecretMovie.objects.create(title="Serie floja", personal_rating="5.0", movie=serie)

        response = self.client.get(reverse("secret:list"), {"sort": "series_first"})
        result = list(response.context["movies"])
        self.assertLess(result.index(serie_baja), result.index(peli_alta))

    def test_no_se_muestra_el_numero_interno_en_la_lista(self):
        response = self.client.get(reverse("secret:list"))
        self.assertNotContains(response, "#1 —")
        self.assertNotContains(response, "#2 —")

    def test_la_nota_personal_se_muestra_en_cada_fila(self):
        """La corrección de una petición anterior: el número interno (#1)
        se oculta, pero el badge con la nota personal debe seguir ahí."""
        response = self.client.get(reverse("secret:list"))
        # Django localiza el decimal a coma (es) al renderizarlo en la plantilla.
        self.assertContains(response, "9,0")
        self.assertContains(response, "8,5")

    def test_no_hay_desplegable_de_filtro_por_nota(self):
        response = self.client.get(reverse("secret:list"))
        self.assertNotIn("rating", response.context["form"].fields)

    def test_pagina_mas_de_24_reparte_en_paginas(self):
        for i in range(25):
            SecretMovie.objects.create(title=f"Extra {i}", personal_rating="5.0")

        response = self.client.get(reverse("secret:list"))
        self.assertEqual(len(response.context["movies"]), 24)
        self.assertTrue(response.context["movies"].has_next())

        response_pagina_2 = self.client.get(reverse("secret:list"), {"page": 2}, HTTP_HX_REQUEST="true")
        self.assertEqual(response_pagina_2.status_code, 200)
        self.assertTemplateUsed(response_pagina_2, "secret/_list_items.html")
        self.assertTemplateNotUsed(response_pagina_2, "secret/list.html")

    def test_las_listas_no_salen_visibles_de_entrada_en_la_fila(self):
        terror = Genre.objects.create(name="Terror")
        self.a.genres.add(terror)

        response = self.client.get(reverse("secret:list"))
        self.assertContains(response, "Ver listas")
        self.assertNotContains(response, "Marca varias para cruzarlas")

    def test_cada_fila_enlaza_a_su_ficha_de_detalle(self):
        response = self.client.get(reverse("secret:list"))
        self.assertContains(response, reverse("secret:movie-detail", args=[self.a.pk]))

    def test_pagina_de_detalle_muestra_portada_nota_y_comentario(self):
        self.a.comment = "Mi comentario sobre esta película."
        self.a.save(update_fields=["comment"])

        response = self.client.get(reverse("secret:movie-detail", args=[self.a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.a.title)
        self.assertContains(response, "Mi comentario sobre esta película.")

    def test_ficha_completa_respeta_los_saltos_de_linea_del_comentario(self):
        # El <p> del comentario necesita la misma clase que ya usaba el de
        # Lista completa (white-space: pre-line) para que los saltos de
        # línea que se escriban se vean tal cual, no todos seguidos.
        self.a.comment = "Primera línea.\nSegunda línea."
        self.a.save(update_fields=["comment"])

        response = self.client.get(reverse("secret:movie-detail", args=[self.a.pk]))
        self.assertContains(response, '<p class="secret-movie__comment">Primera línea.\nSegunda línea.</p>')

    def test_ficha_completa_muestra_el_cuadradito_de_visto_en_series(self):
        serie = Movie.objects.create(tmdb_id=20, title="Dark", media_type="tv")
        self.a.movie = serie
        self.a.save()

        response = self.client.get(reverse("secret:movie-detail", args=[self.a.pk]))
        self.assertContains(response, "secret-movie__watch-badge")
        self.assertContains(response, "secret-movie__watch-badge--not_watched")

    def test_ficha_completa_no_muestra_el_cuadradito_en_peliculas(self):
        peli = Movie.objects.create(tmdb_id=21, title="Drive", media_type="movie")
        self.a.movie = peli
        self.a.save()

        response = self.client.get(reverse("secret:movie-detail", args=[self.a.pk]))
        self.assertNotContains(response, "secret-movie__watch-badge")

    def test_click_en_el_cuadradito_desde_la_ficha_completa_devuelve_su_propio_fragmento(self):
        serie = Movie.objects.create(tmdb_id=22, title="Dark", media_type="tv")
        user = User.objects.create(email="visto_ficha@test.local", role=User.Role.LECTOR, username="visto_ficha")
        user.set_password("Testpass123!")
        user.save()
        c = SecretMovie.objects.create(owner=user, title="Dark", personal_rating="7.0", movie=serie)
        self.client.login(username=user.email, password="Testpass123!")

        response = self.client.post(reverse("secret:movie-watch-cycle", args=[c.pk]) + "?context=detail")
        self.assertContains(response, "movie-detail__poster-wrap")
        self.assertContains(response, "secret-movie__watch-badge--airing")

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


class SecretMovieQuickEditTests(TestCase):
    """Edición desde una lista completa (no el admin). Para la lista de
    Bygui (owner=None) sigue haciendo falta ser Admin y que
    TopSecretConfig.allow_web_editing esté activo, igual que antes de que
    existieran las listas propias. Para tu propia lista (owner=tú) es
    siempre editable, sin ningún interruptor de por medio."""

    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.movie = SecretMovie.objects.create(title="Reservoir Dogs", personal_rating="9.0")
        self.admin = User.objects.create(email="edit_admin@test.local", role=User.Role.ADMIN, username="edit_admin")
        self.admin.set_password("Testpass123!")
        self.admin.save()
        self.user = User.objects.create(email="edit_test@test.local", role=User.Role.LECTOR, username="edit_test")
        self.user.set_password("Testpass123!")
        self.user.save()

    def _enable_web_editing(self):
        config = TopSecretConfig.load()
        config.allow_web_editing = True
        config.save()

    def test_editar_da_404_si_el_interruptor_esta_apagado(self):
        self.client.login(username=self.admin.email, password="Testpass123!")
        response = self.client.post(reverse("secret:movie-quick-edit", args=[self.movie.pk]), {
            "personal_rating": "7.5", "tie_break": "0",
        })
        self.assertEqual(response.status_code, 404)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.personal_rating, Decimal("9.0"))

    def test_editar_requiere_login_aunque_el_interruptor_este_encendido(self):
        self._enable_web_editing()
        response = self.client.post(reverse("secret:movie-quick-edit", args=[self.movie.pk]), {
            "personal_rating": "7.5", "tie_break": "0",
        })
        self.assertIn("/cuenta/login/", response.url)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.personal_rating, Decimal("9.0"))

    def test_un_lector_no_puede_editar_la_lista_de_bygui_ni_con_el_interruptor_encendido(self):
        self._enable_web_editing()
        self.client.login(username=self.user.email, password="Testpass123!")
        response = self.client.post(f"{reverse('secret:movie-quick-edit', args=[self.movie.pk])}", {
            "scope": "bygui", "personal_rating": "7.5", "tie_break": "0",
        })
        self.assertEqual(response.status_code, 404)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.personal_rating, Decimal("9.0"))

    def test_editar_nota_y_listas_con_el_interruptor_encendido(self):
        self._enable_web_editing()
        self.client.login(username=self.admin.email, password="Testpass123!")
        terror = Genre.objects.create(name="Terror")

        response = self.client.post(reverse("secret:movie-quick-edit", args=[self.movie.pk]), {
            "title": self.movie.title, "personal_rating": "7.5", "tie_break": "3",
            "genres": [terror.pk], "new_genres_input": "Culto",
        })
        self.assertRedirects(response, reverse("secret:list"))
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.personal_rating, Decimal("7.5"))
        self.assertEqual(self.movie.tie_break, 3)
        self.assertEqual(set(self.movie.genres.values_list("name", flat=True)), {"Terror", "Culto"})

    def test_editar_titulo_con_el_interruptor_encendido(self):
        self._enable_web_editing()
        self.client.login(username=self.admin.email, password="Testpass123!")

        self.client.post(reverse("secret:movie-quick-edit", args=[self.movie.pk]), {
            "title": "Reservoir Dogs (1992)", "personal_rating": "9.0", "tie_break": "0",
        })
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.title, "Reservoir Dogs (1992)")

    def test_un_lector_puede_editar_su_propia_lista_sin_interruptor(self):
        propia = SecretMovie.objects.create(owner=self.user, title="Kill Bill", personal_rating="8.0")
        self.client.login(username=self.user.email, password="Testpass123!")

        response = self.client.post(reverse("secret:movie-quick-edit", args=[propia.pk]), {
            "title": "Kill Bill Vol. 1", "personal_rating": "9.0", "tie_break": "0", "comment": "Genial",
        })
        self.assertRedirects(response, reverse("secret:list"))
        propia.refresh_from_db()
        self.assertEqual(propia.title, "Kill Bill Vol. 1")
        self.assertEqual(propia.personal_rating, Decimal("9.0"))
        self.assertEqual(propia.comment, "Genial")

    def test_un_lector_no_puede_editar_la_lista_propia_de_otro(self):
        other = User.objects.create(email="otra_lista@test.local", role=User.Role.LECTOR, username="otra_lista")
        ajena = SecretMovie.objects.create(owner=other, title="Ajena", personal_rating="7.0")
        self.client.login(username=self.user.email, password="Testpass123!")

        response = self.client.post(reverse("secret:movie-quick-edit", args=[ajena.pk]), {
            "title": "Hackeada", "personal_rating": "1.0", "tie_break": "0",
        })
        self.assertEqual(response.status_code, 404)
        ajena.refresh_from_db()
        self.assertEqual(ajena.title, "Ajena")

    def test_lista_completa_no_enseña_el_formulario_de_edicion_sin_el_interruptor(self):
        response = self.client.get(reverse("secret:list"))
        self.assertNotContains(response, "secret-movie__edit-form")

    def test_lista_completa_enseña_el_formulario_de_edicion_con_el_interruptor(self):
        self._enable_web_editing()
        self.client.login(username=self.admin.email, password="Testpass123!")
        response = self.client.get(reverse("secret:list"))
        self.assertContains(response, "secret-movie__edit-form")


class AdminOnlyMovieTests(TestCase):
    """Una película marcada `admin_only` a ella misma (sin pasar por
    ninguna lista) tampoco la ve nadie que no sea Admin, aunque tenga el
    código — independiente de en qué listas esté."""

    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.oculta = SecretMovie.objects.create(title="Solo para mí", personal_rating="9.0", admin_only=True)
        self.visible = SecretMovie.objects.create(title="Para todos", personal_rating="8.0")

        self.admin = User.objects.create(email="admin_only_movie@test.local", role=User.Role.ADMIN)
        self.admin.set_password("Testpass123!")
        self.admin.save()

    def test_no_admin_no_ve_la_pelicula_oculta_en_la_lista_completa(self):
        response = self.client.get(reverse("secret:list"))
        self.assertEqual(list(response.context["movies"]), [self.visible])

    def test_admin_si_ve_la_pelicula_oculta_en_la_lista_completa(self):
        self.client.login(username=self.admin.email, password="Testpass123!")
        response = self.client.get(reverse("secret:list"))
        self.assertIn(self.oculta, list(response.context["movies"]))

    def test_no_admin_no_puede_acceder_a_la_ficha_de_la_pelicula_oculta(self):
        response = self.client.get(reverse("secret:movie-detail", args=[self.oculta.pk]))
        self.assertEqual(response.status_code, 404)

    def test_no_admin_no_puede_acceder_a_la_pelicula_oculta_por_numero(self):
        response = self.client.get(reverse("secret:by-number"), {"number": self.oculta.number})
        self.assertEqual(response.status_code, 404)


class MoviePosterEditTests(TestCase):
    """Buscar y enlazar/quitar la portada de una entrada de Lista completa
    desde la propia web (mismo hueco e interruptor que nota/desempate/
    listas, ver SecretMovieQuickEditTests)."""

    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.movie = SecretMovie.objects.create(title="Drive", personal_rating="8.0")
        self.user = User.objects.create(email="poster_test@test.local", role=User.Role.ADMIN, username="poster_test")
        self.user.set_password("Testpass123!")
        self.user.save()

    def _enable_web_editing(self):
        config = TopSecretConfig.load()
        config.allow_web_editing = True
        config.save()

    def test_buscar_da_404_si_el_interruptor_esta_apagado(self):
        self.client.login(username=self.user.email, password="Testpass123!")
        response = self.client.get(reverse("secret:movie-poster-search", args=[self.movie.pk]))
        self.assertEqual(response.status_code, 404)

    @patch("apps.secret.views.tmdb_search")
    def test_buscar_usa_el_servicio_tmdb_con_el_interruptor_encendido(self, mock_search):
        self._enable_web_editing()
        self.client.login(username=self.user.email, password="Testpass123!")
        mock_search.return_value = []
        response = self.client.get(reverse("secret:movie-poster-search", args=[self.movie.pk]), {"query": "drive"})
        self.assertEqual(response.status_code, 200)
        mock_search.assert_called_once_with("drive")

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_enlazar_una_portada(self, mock_get_or_create):
        self._enable_web_editing()
        self.client.login(username=self.user.email, password="Testpass123!")
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=55, title="Drive", media_type="movie")

        response = self.client.post(reverse("secret:movie-poster-set", args=[self.movie.pk, 55]))
        self.assertRedirects(response, f"{reverse('secret:list')}?scope=own")
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.movie.tmdb_id, 55)

    def test_enlazar_portada_da_404_si_el_interruptor_esta_apagado(self):
        self.client.login(username=self.user.email, password="Testpass123!")
        response = self.client.post(reverse("secret:movie-poster-set", args=[self.movie.pk, 55]))
        self.assertEqual(response.status_code, 404)

    def test_quitar_la_portada(self):
        self._enable_web_editing()
        catalog_movie = Movie.objects.create(tmdb_id=56, title="Drive", media_type="movie")
        self.movie.movie = catalog_movie
        self.movie.save(update_fields=["movie"])

        self.client.login(username=self.user.email, password="Testpass123!")
        response = self.client.post(reverse("secret:movie-poster-remove", args=[self.movie.pk]))
        self.assertRedirects(response, reverse("secret:list"))
        self.movie.refresh_from_db()
        self.assertIsNone(self.movie.movie)


class OwnMovieAddTests(TestCase):
    """El flujo de "+ Añadir película o serie a mi lista": elegir un
    resultado de búsqueda debe crear la entrada en tu lista propia y
    llevarte a su ficha ya en modo edición -- sin quedarse a medias."""

    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.user = User.objects.create(email="own_movie_add@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_elegir_una_pelicula_la_anade_y_lleva_a_su_ficha_en_edicion(self, mock_get_or_create):
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=42, title="Alien", media_type="movie")
        response = self.client.post(reverse("secret:own-movie-add", args=["movie", 42]))

        entry = SecretMovie.objects.get(owner=self.user, movie__tmdb_id=42)
        self.assertRedirects(response, f"{reverse('secret:movie-detail', args=[entry.pk])}?scope=own&edit=1&fresh=1")
        mock_get_or_create.assert_called_once_with(42, media_type="movie")

        # La ficha en sí carga bien y ya sale en modo edición.
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alien")
        self.assertContains(response, "editing: true")

        # El campo de nota sale vacío (con &fresh=1) en vez de mostrar la
        # nota provisional "5" que el modelo exige internamente -- si no
        # se tocara, se vería como si ya estuviera puntuada.
        self.assertContains(response, 'placeholder="Pon tu nota (1-10)"')
        self.assertNotContains(response, 'value="5.0"')
        self.assertNotContains(response, 'value="5,0"')

        # Sin &fresh=1 (una edición normal, no recién añadida) sí se ve
        # la nota real.
        response = self.client.get(f"{reverse('secret:movie-detail', args=[entry.pk])}?scope=own&edit=1")
        self.assertNotContains(response, 'placeholder="Pon tu nota (1-10)"')

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_elegir_una_serie_la_anade_con_su_media_type(self, mock_get_or_create):
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=43, title="The Wire", media_type="tv")
        self.client.post(reverse("secret:own-movie-add", args=["tv", 43]))
        mock_get_or_create.assert_called_once_with(43, media_type="tv")
        self.assertTrue(SecretMovie.objects.filter(owner=self.user, movie__tmdb_id=43).exists())

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_elegir_la_misma_pelicula_dos_veces_no_la_duplica(self, mock_get_or_create):
        movie = Movie.objects.create(tmdb_id=44, title="Dupe", media_type="movie")
        mock_get_or_create.return_value = movie
        self.client.post(reverse("secret:own-movie-add", args=["movie", 44]))
        self.client.post(reverse("secret:own-movie-add", args=["movie", 44]))
        self.assertEqual(SecretMovie.objects.filter(owner=self.user, movie=movie).count(), 1)

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_si_tmdb_falla_no_rompe_solo_avisa_y_vuelve_a_la_lista(self, mock_get_or_create):
        mock_get_or_create.side_effect = MovieAPIError("fallo de TMDb")
        response = self.client.post(reverse("secret:own-movie-add", args=["movie", 45]))
        self.assertRedirects(response, f"{reverse('secret:list')}?scope=own")
        self.assertFalse(SecretMovie.objects.filter(owner=self.user).exists())

    def test_get_no_anade_nada_solo_redirige(self):
        # El botón "+ Elegir" es un <form method="post">; una petición GET
        # a la misma URL (ej. si algo la enlazase mal) no debe dar de alta.
        response = self.client.get(reverse("secret:own-movie-add", args=["movie", 46]))
        self.assertRedirects(response, f"{reverse('secret:list')}?scope=own")
        self.assertFalse(SecretMovie.objects.filter(owner=self.user).exists())

    def test_boton_elegir_esta_en_los_resultados_de_busqueda(self):
        with patch("apps.secret.views.tmdb_search") as mock_search:
            from apps.movies.services import TMDbResult
            mock_search.return_value = [
                TMDbResult(tmdb_id=47, title="Encontrada", year="2024", poster_path="", overview="", media_type="movie"),
            ]
            response = self.client.get(reverse("secret:own-movie-add-search"), {"query": "encontrada"})
        self.assertContains(response, reverse("secret:own-movie-add", args=["movie", 47]))
        self.assertContains(response, "+ Elegir")


class OwnMovieAddAsAdminTests(TestCase):
    """Para Admin, "tu propia lista" es la lista de Bygui: owner=None
    (ver _resolve_scope). own_movie_add/own_movie_delete tenían un fallo
    -- guardaban/buscaban con owner=request.user (su usuario real) en vez
    de owner=None, así que lo que Admin añadía se volvía invisible (404)
    en cuanto lo miraba con scope=own. Repro exacta del bug reportado:
    "al añadir película, ahora te dice que no está"."""

    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.admin = User.objects.create(email="own_movie_add_admin@test.local", role=User.Role.ADMIN)
        self.admin.set_password("Testpass123!")
        self.admin.save()
        self.client.login(username=self.admin.email, password="Testpass123!")

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_admin_anade_una_pelicula_y_la_encuentra_en_su_propia_lista(self, mock_get_or_create):
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=42, title="Alien", media_type="movie")
        response = self.client.post(reverse("secret:own-movie-add", args=["movie", 42]))

        entry = SecretMovie.objects.get(movie__tmdb_id=42)
        self.assertIsNone(entry.owner)  # guardada como la de Bygui, no bajo el usuario real de Admin
        self.assertRedirects(response, f"{reverse('secret:movie-detail', args=[entry.pk])}?scope=own&edit=1&fresh=1")

        # La ficha se ve de verdad con scope=own -- antes daba 404 aquí.
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alien")

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_admin_anade_la_misma_pelicula_dos_veces_no_la_duplica_ni_da_404(self, mock_get_or_create):
        movie = Movie.objects.create(tmdb_id=44, title="Dupe", media_type="movie")
        mock_get_or_create.return_value = movie
        self.client.post(reverse("secret:own-movie-add", args=["movie", 44]))
        response = self.client.post(reverse("secret:own-movie-add", args=["movie", 44]))

        self.assertEqual(SecretMovie.objects.filter(movie=movie, owner=None).count(), 1)
        self.assertEqual(response.status_code, 302)
        detail_response = self.client.get(response.url)
        self.assertEqual(detail_response.status_code, 200)

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_con_la_edicion_desactivada_se_explica_por_que_en_vez_de_no_decir_nada(self, mock_get_or_create):
        # allow_web_editing es False por defecto -- antes, con esto
        # apagado, la ficha recién creada no mostraba ni el formulario ni
        # ninguna pista de por qué no se podía editar/borrar nada.
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=46, title="Sin editar", media_type="movie")
        response = self.client.post(reverse("secret:own-movie-add", args=["movie", 46]))
        detail_response = self.client.get(response.url)
        self.assertContains(detail_response, "La edición desde la web está desactivada")
        self.assertNotContains(detail_response, "Editar título, nota, comentario, listas y portada")

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_admin_borra_una_pelicula_de_su_propia_lista(self, mock_get_or_create):
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=45, title="A borrar", media_type="movie")
        self.client.post(reverse("secret:own-movie-add", args=["movie", 45]))
        entry = SecretMovie.objects.get(movie__tmdb_id=45)

        response = self.client.post(reverse("secret:own-movie-delete", args=[entry.pk]))
        self.assertRedirects(response, f"{reverse('secret:list')}?scope=own")
        self.assertFalse(SecretMovie.objects.filter(pk=entry.pk).exists())


class GenreManageTests(TestCase):
    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.user = User.objects.create(email="genre_manage_test@test.local", role=User.Role.ADMIN, username="genre_manage_test")
        self.user.set_password("Testpass123!")
        self.user.save()
        config = TopSecretConfig.load()
        config.allow_web_editing = True
        config.save()

    def test_pagina_de_gestion_da_404_si_el_interruptor_esta_apagado(self):
        config = TopSecretConfig.load()
        config.allow_web_editing = False
        config.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        response = self.client.get(reverse("secret:genre-manage"))
        self.assertEqual(response.status_code, 404)

    def test_crear_lista(self):
        self.client.login(username=self.user.email, password="Testpass123!")
        response = self.client.post(reverse("secret:genre-manage"), {"name": "Infravaloradas"})
        self.assertRedirects(response, f"{reverse('secret:genre-manage')}?scope=own")
        self.assertTrue(Genre.objects.filter(name="Infravaloradas").exists())

    def test_borrar_lista(self):
        self.client.login(username=self.user.email, password="Testpass123!")
        genre = Genre.objects.create(name="Terror")
        response = self.client.post(reverse("secret:genre-delete", args=[genre.pk]))
        self.assertRedirects(response, f"{reverse('secret:genre-manage')}?scope=own")
        self.assertFalse(Genre.objects.filter(pk=genre.pk).exists())


class GenreSortableAdminTests(TestCase):
    """Arrastrar para reordenar las listas de Top Secret (Genre), igual que
    Temas o Enlaces de contacto — ver SortableAdminMixin en apps/core/admin.py."""

    def setUp(self):
        self.admin = User.objects.create(email="drag_genre_admin@test.local", role=User.Role.ADMIN, is_staff=True, is_superuser=True)
        self.admin.set_password("Testpass123!")
        self.admin.save()
        self.client.login(username=self.admin.email, password="Testpass123!")
        self.a = Genre.objects.create(name="Terror", order=0)
        self.b = Genre.objects.create(name="Comedia", order=1)
        self.c = Genre.objects.create(name="Drama", order=2)

    def test_arrastrar_actualiza_el_orden_de_todas(self):
        url = reverse("admin:secret_genre_reorder")
        response = self.client.post(
            url, data='{"order": [%d, %d, %d]}' % (self.c.pk, self.a.pk, self.b.pk),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.c.refresh_from_db()
        self.assertEqual(self.c.order, 0)
        self.assertEqual(self.a.order, 1)
        self.assertEqual(self.b.order, 2)

    def test_el_listado_tiene_el_tirador_de_arrastre(self):
        response = self.client.get(reverse("admin:secret_genre_changelist"))
        self.assertContains(response, "drag-handle")


class SecretMovieAdminWatchStatusTests(TestCase):
    """El campo "estado de visionado (series)" está siempre en el
    formulario (para poder mostrarlo/ocultarlo al vuelo desde JS según la
    portada elegida, sin depender de guardar y volver a abrir la entrada
    — ver static/js/admin_secret_movie_watch_status.js), y el endpoint que
    esa JS consulta dice si una película del catálogo es una serie."""

    def setUp(self):
        self.admin = User.objects.create(email="watch_status_admin@test.local", role=User.Role.ADMIN, is_staff=True, is_superuser=True)
        self.admin.set_password("Testpass123!")
        self.admin.save()
        self.client.login(username=self.admin.email, password="Testpass123!")

    def test_el_formulario_de_anadir_incluye_el_campo_aunque_no_haya_portada_todavia(self):
        response = self.client.get(reverse("admin:secret_secretmovie_add"))
        self.assertContains(response, "id_series_watch_status")

    def test_el_endpoint_dice_si_la_pelicula_es_una_serie(self):
        serie = Movie.objects.create(tmdb_id=30, title="Dark", media_type="tv")
        peli = Movie.objects.create(tmdb_id=31, title="Drive", media_type="movie")

        response = self.client.get(reverse("admin:secret_secretmovie_movie_is_tv", args=[serie.pk]))
        self.assertEqual(response.json(), {"is_tv": True})

        response = self.client.get(reverse("admin:secret_secretmovie_movie_is_tv", args=[peli.pk]))
        self.assertEqual(response.json(), {"is_tv": False})

    def test_el_endpoint_requiere_ser_staff(self):
        self.client.logout()
        response = self.client.get(reverse("admin:secret_secretmovie_movie_is_tv", args=[1]))
        self.assertNotEqual(response.status_code, 200)

    def test_el_listado_se_puede_editar_desde_cualquier_columna_no_solo_el_numero(self):
        # Por defecto Django solo deja clicable la primera columna (number)
        # — aquí cualquier columna visible debe llevar a la ficha de edición.
        movie = SecretMovie.objects.create(title="Reservoir Dogs", personal_rating="9.0")
        response = self.client.get(reverse("admin:secret_secretmovie_changelist"))
        change_url = reverse("admin:secret_secretmovie_change", args=[movie.pk])
        html = response.content.decode()
        title_cell = html[html.index('class="field-title"'):]
        self.assertIn(f'href="{change_url}"', title_cell[:300])

    def test_desplegable_ver_la_lista_de_incluye_bygui_y_cada_dueno_con_conteo(self):
        friend = User.objects.create(email="owner_quick_nav@test.local", role=User.Role.LECTOR, username="marta_admin_nav")
        SecretMovie.objects.create(title="De Bygui 1", personal_rating="9.0")
        SecretMovie.objects.create(title="De Bygui 2", personal_rating="8.0")
        SecretMovie.objects.create(owner=friend, title="De Marta", personal_rating="7.0")

        response = self.client.get(reverse("admin:secret_secretmovie_changelist"))
        self.assertContains(response, "Ver la lista de:")
        self.assertContains(response, "🕶️ lasaladebygui (sin dueño) (2)")
        self.assertContains(response, "marta_admin_nav (1)")

    def test_elegir_a_alguien_en_el_desplegable_filtra_solo_lo_suyo(self):
        friend = User.objects.create(email="owner_quick_nav2@test.local", role=User.Role.LECTOR, username="alex_admin_nav")
        SecretMovie.objects.create(title="De Bygui", personal_rating="9.0")
        SecretMovie.objects.create(owner=friend, title="Solo de Alex", personal_rating="7.0")

        response = self.client.get(reverse("admin:secret_secretmovie_changelist"), {"owner__id__exact": friend.pk})
        self.assertContains(response, "Solo de Alex")
        self.assertNotContains(response, "De Bygui")
        # Esa misma opción debe salir marcada como seleccionada en el desplegable.
        self.assertContains(response, f'value="?owner__id__exact={friend.pk}" selected')

    def test_sin_ninguna_pelicula_todavia_el_desplegable_no_revienta(self):
        # Siempre sale al menos la opción de Bygui (con 0), para que el
        # desplegable exista igual en una instalación recién estrenada.
        response = self.client.get(reverse("admin:secret_secretmovie_changelist"))
        self.assertContains(response, "Ver la lista de:")
        self.assertContains(response, "🕶️ lasaladebygui (sin dueño) (0)")


class AdminOnlyGenreTests(TestCase):
    """Una lista marcada `admin_only` (y las películas que tenga) no la ve
    nadie que no sea Admin, aunque tenga el código del maletín."""

    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.secreta = Genre.objects.create(name="Solo Bygui", admin_only=True)
        self.publica = Genre.objects.create(name="Terror")
        self.oculta = SecretMovie.objects.create(title="Solo para mí", personal_rating="9.0")
        self.oculta.genres.add(self.secreta)
        self.visible = SecretMovie.objects.create(title="Para todos", personal_rating="8.0")
        self.visible.genres.add(self.publica)

        self.admin = User.objects.create(email="admin_top_secret@test.local", role=User.Role.ADMIN)
        self.admin.set_password("Testpass123!")
        self.admin.save()

    def test_no_admin_no_ve_la_pelicula_oculta_en_la_lista_completa(self):
        response = self.client.get(reverse("secret:list"))
        self.assertEqual(list(response.context["movies"]), [self.visible])

    def test_admin_si_ve_la_pelicula_oculta_en_la_lista_completa(self):
        self.client.login(username=self.admin.email, password="Testpass123!")
        response = self.client.get(reverse("secret:list"))
        self.assertIn(self.oculta, list(response.context["movies"]))

    def test_no_admin_no_ve_la_lista_privada_en_el_filtro(self):
        response = self.client.get(reverse("secret:list"))
        self.assertNotIn(self.secreta, list(response.context["form"].fields["genres"].queryset))

    def test_admin_si_ve_la_lista_privada_en_el_filtro(self):
        self.client.login(username=self.admin.email, password="Testpass123!")
        response = self.client.get(reverse("secret:list"))
        self.assertIn(self.secreta, list(response.context["form"].fields["genres"].queryset))

    def test_no_admin_no_puede_acceder_a_la_pelicula_oculta_por_numero(self):
        response = self.client.get(reverse("secret:by-number"), {"number": self.oculta.number})
        self.assertEqual(response.status_code, 404)

    def test_no_admin_no_puede_acceder_a_la_ficha_de_la_pelicula_oculta(self):
        response = self.client.get(reverse("secret:movie-detail", args=[self.oculta.pk]))
        self.assertEqual(response.status_code, 404)

    def test_no_admin_no_ve_la_lista_privada_en_el_buscador_por_nota(self):
        response = self.client.get(reverse("secret:by-rating"))
        self.assertNotIn(self.secreta, list(response.context["genres"]))

    def test_no_admin_buscando_por_la_lista_privada_no_encuentra_nada(self):
        response = self.client.get(reverse("secret:by-rating"), {
            "min_rating": 1, "max_rating": 10, "genre": self.secreta.slug,
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
        # A mayor valor de tie_break, mejor puesto (número más bajo).
        a = SecretMovie.objects.create(title="A", personal_rating="9.0", tie_break=1)
        b = SecretMovie.objects.create(title="B", personal_rating="9.0", tie_break=0)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.number, 1)
        self.assertEqual(b.number, 2)

    def test_cambiar_el_tie_break_reordena_el_empate(self):
        a = SecretMovie.objects.create(title="A", personal_rating="9.0", tie_break=0)
        b = SecretMovie.objects.create(title="B", personal_rating="9.0", tie_break=1)
        b.refresh_from_db()
        self.assertEqual(b.number, 1)

        a.tie_break = 5
        a.save()
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.number, 1)
        self.assertEqual(b.number, 2)

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
    """Las listas ya no se escriben a mano de cero cada vez: las que
    existen se marcan con casillas (genres), y solo hace falta escribir
    algo en new_genres_input si la lista es de verdad nueva."""

    def test_crea_generos_sobre_la_marcha(self):
        form = SecretMovieForm(data={
            "number": 1, "title": "Kill Bill", "personal_rating": "9.0",
            "comment": "", "genres": [], "new_genres_input": "acción, venganza, Tarantino",
        })
        self.assertTrue(form.is_valid(), form.errors)
        movie = form.save()
        self.assertEqual(
            set(movie.genres.values_list("name", flat=True)),
            {"acción", "venganza", "Tarantino"},
        )

    def test_reutiliza_generos_existentes_marcando_la_casilla(self):
        terror = Genre.objects.create(name="Terror")
        form = SecretMovieForm(data={
            "number": 1, "title": "El resplandor", "personal_rating": "9.5",
            "comment": "", "genres": [terror.pk], "new_genres_input": "Drama",
        })
        self.assertTrue(form.is_valid(), form.errors)
        movie = form.save()
        self.assertEqual(Genre.objects.count(), 2)
        self.assertEqual(movie.genres.count(), 2)

    def test_editar_precarga_los_generos_actuales(self):
        movie = SecretMovie.objects.create(title="X", personal_rating="8.0")
        drama = Genre.objects.create(name="Drama")
        movie.genres.add(drama)
        form = SecretMovieForm(instance=movie)
        self.assertEqual(list(form.fields["genres"].initial), [drama])


class TierListTests(TestCase):
    """El tier list es personal de cada usuario, igual que el calendario:
    cada test parte de su propio conjunto de niveles."""

    def setUp(self):
        self.user = User.objects.create(email="tierlist@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.s = TierLevel.objects.create(user=self.user, name="S", color="#FFD700", order=0)
        self.d = TierLevel.objects.create(user=self.user, name="D", color="#D98C8C", order=1)

    def test_agrupa_por_nivel(self):
        TierListEntry.objects.create(user=self.user, tier=self.s, title="Pulp Fiction", order=1)
        TierListEntry.objects.create(user=self.user, tier=self.s, title="Kill Bill", order=2)
        TierListEntry.objects.create(user=self.user, tier=self.d, title="Una película mala", order=1)

        response = self.client.get(reverse("secret:tier-list"))
        level_rows = dict(response.context["level_rows"])
        self.assertEqual([e.title for e in level_rows[self.s]], ["Pulp Fiction", "Kill Bill"])
        self.assertEqual([e.title for e in level_rows[self.d]], ["Una película mala"])

    def test_no_muestra_el_tier_list_de_otro_usuario(self):
        other = User.objects.create(email="otro_tier@test.local", role=User.Role.LECTOR)
        other_level = TierLevel.objects.create(user=other, name="S", color="#FFD700", order=0)
        TierListEntry.objects.create(user=other, tier=other_level, title="Ajena", order=1)

        response = self.client.get(reverse("secret:tier-list"))
        level_rows = dict(response.context["level_rows"])
        self.assertNotIn(other_level, level_rows)

    def test_requiere_haber_entrado_al_maletin(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:tier-list"))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_requiere_login(self):
        anon_client = self.client_class()
        anon_client.post(reverse("secret:gate"), {"code": "8888"})
        response = anon_client.get(reverse("secret:tier-list"))
        self.assertIn("/cuenta/login/", response.url)

    def test_compartir_devuelve_una_imagen_png(self):
        TierListEntry.objects.create(user=self.user, tier=self.s, title="Pulp Fiction", order=1)
        TierListEntry.objects.create(user=self.user, tier=None, title="Sin clasificar todavía", order=1)
        response = self.client.get(reverse("secret:tier-list-share-image"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_compartir_con_tier_list_vacia_no_rompe(self):
        response = self.client.get(reverse("secret:tier-list-share-image"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_compartir_requiere_haber_entrado_al_maletin(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:tier-list-share-image"))
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
        self.assertEqual(entry.user, self.user)
        self.assertIsNone(entry.tier)
        self.assertEqual(entry.title, "Nueva película")

    @patch("apps.secret.views.Movie.get_or_create_from_tmdb", side_effect=MovieAPIError("fallo"))
    def test_error_de_tmdb_al_anadir_no_rompe_la_pagina(self, mock_get_or_create):
        response = self.client.post(reverse("secret:tier-list-add", args=[99]))
        self.assertRedirects(response, reverse("secret:tier-list"))
        self.assertFalse(TierListEntry.objects.exists())

    def test_mover_cambia_de_nivel_y_se_coloca_al_final(self):
        TierListEntry.objects.create(user=self.user, tier=self.d, title="Ya en D", order=1)
        entry = TierListEntry.objects.create(user=self.user, tier=self.s, title="Se mueve", order=1)

        response = self.client.post(reverse("secret:tier-list-move", args=[entry.pk]), {"tier": self.d.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

        entry.refresh_from_db()
        self.assertEqual(entry.tier, self.d)
        self.assertEqual(entry.order, 2)

    def test_mover_a_sin_clasificar(self):
        entry = TierListEntry.objects.create(user=self.user, tier=self.s, title="X", order=1)
        response = self.client.post(reverse("secret:tier-list-move", args=[entry.pk]), {"tier": ""})
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertIsNone(entry.tier)

    def test_mover_con_nivel_invalido_da_error(self):
        entry = TierListEntry.objects.create(user=self.user, tier=self.s, title="X", order=1)
        response = self.client.post(reverse("secret:tier-list-move", args=[entry.pk]), {"tier": "9999"})
        self.assertEqual(response.status_code, 400)
        entry.refresh_from_db()
        self.assertEqual(entry.tier, self.s)

    def test_no_se_puede_mover_una_entrada_ajena(self):
        other = User.objects.create(email="otro_mover_tier@test.local", role=User.Role.LECTOR)
        other_level = TierLevel.objects.create(user=other, name="S", color="#FFD700", order=0)
        entry = TierListEntry.objects.create(user=other, tier=other_level, title="Ajena", order=1)
        response = self.client.post(reverse("secret:tier-list-move", args=[entry.pk]), {"tier": self.s.pk})
        self.assertEqual(response.status_code, 404)

    def test_mover_requiere_haber_entrado_al_maletin(self):
        entry = TierListEntry.objects.create(user=self.user, tier=self.s, title="X", order=1)
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:tier-list-move", args=[entry.pk]))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_reiniciar_vacia_toda_la_tier_list(self):
        TierListEntry.objects.create(user=self.user, tier=self.s, title="Uno", order=1)
        TierListEntry.objects.create(user=self.user, tier=None, title="Dos", order=1)
        response = self.client.post(reverse("secret:tier-list-reset"))
        self.assertRedirects(response, reverse("secret:tier-list"))
        self.assertFalse(TierListEntry.objects.filter(user=self.user).exists())

    def test_reiniciar_no_afecta_a_otro_usuario(self):
        other = User.objects.create(email="otro_reset_tier@test.local", role=User.Role.LECTOR)
        other_level = TierLevel.objects.create(user=other, name="S", color="#FFD700", order=0)
        TierListEntry.objects.create(user=other, tier=other_level, title="Ajena", order=1)
        self.client.post(reverse("secret:tier-list-reset"))
        self.assertTrue(TierListEntry.objects.filter(user=other).exists())

    def test_reiniciar_requiere_haber_entrado_al_maletin(self):
        TierListEntry.objects.create(user=self.user, tier=self.s, title="Uno", order=1)
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:tier-list-reset"))
        self.assertRedirects(response, reverse("secret:gate"))
        self.assertTrue(TierListEntry.objects.exists())


class TierLevelManagementTests(TestCase):
    """Nombre, color y alta/baja de niveles se gestionan enteros desde la
    propia página del Tier List, sin pasar por el admin."""

    def setUp(self):
        self.user = User.objects.create(email="tierlevel@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

    def test_anadir_nivel(self):
        response = self.client.post(reverse("secret:tier-level-create"), {"name": "Favoritas", "color": "#ABCDEF"})
        self.assertRedirects(response, reverse("secret:tier-list"))
        level = TierLevel.objects.get(name="Favoritas")
        self.assertEqual(level.user, self.user)
        self.assertEqual(level.color, "#ABCDEF")

    def test_nuevo_nivel_se_coloca_al_final(self):
        TierLevel.objects.create(user=self.user, name="S", color="#FFD700", order=0)
        self.client.post(reverse("secret:tier-level-create"), {"name": "Extra", "color": "#000000"})
        nuevo = TierLevel.objects.get(name="Extra")
        self.assertEqual(nuevo.order, 1)

    def test_editar_nivel_cambia_nombre_y_color(self):
        level = TierLevel.objects.create(user=self.user, name="S", color="#FFD700", order=0)
        response = self.client.post(
            reverse("secret:tier-level-update", args=[level.pk]), {"name": "Sobresaliente", "color": "#123456"},
        )
        self.assertRedirects(response, reverse("secret:tier-list"))
        level.refresh_from_db()
        self.assertEqual(level.name, "Sobresaliente")
        self.assertEqual(level.color, "#123456")

    def test_no_se_puede_editar_un_nivel_ajeno(self):
        other = User.objects.create(email="otro_nivel@test.local", role=User.Role.LECTOR)
        level = TierLevel.objects.create(user=other, name="S", color="#FFD700", order=0)
        response = self.client.post(
            reverse("secret:tier-level-update", args=[level.pk]), {"name": "Robado", "color": "#123456"},
        )
        self.assertEqual(response.status_code, 404)
        level.refresh_from_db()
        self.assertEqual(level.name, "S")

    def test_borrar_nivel_manda_sus_peliculas_a_sin_clasificar(self):
        level = TierLevel.objects.create(user=self.user, name="S", color="#FFD700", order=0)
        entry = TierListEntry.objects.create(user=self.user, tier=level, title="Se queda sin nivel", order=1)

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
    """El tablón es personal de cada usuario (antes era único y
    compartido/anónimo); se puede compartir con amigos concretos vía
    `PhotoBoardMember`."""

    def setUp(self):
        self.user = User.objects.create(email="tablon@test.local", role=User.Role.LECTOR, username="dueno_tablon")
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

    def test_requiere_haber_entrado_al_maletin(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:photo-board"))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_requiere_login(self):
        anon_client = self.client_class()
        anon_client.post(reverse("secret:gate"), {"code": "8888"})
        response = anon_client.get(reverse("secret:photo-board"))
        self.assertIn("/cuenta/login/", response.url)

    def test_la_pagina_del_tablon_separa_gestionar_acceso_de_las_fotos_y_no_lleva_el_formulario_de_subir(self):
        # Antes el formulario de subir vivía mezclado aquí mismo con
        # "gestionar acceso" y la cuadrícula de fotos — ahora subir es su
        # propia pantalla (ver photo_board_upload.html), enlazada con un
        # botón, y aquí solo quedan "Gestionar acceso" y "Las fotos".
        response = self.client.get(reverse("secret:photo-board"))
        self.assertContains(response, "Gestionar acceso")
        self.assertContains(response, "Las fotos")
        self.assertContains(response, reverse("secret:photo-board-upload"))
        self.assertNotContains(response, 'enctype="multipart/form-data"')

    def test_la_pagina_de_subir_tiene_el_formulario(self):
        response = self.client.get(reverse("secret:photo-board-upload"))
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, "Subir foto")

    def test_subir_foto_a_tu_propio_tablon(self):
        response = self.client.post(reverse("secret:photo-board-upload"), {
            "image": _fake_image(), "description": "Mi foto",
        })
        self.assertRedirects(response, reverse("secret:photo-board"))
        photo = SecretPhoto.objects.get()
        self.assertEqual(photo.board_owner, self.user)
        self.assertEqual(photo.uploaded_by, self.user)

    def test_listado_muestra_las_fotos_subidas(self):
        SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=self.user, image=_fake_image(), description="Foto de prueba",
        )
        response = self.client.get(reverse("secret:photo-board"))
        self.assertContains(response, "Foto de prueba")

    def test_sin_imagen_no_crea_la_foto(self):
        response = self.client.post(reverse("secret:photo-board-upload"), {"description": "Sin imagen"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SecretPhoto.objects.exists())

    def test_no_ves_el_tablon_de_otro_sin_invitacion(self):
        other = User.objects.create(email="otro_tablon@test.local", role=User.Role.LECTOR, username="otro_tablon")
        SecretPhoto.objects.create(board_owner=other, uploaded_by=other, image=_fake_image(), description="Ajena")

        response = self.client.get(reverse("secret:photo-board-shared", args=[other.username]))
        self.assertEqual(response.status_code, 404)

    def test_invitar_a_un_amigo_le_da_acceso(self):
        friend = User.objects.create(email="amigo_tablon@test.local", role=User.Role.LECTOR, username="amigo")
        FriendRequest.objects.create(from_user=self.user, to_user=friend, accepted=True)

        response = self.client.post(reverse("secret:photo-board-invite", args=[friend.username]))
        self.assertRedirects(response, reverse("secret:photo-board"))
        self.assertTrue(PhotoBoardMember.objects.filter(owner=self.user, member=friend).exists())

    def test_no_se_puede_invitar_a_quien_no_es_amigo(self):
        stranger = User.objects.create(email="desconocido@test.local", role=User.Role.LECTOR, username="desconocido")
        self.client.post(reverse("secret:photo-board-invite", args=[stranger.username]))
        self.assertFalse(PhotoBoardMember.objects.filter(owner=self.user, member=stranger).exists())

    def test_un_invitado_puede_ver_y_subir_al_tablon_compartido(self):
        friend = User.objects.create(email="amigo2_tablon@test.local", role=User.Role.LECTOR, username="amigo2")
        friend.set_password("Testpass123!")
        friend.save()
        PhotoBoardMember.objects.create(owner=self.user, member=friend)

        friend_client = self.client_class()
        friend_client.login(username=friend.email, password="Testpass123!")
        friend_client.post(reverse("secret:gate"), {"code": "8888"})

        response = friend_client.post(reverse("secret:photo-board-upload-shared", args=[self.user.username]), {
            "image": _fake_image(), "description": "Del invitado",
        })
        self.assertRedirects(response, reverse("secret:photo-board-shared", args=[self.user.username]))
        photo = SecretPhoto.objects.get()
        self.assertEqual(photo.board_owner, self.user)
        self.assertEqual(photo.uploaded_by, friend)

    def test_expulsar_quita_el_acceso(self):
        friend = User.objects.create(email="amigo3_tablon@test.local", role=User.Role.LECTOR, username="amigo3")
        member = PhotoBoardMember.objects.create(owner=self.user, member=friend)

        response = self.client.post(reverse("secret:photo-board-kick", args=[member.pk]))
        self.assertRedirects(response, reverse("secret:photo-board"))
        self.assertFalse(PhotoBoardMember.objects.filter(pk=member.pk).exists())

    def test_no_puedes_expulsar_de_un_tablon_ajeno(self):
        owner = User.objects.create(email="dueno_ajeno@test.local", role=User.Role.LECTOR, username="dueno_ajeno")
        member = PhotoBoardMember.objects.create(owner=owner, member=self.user)

        response = self.client.post(reverse("secret:photo-board-kick", args=[member.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(PhotoBoardMember.objects.filter(pk=member.pk).exists())

    def test_puedes_editar_la_descripcion_de_tu_propia_foto(self):
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=self.user, image=_fake_image(), description="Antes",
        )
        response = self.client.post(reverse("secret:photo-board-edit", args=[photo.pk]), {"description": "Después"})
        self.assertRedirects(response, reverse("secret:photo-board"))
        photo.refresh_from_db()
        self.assertEqual(photo.description, "Después")

    def test_no_puedes_editar_una_foto_que_no_subiste_tu(self):
        friend = User.objects.create(email="amigo4_tablon@test.local", role=User.Role.LECTOR, username="amigo4")
        PhotoBoardMember.objects.create(owner=self.user, member=friend)
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=friend, image=_fake_image(), description="Del invitado",
        )
        response = self.client.post(reverse("secret:photo-board-edit", args=[photo.pk]), {"description": "Cambiada"})
        self.assertEqual(response.status_code, 404)
        photo.refresh_from_db()
        self.assertEqual(photo.description, "Del invitado")

    def test_la_pagina_de_editar_tiene_el_formulario_y_la_foto_actual(self):
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=self.user, image=_fake_image(), description="Actual",
        )
        response = self.client.get(reverse("secret:photo-board-edit", args=[photo.pk]))
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, "Actual")
        self.assertContains(response, reverse("secret:photo-serve", args=[photo.pk]))

    def test_editar_puede_resubir_la_imagen_ademas_de_la_descripcion(self):
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=self.user, image=_fake_image(), description="Antes",
        )
        old_name = photo.image.name
        response = self.client.post(reverse("secret:photo-board-edit", args=[photo.pk]), {
            "image": _fake_image(), "description": "Después",
        })
        self.assertRedirects(response, reverse("secret:photo-board"))
        photo.refresh_from_db()
        self.assertEqual(photo.description, "Después")
        self.assertNotEqual(photo.image.name, old_name)

    def test_no_puedes_ver_la_pagina_de_editar_de_una_foto_ajena(self):
        friend = User.objects.create(email="amigo7_tablon@test.local", role=User.Role.LECTOR, username="amigo7")
        PhotoBoardMember.objects.create(owner=self.user, member=friend)
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=friend, image=_fake_image(), description="Del invitado",
        )
        response = self.client.get(reverse("secret:photo-board-edit", args=[photo.pk]))
        self.assertEqual(response.status_code, 404)

    def test_puedes_borrar_tu_propia_foto(self):
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=self.user, image=_fake_image(), description="A borrar",
        )
        response = self.client.post(reverse("secret:photo-board-delete", args=[photo.pk]))
        self.assertRedirects(response, reverse("secret:photo-board"))
        self.assertFalse(SecretPhoto.objects.filter(pk=photo.pk).exists())

    def test_no_puedes_borrar_una_foto_que_no_subiste_tu(self):
        friend = User.objects.create(email="amigo5_tablon@test.local", role=User.Role.LECTOR, username="amigo5")
        PhotoBoardMember.objects.create(owner=self.user, member=friend)
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=friend, image=_fake_image(), description="Del invitado",
        )
        response = self.client.post(reverse("secret:photo-board-delete", args=[photo.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(SecretPhoto.objects.filter(pk=photo.pk).exists())

    def test_borrar_desde_un_tablon_compartido_vuelve_al_tablon_compartido(self):
        friend = User.objects.create(email="amigo6_tablon@test.local", role=User.Role.LECTOR, username="amigo6")
        friend.set_password("Testpass123!")
        friend.save()
        PhotoBoardMember.objects.create(owner=self.user, member=friend)
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=friend, image=_fake_image(), description="Del invitado",
        )

        friend_client = self.client_class()
        friend_client.login(username=friend.email, password="Testpass123!")
        friend_client.post(reverse("secret:gate"), {"code": "8888"})

        response = friend_client.post(reverse("secret:photo-board-delete", args=[photo.pk]))
        self.assertRedirects(response, reverse("secret:photo-board-shared", args=[self.user.username]))
        self.assertFalse(SecretPhoto.objects.filter(pk=photo.pk).exists())

    def test_la_pagina_del_tablon_enlaza_a_la_vista_protegida_no_a_la_url_del_storage(self):
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=self.user, image=_fake_image(), description="Protegida",
        )
        response = self.client.get(reverse("secret:photo-board"))
        self.assertContains(response, reverse("secret:photo-serve", args=[photo.pk]))
        self.assertNotContains(response, photo.image.url)

    def test_photo_serve_devuelve_la_imagen_al_dueno(self):
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=self.user, image=_fake_image(), description="Mía",
        )
        response = self.client.get(reverse("secret:photo-serve", args=[photo.pk]))
        self.assertEqual(response.status_code, 200)

    def test_photo_serve_exige_el_codigo(self):
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=self.user, image=_fake_image(), description="Mía",
        )
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:photo-serve", args=[photo.pk]))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_photo_serve_da_404_sin_acceso_al_tablon(self):
        other = User.objects.create(email="ajeno_foto@test.local", role=User.Role.LECTOR, username="ajeno_foto")
        photo = SecretPhoto.objects.create(
            board_owner=other, uploaded_by=other, image=_fake_image(), description="Ajena",
        )
        response = self.client.get(reverse("secret:photo-serve", args=[photo.pk]))
        self.assertEqual(response.status_code, 404)

    def test_photo_serve_accesible_para_invitado(self):
        friend = User.objects.create(email="invitado_foto@test.local", role=User.Role.LECTOR, username="invitado_foto")
        friend.set_password("Testpass123!")
        friend.save()
        PhotoBoardMember.objects.create(owner=self.user, member=friend)
        photo = SecretPhoto.objects.create(
            board_owner=self.user, uploaded_by=self.user, image=_fake_image(), description="Compartida",
        )

        friend_client = self.client_class()
        friend_client.login(username=friend.email, password="Testpass123!")
        friend_client.post(reverse("secret:gate"), {"code": "8888"})
        response = friend_client.get(reverse("secret:photo-serve", args=[photo.pk]))
        self.assertEqual(response.status_code, 200)


class CalendarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="calendario@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.movie = Movie.objects.create(tmdb_id=1, title="Estreno de prueba", media_type="movie")

    def test_requiere_haber_entrado_al_maletin(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:calendar"))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_requiere_login(self):
        # self.client.logout() también borraría el código ya desbloqueado
        # (Django vacía toda la sesión), así que probamos con un cliente
        # nuevo que solo ha metido el código, sin haber iniciado sesión.
        anon_client = self.client_class()
        anon_client.post(reverse("secret:gate"), {"code": "8888"})
        response = anon_client.get(reverse("secret:calendar"))
        self.assertIn("/cuenta/login/", response.url)

    def test_el_input_de_buscar_manda_el_valor_como_query(self):
        # Regresión: sin name="query" en el <input>, HTMX nunca manda lo
        # escrito y el desplegable de resultados no aparece nunca, aunque
        # la búsqueda "funcione" (con query siempre vacía).
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        self.assertContains(response, 'name="query"')

    def test_compartir_devuelve_una_imagen_png(self):
        ReleaseEvent.objects.create(user=self.user, movie=self.movie, date=date(2026, 3, 15))
        response = self.client.get(reverse("secret:calendar-share-image"), {"year": 2026, "month": 3})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("calendario_2026_03.png", response["Content-Disposition"])
        # Cabecera PNG real, no basta con el content-type de la respuesta.
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_compartir_requiere_haber_entrado_al_maletin(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:calendar-share-image"))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_compartir_con_mes_invalido_da_404(self):
        response = self.client.get(reverse("secret:calendar-share-image"), {"year": 2026, "month": 13})
        self.assertEqual(response.status_code, 404)

    def test_compartir_con_titulo_en_caracteres_no_latinos_no_rompe(self):
        # Regresión: la fuente que usa la imagen no tiene glifos para
        # japonés/coreano/etc. y antes de este fix salían como cuadros
        # ilegibles; ahora se descartan y, si no queda nada legible, se
        # usa un texto de repuesto.
        anime = Movie.objects.create(tmdb_id=2, title="君の名は。", media_type="movie")
        ReleaseEvent.objects.create(user=self.user, movie=anime, date=date(2026, 3, 15))
        response = self.client.get(reverse("secret:calendar-share-image"), {"year": 2026, "month": 3})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_muestra_eventos_del_mes_pedido(self):
        event = ReleaseEvent.objects.create(user=self.user, movie=self.movie, date=date(2026, 3, 15), note="Estreno")
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        self.assertEqual(response.status_code, 200)
        all_events = [e for week in response.context["weeks"] for day in week for e in day["events"]]
        self.assertEqual(all_events, [event])

    def test_muestra_la_portada_y_el_titulo_del_evento(self):
        movie = Movie.objects.create(tmdb_id=99, title="Con portada", media_type="movie", poster_path="/abc.jpg")
        ReleaseEvent.objects.create(user=self.user, movie=movie, date=date(2026, 3, 15))
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        self.assertContains(response, "Con portada")
        self.assertContains(response, movie.poster_url)

    def test_no_muestra_eventos_de_otro_mes(self):
        ReleaseEvent.objects.create(user=self.user, movie=self.movie, date=date(2026, 4, 1))
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        all_events = [e for week in response.context["weeks"] for day in week for e in day["events"]]
        self.assertEqual(all_events, [])

    def test_no_muestra_eventos_de_otro_usuario(self):
        other = User.objects.create(email="otro_calendario@test.local", role=User.Role.LECTOR)
        ReleaseEvent.objects.create(user=other, movie=self.movie, date=date(2026, 3, 15))
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        all_events = [e for week in response.context["weeks"] for day in week for e in day["events"]]
        self.assertEqual(all_events, [])

    def test_mes_o_year_invalido_da_404(self):
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 13})
        self.assertEqual(response.status_code, 404)

    def test_mover_evento_a_otra_fecha(self):
        event = ReleaseEvent.objects.create(user=self.user, movie=self.movie, date=date(2026, 3, 15))
        response = self.client.post(reverse("secret:calendar-move", args=[event.pk]), {"date": "2026-03-20"})
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.date, date(2026, 3, 20))

    def test_mover_con_fecha_invalida_no_cambia_nada(self):
        event = ReleaseEvent.objects.create(user=self.user, movie=self.movie, date=date(2026, 3, 15))
        self.client.post(reverse("secret:calendar-move", args=[event.pk]), {"date": "no-es-una-fecha"})
        event.refresh_from_db()
        self.assertEqual(event.date, date(2026, 3, 15))

    def test_no_se_puede_mover_un_evento_ajeno(self):
        other = User.objects.create(email="otro_mover@test.local", role=User.Role.LECTOR)
        event = ReleaseEvent.objects.create(user=other, movie=self.movie, date=date(2026, 3, 15))
        response = self.client.post(reverse("secret:calendar-move", args=[event.pk]), {"date": "2026-03-20"})
        self.assertEqual(response.status_code, 404)
        event.refresh_from_db()
        self.assertEqual(event.date, date(2026, 3, 15))

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
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.date, date(2026, 3, 15))
        mock_get_or_create.assert_called_once_with(1, media_type="movie")

    def test_anadir_con_fecha_invalida_no_crea_nada(self):
        response = self.client.post(reverse("secret:calendar-add", args=["movie", 1]), {"date": "no-es-una-fecha"})
        self.assertRedirects(response, reverse("secret:calendar"))
        self.assertFalse(ReleaseEvent.objects.exists())

    def test_quitar_borra_el_evento(self):
        event = ReleaseEvent.objects.create(user=self.user, movie=self.movie, date=date(2026, 3, 15))
        response = self.client.post(reverse("secret:calendar-remove", args=[event.pk]))
        self.assertRedirects(response, reverse("secret:calendar") + "?year=2026&month=3")
        self.assertFalse(ReleaseEvent.objects.filter(pk=event.pk).exists())

    def test_no_se_puede_quitar_un_evento_ajeno(self):
        other = User.objects.create(email="otro_quitar@test.local", role=User.Role.LECTOR)
        event = ReleaseEvent.objects.create(user=other, movie=self.movie, date=date(2026, 3, 15))
        response = self.client.post(reverse("secret:calendar-remove", args=[event.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ReleaseEvent.objects.filter(pk=event.pk).exists())

    def test_guardar_comentario_de_un_dia(self):
        response = self.client.post(reverse("secret:calendar-day-note"), {"date": "2026-03-15", "note": "Vacaciones"})
        self.assertRedirects(response, reverse("secret:calendar") + "?year=2026&month=3")
        note = CalendarDayNote.objects.get(user=self.user, date=date(2026, 3, 15))
        self.assertEqual(note.note, "Vacaciones")

    def test_el_calendario_muestra_el_comentario_del_dia(self):
        CalendarDayNote.objects.create(user=self.user, date=date(2026, 3, 15), note="Vacaciones")
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        self.assertContains(response, "Vacaciones")

    def test_no_muestra_el_comentario_de_otro_usuario(self):
        other = User.objects.create(email="otro_nota@test.local", role=User.Role.LECTOR)
        CalendarDayNote.objects.create(user=other, date=date(2026, 3, 15), note="Ajeno")
        response = self.client.get(reverse("secret:calendar"), {"year": 2026, "month": 3})
        self.assertNotContains(response, "Ajeno")

    def test_editar_un_comentario_existente_lo_sobreescribe(self):
        CalendarDayNote.objects.create(user=self.user, date=date(2026, 3, 15), note="Antiguo")
        self.client.post(reverse("secret:calendar-day-note"), {"date": "2026-03-15", "note": "Nuevo"})
        self.assertEqual(CalendarDayNote.objects.count(), 1)
        self.assertEqual(CalendarDayNote.objects.get().note, "Nuevo")

    def test_guardar_nota_vacia_borra_el_comentario(self):
        CalendarDayNote.objects.create(user=self.user, date=date(2026, 3, 15), note="Algo")
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
        self.user = User.objects.create(email="calendario_google@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.movie = Movie.objects.create(tmdb_id=1, title="Estreno de prueba", media_type="movie")

    @patch("apps.secret.views.google_create_event")
    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_anadir_evento_lo_crea_en_tu_google_calendar_si_esta_conectado(self, mock_get_or_create, mock_create_event):
        mock_get_or_create.return_value = self.movie
        mock_create_event.return_value = "google-event-id-1"
        GoogleCalendarConnection.objects.create(user=self.user, refresh_token="r")

        self.client.post(reverse("secret:calendar-add", args=["movie", 1]), {"date": "2026-03-15"})

        mock_create_event.assert_called_once()
        event = ReleaseEvent.objects.get()
        self.assertEqual(event.google_event_id, "google-event-id-1")

    @patch("apps.secret.views.google_create_event")
    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_sin_conectar_no_llama_a_google(self, mock_get_or_create, mock_create_event):
        mock_get_or_create.return_value = self.movie
        self.client.post(reverse("secret:calendar-add", args=["movie", 1]), {"date": "2026-03-15"})
        mock_create_event.assert_not_called()
        event = ReleaseEvent.objects.get()
        self.assertEqual(event.google_event_id, "")

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="", GOOGLE_OAUTH_CLIENT_SECRET="")
    @patch("apps.secret.views.google_create_event")
    @patch("apps.secret.views.Movie.get_or_create_from_tmdb")
    def test_sin_credenciales_de_google_no_llama_a_la_api(self, mock_get_or_create, mock_create_event):
        mock_get_or_create.return_value = self.movie
        GoogleCalendarConnection.objects.create(user=self.user, refresh_token="r")

        self.client.post(reverse("secret:calendar-add", args=["movie", 1]), {"date": "2026-03-15"})

        mock_create_event.assert_not_called()

    @patch("apps.secret.views.google_delete_event")
    def test_quitar_evento_lo_borra_de_tu_google_calendar(self, mock_delete_event):
        GoogleCalendarConnection.objects.create(user=self.user, refresh_token="r")
        event = ReleaseEvent.objects.create(user=self.user, movie=self.movie, date=date(2026, 3, 15), google_event_id="g1")

        self.client.post(reverse("secret:calendar-remove", args=[event.pk]))

        mock_delete_event.assert_called_once()
        self.assertEqual(mock_delete_event.call_args.args[1], "g1")

    @patch("apps.secret.views.google_delete_event")
    def test_quitar_evento_sin_conectar_no_llama_a_google(self, mock_delete_event):
        event = ReleaseEvent.objects.create(user=self.user, movie=self.movie, date=date(2026, 3, 15))

        response = self.client.post(reverse("secret:calendar-remove", args=[event.pk]))

        self.assertEqual(response.status_code, 302)
        mock_delete_event.assert_not_called()


class ShareableFriendsExcludesContactBotTests(TestCase):
    """El Buzón de contacto os hace "amigos" en cuanto alguien escribe por
    Escríbenos (ver `ensure_friends`), pero no es una persona con la que
    compartir listas/tablón/calendario -- no debe aparecer en ningún
    "invitar a..." de Top Secret."""

    def setUp(self):
        self.user = User.objects.create(email="sin_buzon@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

    def test_el_buzon_no_sale_como_invitable_en_lista_propia(self):
        bot = get_contact_bot_user()
        ensure_friends(self.user, bot)
        real_friend = User.objects.create(email="amigo_de_verdad@test.local", role=User.Role.LECTOR, username="amigo_de_verdad")
        FriendRequest.objects.create(from_user=self.user, to_user=real_friend, accepted=True)

        response = self.client.get(reverse("secret:own-list-share"))

        invitable = list(response.context["invitable_friends"])
        self.assertNotIn(bot, invitable)
        self.assertIn(real_friend, invitable)


class SavedMoviesInTopSecretTests(TestCase):
    """Guardados dentro del maletín: mismos datos que Guardadas en
    Películas, pero sin salir de Top Secret ni al listarlas ni al actuar
    sobre ellas (crear/borrar listas, mover, quitar)."""

    def setUp(self):
        self.user = User.objects.create(email="guardados_ts@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.movie = Movie.objects.create(tmdb_id=1, title="Guardada de prueba", media_type="movie")
        self.saved = SavedMovie.objects.create(user=self.user, movie=self.movie)

    def test_lista_las_guardadas_dentro_del_maletin(self):
        response = self.client.get(reverse("secret:saved-movies"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Guardada de prueba")
        self.assertContains(response, "Top Secret")

    def test_quitar_una_guardada_no_saca_del_maletin(self):
        response = self.client.post(
            reverse("movies:saved-movie-remove", args=[self.saved.pk]),
            {"next": reverse("secret:saved-movies")},
        )
        self.assertRedirects(response, reverse("secret:saved-movies"))
        self.assertFalse(SavedMovie.objects.filter(pk=self.saved.pk).exists())

    def test_sin_next_la_accion_vuelve_a_guardadas_de_peliculas(self):
        response = self.client.post(reverse("movies:saved-movie-remove", args=[self.saved.pk]))
        self.assertRedirects(response, reverse("movies:saved-movies"))



class AmigosHubTests(TestCase):
    """Amigos (antes "Compartidos"): a la izquierda quién te comparte
    algo, a la derecha un adelanto de su Lista/Tablón/Calendario con
    pestañas internas -- sin salir de la página para ver a cada amigo."""

    def setUp(self):
        self.user = User.objects.create(email="amigos_hub@test.local", role=User.Role.LECTOR, username="yo_amigos")
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

        self.marta = User.objects.create(email="marta_amigos@test.local", role=User.Role.LECTOR, username="marta")
        self.alex = User.objects.create(email="alex_amigos@test.local", role=User.Role.LECTOR, username="alex")
        for friend in (self.marta, self.alex):
            FriendRequest.objects.create(from_user=self.user, to_user=friend, accepted=True)

    def test_sin_nadie_compartiendo_te_avisa(self):
        response = self.client.get(reverse("secret:shared-hub"))
        self.assertContains(response, "Todavía nadie te ha compartido nada")

    def test_amigo_con_lista_compartida_aparece_y_se_previsualiza(self):
        SecretListMember.objects.create(owner=self.marta, member=self.user)
        SecretMovie.objects.create(owner=self.marta, title="La de Marta", personal_rating="8.0")

        response = self.client.get(reverse("secret:shared-hub"))
        self.assertContains(response, "marta")
        self.assertContains(response, "La de Marta")
        self.assertEqual(response.context["selected_tab"], "lista")
        self.assertEqual(response.context["selected_row"]["owner"], self.marta)

    def test_elegir_amigo_por_query_param_cambia_la_previsualizacion(self):
        SecretListMember.objects.create(owner=self.marta, member=self.user)
        SecretListMember.objects.create(owner=self.alex, member=self.user)
        SecretMovie.objects.create(owner=self.marta, title="Solo de Marta", personal_rating="8.0")
        SecretMovie.objects.create(owner=self.alex, title="Solo de Alex", personal_rating="7.0")

        response = self.client.get(reverse("secret:shared-hub"), {"friend": "alex"})
        self.assertEqual(response.context["selected_row"]["owner"], self.alex)
        self.assertContains(response, "Solo de Alex")
        self.assertNotContains(response, "Solo de Marta")

    def test_amigo_sin_lista_compartida_pero_con_tablon_cae_en_tablon(self):
        PhotoBoardMember.objects.create(owner=self.marta, member=self.user)
        response = self.client.get(reverse("secret:shared-hub"))
        self.assertEqual(response.context["selected_tab"], "tablon")

    def test_no_se_puede_forzar_ver_a_alguien_que_no_te_comparte_nada(self):
        # `alex` no comparte nada contigo -- pedirlo explícitamente por la
        # URL no debe colar su contenido de matute.
        SecretListMember.objects.create(owner=self.marta, member=self.user)
        SecretMovie.objects.create(owner=self.alex, title="Privada de Alex", personal_rating="9.0")

        response = self.client.get(reverse("secret:shared-hub"), {"friend": "alex"})
        self.assertIsNone(response.context["selected_row"])
        self.assertNotContains(response, "Privada de Alex")

    def test_calendario_solo_ensena_estrenos_futuros(self):
        CalendarShareMember.objects.create(owner=self.marta, member=self.user)
        movie = Movie.objects.create(tmdb_id=1, title="Estreno", media_type="movie")
        from datetime import timedelta

        pasado = ReleaseEvent.objects.create(user=self.marta, movie=movie, date=date.today() - timedelta(days=5))
        futuro = ReleaseEvent.objects.create(user=self.marta, movie=movie, date=date.today() + timedelta(days=5))

        response = self.client.get(reverse("secret:shared-hub"), {"friend": "marta", "tab": "calendario"})
        preview_ids = [e.pk for e in response.context["preview"]]
        self.assertIn(futuro.pk, preview_ids)
        self.assertNotIn(pasado.pk, preview_ids)

    def test_peticion_htmx_normal_devuelve_solo_el_fragmento(self):
        SecretListMember.objects.create(owner=self.marta, member=self.user)
        response = self.client.get(reverse("secret:shared-hub"), {"friend": "marta"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, 'id="amigos-panel"')
        self.assertNotContains(response, "ts-rail__brand")

    def test_peticion_htmx_de_navegacion_del_maletin_devuelve_la_pagina_entera(self):
        response = self.client.get(reverse("secret:shared-hub"), HTTP_HX_REQUEST="true", HTTP_HX_SHELL_NAV="1")
        self.assertContains(response, "ts-rail__brand")

    def test_cambiar_de_amigo_por_htmx_actualiza_el_resaltado_de_la_lista(self):
        # El swap de HTMX repinta #amigos-panel entero (lista + panel a la
        # derecha), no solo el panel -- si solo repintase el panel, la fila
        # resaltada de la izquierda se quedaría marcando al amigo anterior.
        import re

        SecretListMember.objects.create(owner=self.marta, member=self.user)
        CalendarShareMember.objects.create(owner=self.alex, member=self.user)

        response = self.client.get(reverse("secret:shared-hub"), {"friend": "alex"}, HTTP_HX_REQUEST="true")
        content = response.content.decode()

        def friend_row_html(username):
            match = re.search(rf'<a href="\?friend={username}"[^>]*>.*?</a>', content, re.DOTALL)
            self.assertIsNotNone(match, f"no se encontró la fila de {username}")
            return match.group(0)

        self.assertIn("is-selected", friend_row_html("alex"))
        self.assertNotIn("is-selected", friend_row_html("marta"))

    def test_gestion_de_a_quien_compartes_sigue_disponible(self):
        response = self.client.get(reverse("secret:shared-hub"))
        self.assertContains(response, "Con quién compartes")
        self.assertContains(response, "marta")


class TopSecretTabOrderTests(TestCase):
    """Orden de las pestañas de arriba del maletín (TopSecretTab,
    reordenable arrastrando desde el admin) -- ver
    templates/secret/_shell.html y secret_extras.topsecret_tab_order."""

    def setUp(self):
        self.user = User.objects.create(email="tab_order@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

    def test_sin_filas_sembradas_usa_el_orden_por_defecto(self):
        # La migración de datos siembra las 6 filas, pero ordered_keys()
        # no debe reventar ni perder pestañas si por lo que sea faltan.
        TopSecretTab.objects.all().delete()
        self.assertEqual(
            TopSecretTab.ordered_keys(),
            ["lista", "calendario", "tablon", "buscar", "amigos", "guardados"],
        )

    def test_reordenar_desde_el_admin_cambia_el_orden_de_la_barra(self):
        TopSecretTab.objects.filter(key="lista").update(order=10)
        TopSecretTab.objects.filter(key="buscar").update(order=0)

        response = self.client.get(reverse("secret:list"))
        content = response.content.decode()
        pos_buscar = content.index(">Buscar<")
        pos_lista = content.index(">Lista<")
        self.assertLess(pos_buscar, pos_lista)

    def test_una_pestana_nueva_sin_fila_todavia_no_desaparece(self):
        TopSecretTab.objects.filter(key="guardados").delete()
        self.assertIn("guardados", TopSecretTab.ordered_keys())

    def test_reordenar_no_hace_salir_amigos_ni_guardados_sin_login(self):
        # Sin sesión iniciada, esas dos pestañas siguen sin salir en la
        # barra pase lo que pase con el orden (ver _shell.html). logout()
        # vacía también la sesión del maletín (secret_required la exige
        # aparte del login), así que hay que volver a abrirlo.
        self.client.logout()
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        response = self.client.get(f"{reverse('secret:list')}?scope=bygui")
        self.assertNotContains(response, ">Amigos<")
        self.assertNotContains(response, ">Guardados<")


class CompareWithFriendsTests(TestCase):
    """Comparar con amigos (por_number/by_rating): "Tú" ya va siempre
    incluido en la comparación sin marcarlo a mano (antes era una
    casilla más, redundante -- comparar sin uno mismo no tenía mucho
    sentido). lasaladebygui (owner=None) no se ofrece como opción
    aparte para el propio Admin, porque su "Tú" ya ES esa misma lista."""

    def setUp(self):
        self.user = User.objects.create(email="compare_friends@test.local", role=User.Role.LECTOR, username="yo_comparo")
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

        self.friend = User.objects.create(email="compare_friend2@test.local", role=User.Role.LECTOR, username="mi_amigo")
        FriendRequest.objects.create(from_user=self.user, to_user=self.friend, accepted=True)
        SecretListMember.objects.create(owner=self.friend, member=self.user)

        SecretMovie.objects.create(owner=self.user, title="La mía", personal_rating="8.0")
        SecretMovie.objects.create(owner=self.friend, title="La de mi amigo", personal_rating="7.0")

    def test_tu_sale_siempre_incluido_sin_marcarlo(self):
        SecretMovie.objects.filter(owner=self.user).update(number=1)
        SecretMovie.objects.filter(owner=self.friend).update(number=1)

        response = self.client.get(reverse("secret:by-number"), {
            "number": 1, "compare": "1", "with": ["mi_amigo"],
        })
        labels = [row["label"] for row in response.context["rows"]]
        self.assertEqual(labels[0], "Tú")
        self.assertIn("mi_amigo", labels)

    def test_lasaladebygui_no_sale_como_opcion_para_el_propio_admin(self):
        admin = User.objects.create(email="compare_admin@test.local", role=User.Role.ADMIN)
        admin.set_password("Testpass123!")
        admin.save()
        # login() con un usuario distinto al de setUp vacía la sesión
        # (previene fijación de sesión) y con ella el código del maletín.
        self.client.login(username=admin.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

        response = self.client.get(reverse("secret:by-number"), {"number": 1})
        keys = [key for key, label, o in response.context["comparable_owners"]]
        self.assertNotIn("bygui", keys)

    def test_lasaladebygui_si_sale_como_opcion_para_un_usuario_normal(self):
        response = self.client.get(reverse("secret:by-number"), {"number": 1})
        labels = [label for key, label, o in response.context["comparable_owners"]]
        self.assertIn("lasaladebygui", labels)

    def test_boton_todos_aparece_cuando_hay_con_quien_comparar(self):
        response = self.client.get(reverse("secret:by-number"), {"number": 1})
        self.assertContains(response, 'class="compare-picker__all"')

    def test_mas_de_tres_comparados_usa_layout_de_lista(self):
        SecretMovie.objects.filter(owner=self.user).update(number=1)
        SecretMovie.objects.filter(owner=self.friend).update(number=1)
        other_friends = []
        for i in range(3):
            f = User.objects.create(email=f"compare_extra{i}@test.local", role=User.Role.LECTOR, username=f"extra{i}")
            FriendRequest.objects.create(from_user=self.user, to_user=f, accepted=True)
            SecretListMember.objects.create(owner=f, member=self.user)
            SecretMovie.objects.create(owner=f, title=f"Extra {i}", personal_rating="6.0", number=1)
            other_friends.append(f.username)

        response = self.client.get(reverse("secret:by-number"), {
            "number": 1, "compare": "1", "with": ["mi_amigo"] + other_friends,
        })
        self.assertGreater(len(response.context["rows"]), 3)
        self.assertContains(response, "compare-grid--list")

    def test_hasta_tres_comparados_no_usa_layout_de_lista(self):
        SecretMovie.objects.filter(owner=self.user).update(number=1)
        SecretMovie.objects.filter(owner=self.friend).update(number=1)

        response = self.client.get(reverse("secret:by-number"), {
            "number": 1, "compare": "1", "with": ["mi_amigo"],
        })
        self.assertLessEqual(len(response.context["rows"]), 3)
        self.assertNotContains(response, "compare-grid--list")

    def test_by_rating_tambien_incluye_tu_siempre(self):
        SecretMovie.objects.filter(owner=self.user).update(personal_rating="8.0")
        SecretMovie.objects.filter(owner=self.friend).update(personal_rating="7.0")

        response = self.client.get(reverse("secret:by-rating"), {
            "min_rating": 1, "max_rating": 10, "compare": "1", "with": ["mi_amigo"],
        })
        labels = [row["label"] for row in response.context["rows"]]
        self.assertEqual(labels[0], "Tú")
