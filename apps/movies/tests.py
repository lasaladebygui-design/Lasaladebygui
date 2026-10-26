import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User

from .models import Movie, RouletteRatingSeen, RouletteSavedSeen, SavedMovie, SavedMovieList, Vote
from .services import MovieAPIError, omdb_get_imdb_rating, tmdb_search_person


def make_user(email):
    user = User(email=email, role=User.Role.LECTOR)
    user.set_password("Testpass123!")
    user.save()
    return user


def make_movie(tmdb_id, title, imdb_rating):
    return Movie.objects.create(tmdb_id=tmdb_id, title=title, imdb_rating=imdb_rating)


class TmdbSearchPersonTests(TestCase):
    """tmdb_search_person: para la foto de perfil de un actor/actriz, usada
    en 'Cuál tiene al actor/actriz' y en el resultado de 'Qué personaje
    eres' (foto de quien interpretó al personaje)."""

    @override_settings(TMDB_API_KEY="fake-tmdb-key")
    @patch("requests.get")
    def test_devuelve_nombre_y_foto_de_perfil(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "results": [{"id": 42, "name": "Actor Ejemplo", "profile_path": "/foto.jpg"}],
        }
        results = tmdb_search_person("Actor Ejemplo")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tmdb_id, 42)
        self.assertEqual(results[0].name, "Actor Ejemplo")
        self.assertIn("/foto.jpg", results[0].profile_url)

    @override_settings(TMDB_API_KEY="fake-tmdb-key")
    @patch("requests.get")
    def test_sin_foto_de_perfil_devuelve_url_vacia(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {
            "results": [{"id": 43, "name": "Sin foto", "profile_path": None}],
        }
        results = tmdb_search_person("Sin foto")
        self.assertEqual(results[0].profile_url, "")

    @override_settings(TMDB_API_KEY="fake-tmdb-key")
    @patch("requests.get")
    def test_fallo_de_red_lanza_movieapierror(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("boom")
        with self.assertRaises(MovieAPIError):
            tmdb_search_person("lo que sea")


class OmdbGetImdbRatingTests(TestCase):
    """omdb_get_imdb_rating es un dato complementario (ver
    Movie.get_or_create_from_tmdb) -- que OMDb esté caído, sin cuota o sin
    clave configurada nunca debe romper el añadir una película/serie a
    Top Secret, así que aquí solo debe devolver None, no MovieAPIError."""

    @override_settings(OMDB_API_KEY="fake-omdb-key")
    @patch("requests.get")
    def test_fallo_de_red_devuelve_none_en_vez_de_lanzar(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("boom")
        self.assertIsNone(omdb_get_imdb_rating("tt0000001"))

    @override_settings(OMDB_API_KEY="fake-omdb-key")
    @patch("requests.get")
    def test_nota_disponible_se_devuelve_como_float(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {"imdbRating": "7.8"}
        self.assertEqual(omdb_get_imdb_rating("tt0000001"), 7.8)


class GetOrCreateFromTmdbTests(TestCase):
    """Un fallo de OMDb al resolver la nota IMDb no debe impedir dar de
    alta la película/serie -- solo un fallo de TMDb (los datos de
    verdad) debe hacerlo. Repro del bug reportado: "al añadir película le
    das pero no te lleva al sitio donde rellenar la ficha"."""

    def _fake_tmdb_get(self, url, params=None, timeout=None):
        response = type("Resp", (), {})()
        response.raise_for_status = lambda: None
        if "themoviedb.org" in url:
            response.json = lambda: {
                "title": "Vengadores", "release_date": "2012-05-04",
                "poster_path": "/x.jpg", "overview": "x",
                "external_ids": {"imdb_id": "tt0000001"},
            }
        else:
            raise AssertionError(f"URL inesperada: {url}")
        return response

    @override_settings(TMDB_API_KEY="fake-tmdb-key", OMDB_API_KEY="fake-omdb-key")
    @patch("requests.get")
    def test_fallo_de_omdb_no_impide_crear_la_pelicula(self, mock_get):
        import requests

        def side_effect(url, params=None, timeout=None):
            if "omdbapi.com" in url:
                raise requests.RequestException("boom")
            return self._fake_tmdb_get(url, params, timeout)

        mock_get.side_effect = side_effect
        movie = Movie.get_or_create_from_tmdb(24428, media_type="movie")
        self.assertEqual(movie.title, "Vengadores")
        self.assertIsNone(movie.imdb_rating)


class VoteTests(TestCase):
    def setUp(self):
        self.user = make_user("lector@test.local")
        self.movie = make_movie(1, "Movie A", "8.0")
        self.client.login(username=self.user.email, password="Testpass123!")

    def test_un_voto_por_usuario_y_pelicula_sobreescribe(self):
        self.client.post(reverse("movies:vote", args=[self.movie.pk]), {"score": 7})
        self.client.post(reverse("movies:vote", args=[self.movie.pk]), {"score": 9})
        self.assertEqual(Vote.objects.filter(movie=self.movie, user=self.user).count(), 1)
        self.assertEqual(Vote.objects.get(movie=self.movie, user=self.user).score, 9)

    def test_anonimo_no_puede_votar(self):
        self.client.logout()
        response = self.client.post(reverse("movies:vote", args=[self.movie.pk]), {"score": 7})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/cuenta/login/", response.url)

    def test_media_y_recuento(self):
        other = make_user("otro@test.local")
        Vote.objects.create(movie=self.movie, user=self.user, score=8)
        Vote.objects.create(movie=self.movie, user=other, score=6)
        self.assertEqual(self.movie.votes_count, 2)
        self.assertEqual(float(self.movie.average_score), 7.0)

    def test_quitar_nota_borra_el_voto(self):
        Vote.objects.create(movie=self.movie, user=self.user, score=8)
        self.client.post(reverse("movies:vote-remove", args=[self.movie.pk]))
        self.assertFalse(Vote.objects.filter(movie=self.movie, user=self.user).exists())

    def test_quitar_nota_la_saca_de_mis_peliculas(self):
        Vote.objects.create(movie=self.movie, user=self.user, score=8)
        self.client.post(reverse("movies:vote-remove", args=[self.movie.pk]))
        response = self.client.get(reverse("movies:my-movies"))
        self.assertEqual(list(response.context["votes"]), [])

    def test_quitar_nota_no_afecta_el_voto_de_otro_usuario(self):
        other = make_user("otro@test.local")
        Vote.objects.create(movie=self.movie, user=self.user, score=8)
        Vote.objects.create(movie=self.movie, user=other, score=5)
        self.client.post(reverse("movies:vote-remove", args=[self.movie.pk]))
        self.assertTrue(Vote.objects.filter(movie=self.movie, user=other).exists())

    def test_anonimo_no_puede_quitar_nota(self):
        self.client.logout()
        response = self.client.post(reverse("movies:vote-remove", args=[self.movie.pk]))
        self.assertIn("/cuenta/login/", response.url)


class SavedMovieTests(TestCase):
    def setUp(self):
        self.user = make_user("lector@test.local")
        self.movie = make_movie(1, "Movie A", "8.0")
        self.client.login(username=self.user.email, password="Testpass123!")

    def test_guardar_pelicula(self):
        response = self.client.post(reverse("movies:save-toggle", args=[self.movie.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SavedMovie.objects.filter(user=self.user, movie=self.movie).exists())

    def test_segundo_clic_la_quita(self):
        SavedMovie.objects.create(user=self.user, movie=self.movie)
        self.client.post(reverse("movies:save-toggle", args=[self.movie.pk]))
        self.assertFalse(SavedMovie.objects.filter(user=self.user, movie=self.movie).exists())

    def test_anonimo_no_puede_guardar(self):
        self.client.logout()
        response = self.client.post(reverse("movies:save-toggle", args=[self.movie.pk]))
        self.assertIn("/cuenta/login/", response.url)

    def test_la_ficha_de_una_pelicula_dice_guardar_pelicula(self):
        response = self.client.get(reverse("movies:detail", args=[self.movie.pk]))
        self.assertContains(response, "Guardar película")
        self.assertNotContains(response, "Guardar serie")

    def test_la_ficha_de_una_serie_dice_guardar_serie(self):
        series = Movie.objects.create(tmdb_id=2, title="Serie A", media_type="tv")
        response = self.client.get(reverse("movies:detail", args=[series.pk]))
        self.assertContains(response, "Guardar serie")
        self.assertNotContains(response, "Guardar película")

    def test_la_ficha_no_muestra_la_recaudacion_aunque_se_conozca(self):
        self.movie.revenue = 2_798_000_000
        self.movie.save(update_fields=["revenue"])
        response = self.client.get(reverse("movies:detail", args=[self.movie.pk]))
        self.assertNotContains(response, "💰")
        self.assertNotContains(response, "$2.798.000.000")

    def test_mis_peliculas_muestra_solo_lo_votado(self):
        other_movie = make_movie(2, "Movie B", "7.0")
        Vote.objects.create(movie=self.movie, user=self.user, score=9)
        SavedMovie.objects.create(user=self.user, movie=other_movie)

        response = self.client.get(reverse("movies:my-movies"))
        self.assertEqual(list(response.context["votes"].values_list("movie", flat=True)), [self.movie.pk])
        self.assertNotIn("saved", response.context)

    def test_pagina_guardadas_separada_de_mis_peliculas(self):
        SavedMovie.objects.create(user=self.user, movie=self.movie)
        response = self.client.get(reverse("movies:saved-movies"))
        self.assertEqual(list(response.context["saved"].values_list("movie", flat=True)), [self.movie.pk])

    def test_anonimo_no_ve_guardadas(self):
        self.client.logout()
        response = self.client.get(reverse("movies:saved-movies"))
        self.assertIn("/cuenta/login/", response.url)

    def test_guardadas_filtra_por_tipo(self):
        serie = Movie.objects.create(tmdb_id=2, title="Serie A", media_type="tv")
        SavedMovie.objects.create(user=self.user, movie=self.movie)
        SavedMovie.objects.create(user=self.user, movie=serie)

        response = self.client.get(reverse("movies:saved-movies"), {"type": "tv"})
        self.assertEqual(list(response.context["saved"].values_list("movie", flat=True)), [serie.pk])

        response = self.client.get(reverse("movies:saved-movies"), {"type": "movie"})
        self.assertEqual(list(response.context["saved"].values_list("movie", flat=True)), [self.movie.pk])

    def test_guardadas_muestra_pelis_y_series_juntas_por_defecto(self):
        serie = Movie.objects.create(tmdb_id=2, title="Serie A", media_type="tv")
        SavedMovie.objects.create(user=self.user, movie=self.movie)
        SavedMovie.objects.create(user=self.user, movie=serie)

        response = self.client.get(reverse("movies:saved-movies"))
        self.assertEqual(response.context["media_type"], "all")
        self.assertEqual(
            set(response.context["saved"].values_list("movie", flat=True)),
            {self.movie.pk, serie.pk},
        )

    def test_guardadas_busca_por_titulo(self):
        other_movie = make_movie(2, "Otra pelicula", "7.0")
        SavedMovie.objects.create(user=self.user, movie=self.movie)
        SavedMovie.objects.create(user=self.user, movie=other_movie)

        response = self.client.get(reverse("movies:saved-movies"), {"q": self.movie.title})
        self.assertEqual(list(response.context["saved"].values_list("movie", flat=True)), [self.movie.pk])

    def test_mover_guardada_cambia_el_orden(self):
        other = make_movie(2, "Movie B", "7.0")
        saved_a = SavedMovie.objects.create(user=self.user, movie=self.movie, order=0)
        saved_b = SavedMovie.objects.create(user=self.user, movie=other, order=1)

        self.client.post(reverse("movies:saved-movie-move", args=[saved_b.pk, "up"]))

        saved_a.refresh_from_db()
        saved_b.refresh_from_db()
        self.assertEqual(saved_b.order, 0)
        self.assertEqual(saved_a.order, 1)

    def test_no_se_puede_mover_una_guardada_ajena(self):
        other_user = make_user("otro_guardada@test.local")
        saved = SavedMovie.objects.create(user=other_user, movie=self.movie, order=0)
        response = self.client.post(reverse("movies:saved-movie-move", args=[saved.pk, "up"]))
        self.assertEqual(response.status_code, 404)

    def test_reordenar_por_arrastre_aplica_el_orden_recibido(self):
        import json

        other = make_movie(2, "Movie B", "7.0")
        third = make_movie(3, "Movie C", "6.0")
        a = SavedMovie.objects.create(user=self.user, movie=self.movie, order=0)
        b = SavedMovie.objects.create(user=self.user, movie=other, order=1)
        c = SavedMovie.objects.create(user=self.user, movie=third, order=2)

        response = self.client.post(
            reverse("movies:saved-movie-reorder"),
            data=json.dumps({"order": [c.pk, a.pk, b.pk]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        a.refresh_from_db(); b.refresh_from_db(); c.refresh_from_db()
        self.assertEqual((c.order, a.order, b.order), (0, 1, 2))

    def test_reordenar_por_arrastre_no_mueve_las_guardadas_fuera_del_filtro(self):
        """Arrastrar dentro de una lista filtrada solo debe permutar las que
        se ven — una guardada de otra lista, no incluida en el POST, debe
        conservar su posición relativa."""
        import json

        other = make_movie(2, "Movie B", "7.0")
        hidden_movie = make_movie(3, "Hidden", "5.0")
        a = SavedMovie.objects.create(user=self.user, movie=self.movie, order=0)
        hidden = SavedMovie.objects.create(user=self.user, movie=hidden_movie, order=1)
        b = SavedMovie.objects.create(user=self.user, movie=other, order=2)

        response = self.client.post(
            reverse("movies:saved-movie-reorder"),
            data=json.dumps({"order": [b.pk, a.pk]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        a.refresh_from_db(); hidden.refresh_from_db(); b.refresh_from_db()
        # a y b se permutan entre sí (posiciones 0 y 2), hidden se queda en medio (1).
        self.assertEqual((b.order, hidden.order, a.order), (0, 1, 2))

    def test_reordenar_por_arrastre_no_afecta_guardadas_de_otro_usuario(self):
        import json

        other_user = make_user("otro_arrastre@test.local")
        ajena = SavedMovie.objects.create(user=other_user, movie=self.movie, order=0)

        response = self.client.post(
            reverse("movies:saved-movie-reorder"),
            data=json.dumps({"order": [ajena.pk]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        ajena.refresh_from_db()
        self.assertEqual(ajena.order, 0)


class MovieSaveListsWidgetTests(TestCase):
    """Marcar listas directamente desde la ficha de la película — al lado
    del botón de guardar, sin estorbar a quien no tiene listas creadas."""

    def setUp(self):
        self.user = make_user("con_listas@test.local")
        self.movie = make_movie(1, "Movie A", "8.0")
        self.client.login(username=self.user.email, password="Testpass123!")

    def test_sin_listas_creadas_no_sale_el_selector(self):
        response = self.client.get(reverse("movies:detail", args=[self.movie.pk]))
        self.assertNotContains(response, "save-lists__toggle")

    def test_con_listas_creadas_sale_el_selector(self):
        SavedMovieList.objects.create(user=self.user, name="Terror")
        response = self.client.get(reverse("movies:detail", args=[self.movie.pk]))
        self.assertContains(response, "save-lists__toggle")
        self.assertContains(response, "Terror")

    def test_marcar_una_lista_guarda_la_pelicula_si_no_lo_estaba(self):
        lista = SavedMovieList.objects.create(user=self.user, name="Terror")
        self.client.post(reverse("movies:save-lists", args=[self.movie.pk]), {"sublists": [lista.pk]})
        saved = SavedMovie.objects.get(user=self.user, movie=self.movie)
        self.assertIn(lista, saved.sublists.all())

    def test_desmarcar_todas_deja_la_pelicula_guardada_sin_listas(self):
        lista = SavedMovieList.objects.create(user=self.user, name="Terror")
        saved = SavedMovie.objects.create(user=self.user, movie=self.movie)
        saved.sublists.add(lista)

        self.client.post(reverse("movies:save-lists", args=[self.movie.pk]), {})

        saved.refresh_from_db()
        self.assertTrue(SavedMovie.objects.filter(pk=saved.pk).exists())
        self.assertEqual(list(saved.sublists.all()), [])

    def test_no_se_pueden_usar_listas_ajenas(self):
        other_user = make_user("otra_persona_listas@test.local")
        ajena = SavedMovieList.objects.create(user=other_user, name="Ajena")
        self.client.post(reverse("movies:save-lists", args=[self.movie.pk]), {"sublists": [ajena.pk]})
        saved = SavedMovie.objects.get(user=self.user, movie=self.movie)
        self.assertEqual(list(saved.sublists.all()), [])

    def test_anonimo_no_puede_usar_el_selector(self):
        self.client.logout()
        response = self.client.post(reverse("movies:save-lists", args=[self.movie.pk]), {})
        self.assertIn("/cuenta/login/", response.url)


class SavedMovieSublistTests(TestCase):
    def setUp(self):
        self.user = make_user("sublistas@test.local")
        self.client.login(username=self.user.email, password="Testpass123!")
        self.movie_a = make_movie(1, "A", None)
        self.movie_b = make_movie(2, "B", None)

    def test_crear_sublista(self):
        self.client.post(reverse("movies:saved-list-create"), {"name": "Terror"})
        self.assertTrue(SavedMovieList.objects.filter(user=self.user, name="Terror").exists())

    def test_ordenar_listas_es_un_desplegable_colapsado(self):
        # No es una sección siempre visible: un <details> pequeño, cerrado
        # por defecto, debajo de las guardadas.
        SavedMovieList.objects.create(user=self.user, name="Terror")
        response = self.client.get(reverse("movies:saved-movies"))
        self.assertContains(response, "Ordenar listas")
        self.assertContains(response, "saved-lists-manage")

    def test_sin_sublistas_no_sale_el_desplegable_de_ordenar(self):
        response = self.client.get(reverse("movies:saved-movies"))
        self.assertNotContains(response, "Ordenar listas")

    def test_crear_sublista_con_nombre_repetido_no_duplica(self):
        SavedMovieList.objects.create(user=self.user, name="Terror")
        self.client.post(reverse("movies:saved-list-create"), {"name": "Terror"})
        self.assertEqual(SavedMovieList.objects.filter(user=self.user, name="Terror").count(), 1)

    def test_asignar_una_guardada_a_una_sublista(self):
        sublist = SavedMovieList.objects.create(user=self.user, name="Terror")
        saved = SavedMovie.objects.create(user=self.user, movie=self.movie_a)
        self.client.post(reverse("movies:saved-movie-toggle-sublist", args=[saved.pk, sublist.pk]))
        saved.refresh_from_db()
        self.assertIn(sublist, saved.sublists.all())

    def test_quitar_la_sublista_de_una_guardada(self):
        sublist = SavedMovieList.objects.create(user=self.user, name="Terror")
        saved = SavedMovie.objects.create(user=self.user, movie=self.movie_a)
        saved.sublists.add(sublist)
        self.client.post(reverse("movies:saved-movie-toggle-sublist", args=[saved.pk, sublist.pk]))
        saved.refresh_from_db()
        self.assertNotIn(sublist, saved.sublists.all())

    def test_una_guardada_puede_estar_en_varias_sublistas_a_la_vez(self):
        terror = SavedMovieList.objects.create(user=self.user, name="Terror")
        familia = SavedMovieList.objects.create(user=self.user, name="Familia")
        saved = SavedMovie.objects.create(user=self.user, movie=self.movie_a)
        self.client.post(reverse("movies:saved-movie-toggle-sublist", args=[saved.pk, terror.pk]))
        self.client.post(reverse("movies:saved-movie-toggle-sublist", args=[saved.pk, familia.pk]))
        saved.refresh_from_db()
        self.assertEqual(set(saved.sublists.all()), {terror, familia})

    def test_no_se_puede_asignar_una_sublista_ajena(self):
        other_user = make_user("otro_sublista@test.local")
        ajena = SavedMovieList.objects.create(user=other_user, name="Ajena")
        saved = SavedMovie.objects.create(user=self.user, movie=self.movie_a)
        response = self.client.post(reverse("movies:saved-movie-toggle-sublist", args=[saved.pk, ajena.pk]))
        self.assertEqual(response.status_code, 404)

    def test_filtrar_guardadas_por_sublista(self):
        terror = SavedMovieList.objects.create(user=self.user, name="Terror")
        saved_a = SavedMovie.objects.create(user=self.user, movie=self.movie_a)
        saved_a.sublists.add(terror)
        SavedMovie.objects.create(user=self.user, movie=self.movie_b)

        response = self.client.get(reverse("movies:saved-movies"), {"list": terror.pk})
        self.assertEqual(list(response.context["saved"].values_list("movie", flat=True)), [self.movie_a.pk])

    def test_filtrar_guardadas_sin_sublista(self):
        terror = SavedMovieList.objects.create(user=self.user, name="Terror")
        saved_a = SavedMovie.objects.create(user=self.user, movie=self.movie_a)
        saved_a.sublists.add(terror)
        SavedMovie.objects.create(user=self.user, movie=self.movie_b)

        response = self.client.get(reverse("movies:saved-movies"), {"list": "none"})
        self.assertEqual(list(response.context["saved"].values_list("movie", flat=True)), [self.movie_b.pk])

    def test_borrar_sublista_no_borra_las_guardadas(self):
        sublist = SavedMovieList.objects.create(user=self.user, name="Terror")
        saved = SavedMovie.objects.create(user=self.user, movie=self.movie_a)
        saved.sublists.add(sublist)
        self.client.post(reverse("movies:saved-list-delete", args=[sublist.pk]))
        self.assertFalse(SavedMovieList.objects.filter(pk=sublist.pk).exists())
        saved.refresh_from_db()
        self.assertEqual(saved.sublists.count(), 0)

    def test_no_se_puede_borrar_una_sublista_ajena(self):
        other_user = make_user("otro_sublista2@test.local")
        ajena = SavedMovieList.objects.create(user=other_user, name="Ajena")
        response = self.client.post(reverse("movies:saved-list-delete", args=[ajena.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(SavedMovieList.objects.filter(pk=ajena.pk).exists())

    def test_reordenar_sublistas_arrastrando(self):
        terror = SavedMovieList.objects.create(user=self.user, name="Terror", order=0)
        familia = SavedMovieList.objects.create(user=self.user, name="Familia", order=1)
        response = self.client.post(
            reverse("movies:saved-list-reorder"),
            data=json.dumps({"order": [familia.pk, terror.pk]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        terror.refresh_from_db()
        familia.refresh_from_db()
        self.assertEqual(familia.order, 0)
        self.assertEqual(terror.order, 1)

    def test_reordenar_sublistas_no_toca_las_de_otro_usuario(self):
        other_user = make_user("otro_reorden@test.local")
        ajena = SavedMovieList.objects.create(user=other_user, name="Ajena", order=0)
        self.client.post(
            reverse("movies:saved-list-reorder"),
            data=json.dumps({"order": [ajena.pk]}),
            content_type="application/json",
        )
        ajena.refresh_from_db()
        self.assertEqual(ajena.order, 0)


class SavedMoviesShareImageTests(TestCase):
    def setUp(self):
        self.user = make_user("compartir_guardadas@test.local")
        self.client.login(username=self.user.email, password="Testpass123!")

    def test_compartir_guardadas_devuelve_una_imagen_png(self):
        terror = SavedMovieList.objects.create(user=self.user, name="Terror")
        movie = make_movie(1, "Kill Bill", None)
        saved = SavedMovie.objects.create(user=self.user, movie=movie)
        saved.sublists.add(terror)

        response = self.client.get(reverse("movies:saved-movies-share-image"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_compartir_guardadas_sin_nada_no_rompe(self):
        response = self.client.get(reverse("movies:saved-movies-share-image"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_compartir_guardadas_requiere_login(self):
        self.client.logout()
        response = self.client.get(reverse("movies:saved-movies-share-image"))
        self.assertNotEqual(response.status_code, 200)

    def test_el_boton_compartir_apunta_directo_a_la_imagen_para_descargar(self):
        response = self.client.get(reverse("movies:saved-movies"))
        self.assertContains(response, reverse("movies:saved-movies-share-image"))
        self.assertContains(response, "download=")


class RouletteRatingTests(TestCase):
    def setUp(self):
        self.user = make_user("lector@test.local")
        self.client.login(username=self.user.email, password="Testpass123!")
        self.low = make_movie(1, "Baja", "4.0")
        self.mid1 = make_movie(2, "Media 1", "7.5")
        self.mid2 = make_movie(3, "Media 2", "8.0")

    def test_filtra_por_rango_y_no_repite_hasta_agotar(self):
        seen = set()
        for _ in range(2):
            response = self.client.post(reverse("movies:roulette-rating"), {"min_rating": 7, "max_rating": 9})
            result = response.context["result"]
            self.assertIsNotNone(result)
            self.assertNotIn(result.pk, seen)
            seen.add(result.pk)

        # Ya se mostraron las dos películas del rango: la tercera vez se agota.
        response = self.client.post(reverse("movies:roulette-rating"), {"min_rating": 7, "max_rating": 9})
        self.assertIsNone(response.context["result"])
        self.assertEqual(seen, {self.mid1.pk, self.mid2.pk})

    def test_reiniciar_permite_volver_a_verlas(self):
        RouletteRatingSeen.objects.create(user=self.user, movie=self.mid1)
        RouletteRatingSeen.objects.create(user=self.user, movie=self.mid2)
        self.client.post(reverse("movies:roulette-rating-reset"))
        self.assertEqual(RouletteRatingSeen.objects.filter(user=self.user).count(), 0)

    def test_rango_sin_peliculas(self):
        response = self.client.post(reverse("movies:roulette-rating"), {"min_rating": 1, "max_rating": 2})
        self.assertIsNone(response.context["result"])

    def test_el_carrusel_no_rompe_el_atributo_html(self):
        # Regresión: reel_json es JSON (comillas dobles) y se embebía dentro
        # de un atributo x-data también delimitado por comillas dobles, lo
        # que el navegador cortaba en la primera comilla del JSON — el
        # carrusel/cartel nunca llegaba a mostrarse. Debe ir en comillas simples.
        response = self.client.post(reverse("movies:roulette-rating"), {"min_rating": 7, "max_rating": 9})
        content = response.content.decode()
        self.assertIn("slot-machine\" x-data='slotSpin(", content)
        self.assertNotIn('slot-machine" x-data="slotSpin(', content)

    def test_la_tragaperras_tiene_tres_tiras_que_acaban_en_el_mismo_cartel(self):
        response = self.client.post(reverse("movies:roulette-rating"), {"min_rating": 7, "max_rating": 9})
        parsed = json.loads(response.context["reel_json"])
        self.assertEqual(len(parsed), 3)
        result_poster = response.context["result"].poster_url or ""
        for reel in parsed:
            self.assertEqual(reel[-1], result_poster)


class RouletteListTests(TestCase):
    """Modo 2: gira directamente sobre `SavedMovie`, sin una lista de
    candidatas aparte — guardar una película ya la hace elegible aquí."""

    def setUp(self):
        self.user = make_user("lector@test.local")
        self.client.login(username=self.user.email, password="Testpass123!")
        self.movie_a = make_movie(1, "A", None)
        self.movie_b = make_movie(2, "B", None)
        SavedMovie.objects.create(user=self.user, movie=self.movie_a)
        SavedMovie.objects.create(user=self.user, movie=self.movie_b)

    def test_girar_marca_como_vista_y_no_repite(self):
        seen_ids = set()
        for _ in range(2):
            response = self.client.post(reverse("movies:roulette-list-draw"))
            result = response.context["result"]
            self.assertIsNotNone(result)
            seen_ids.add(result.pk)

        self.assertEqual(seen_ids, {self.movie_a.pk, self.movie_b.pk})
        self.assertEqual(RouletteSavedSeen.objects.filter(user=self.user).count(), 2)

        response = self.client.post(reverse("movies:roulette-list-draw"))
        self.assertIsNone(response.context["result"])

    def test_reiniciar(self):
        RouletteSavedSeen.objects.create(user=self.user, movie=self.movie_a)
        RouletteSavedSeen.objects.create(user=self.user, movie=self.movie_b)
        self.client.post(reverse("movies:roulette-list-reset"))
        self.assertEqual(RouletteSavedSeen.objects.filter(user=self.user).count(), 0)

    def test_guardar_una_pelicula_la_hace_elegible_sin_pasos_extra(self):
        nueva = make_movie(60, "Recién guardada", None)
        self.client.post(reverse("movies:save-toggle", args=[nueva.pk]))

        response = self.client.get(reverse("movies:roulette-list"))
        saved_ids = list(response.context["saved"].values_list("movie", flat=True))
        self.assertIn(nueva.pk, saved_ids)

    def test_sin_guardadas_no_hay_resultado(self):
        SavedMovie.objects.filter(user=self.user).delete()
        response = self.client.post(reverse("movies:roulette-list-draw"))
        self.assertIsNone(response.context["result"])


class RouletteListSublistTests(TestCase):
    def setUp(self):
        self.user = make_user("ruleta_sublista@test.local")
        self.client.login(username=self.user.email, password="Testpass123!")
        self.terror = SavedMovieList.objects.create(user=self.user, name="Terror")
        self.movie_terror = make_movie(1, "De terror", None)
        self.movie_sin_lista = make_movie(2, "Sin lista", None)
        saved_terror = SavedMovie.objects.create(user=self.user, movie=self.movie_terror)
        saved_terror.sublists.add(self.terror)
        SavedMovie.objects.create(user=self.user, movie=self.movie_sin_lista)

    def test_la_pagina_solo_muestra_las_de_la_sublista_elegida(self):
        response = self.client.get(reverse("movies:roulette-list"), {"list": self.terror.pk})
        saved_ids = list(response.context["saved"].values_list("movie", flat=True))
        self.assertEqual(saved_ids, [self.movie_terror.pk])

    def test_girar_con_sublista_solo_elige_de_esa_sublista(self):
        for _ in range(5):
            response = self.client.post(reverse("movies:roulette-list-draw"), {"list": self.terror.pk})
            self.assertEqual(response.context["result"], self.movie_terror)
            RouletteSavedSeen.objects.filter(user=self.user).delete()

    def test_girar_sin_sublista_elige_de_todas(self):
        response = self.client.post(reverse("movies:roulette-list-draw"))
        self.assertIn(response.context["result"], [self.movie_terror, self.movie_sin_lista])

    def test_reiniciar_conserva_el_filtro_de_sublista(self):
        response = self.client.post(reverse("movies:roulette-list-reset"), {"list": self.terror.pk})
        self.assertRedirects(response, reverse("movies:roulette-list") + f"?list={self.terror.pk}")


class MovieListLiveSearchTests(TestCase):
    """El catálogo es el de TMDb entero, no una lista local aparte: buscar
    siempre pega en vivo a la API. Un resultado ya visitado antes se marca
    como local (enlaza directo a su ficha, con la nota IMDb ya cacheada) en
    vez de aparecer duplicado como si fuera un resultado distinto."""

    def _tmdb_result(self, tmdb_id, title, media_type="movie"):
        from apps.movies.services import TMDbResult
        return TMDbResult(tmdb_id=tmdb_id, title=title, year="2020", poster_path="/x.jpg", overview="...", media_type=media_type)

    def test_sin_query_no_busca_en_tmdb(self):
        with patch("apps.movies.views.tmdb_search") as mock_search:
            response = self.client.get(reverse("movies:list"))
            self.assertEqual(response.status_code, 200)
            mock_search.assert_not_called()

    @patch("apps.movies.views.tmdb_search")
    def test_pelicula_no_cacheada_aparece_como_no_local(self, mock_search):
        mock_search.return_value = [self._tmdb_result(603, "The Matrix")]
        response = self.client.get(reverse("movies:list"), {"query": "matrix"})
        mock_search.assert_called_once_with("matrix", media_type="movie")
        movies = response.context["movies"]
        self.assertEqual(len(movies), 1)
        result, is_local = movies[0]
        self.assertEqual(result.tmdb_id, 603)
        self.assertFalse(is_local)

    @patch("apps.movies.views.tmdb_search")
    def test_pelicula_ya_cacheada_aparece_como_local_sin_duplicarse(self, mock_search):
        movie = make_movie(603, "Matrix", None)
        mock_search.return_value = [self._tmdb_result(603, "The Matrix")]
        response = self.client.get(reverse("movies:list"), {"query": "matrix"})
        movies = response.context["movies"]
        self.assertEqual(len(movies), 1)
        result, is_local = movies[0]
        self.assertEqual(result, movie)
        self.assertTrue(is_local)

    @patch("apps.movies.views.tmdb_search", side_effect=MovieAPIError("fallo de red"))
    def test_error_de_tmdb_no_rompe_la_pagina(self, mock_search):
        response = self.client.get(reverse("movies:list"), {"query": "matrix"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["search_error"], "fallo de red")

    @patch("apps.movies.views.Movie.get_or_create_from_tmdb")
    def test_ver_ficha_desde_tmdb_crea_y_redirige(self, mock_get_or_create):
        mock_get_or_create.return_value = make_movie(603, "Matrix", None)
        response = self.client.get(reverse("movies:from-tmdb", args=["movie", 603]))
        self.assertRedirects(response, reverse("movies:detail", args=[mock_get_or_create.return_value.pk]))

    @patch("apps.movies.views.Movie.get_or_create_from_tmdb")
    def test_ver_ficha_de_serie_desde_tmdb(self, mock_get_or_create):
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=1, title="Dark", media_type="tv")
        response = self.client.get(reverse("movies:from-tmdb", args=["tv", 1]))
        self.assertRedirects(response, reverse("movies:detail", args=[mock_get_or_create.return_value.pk]))
        mock_get_or_create.assert_called_once_with(1, media_type="tv")

    def test_catalogo_sin_busqueda_filtra_por_tipo(self):
        pelicula = Movie.objects.create(tmdb_id=1, title="Una película", imdb_rating="7.0", poster_path="/p.jpg")
        serie = Movie.objects.create(tmdb_id=2, title="Una serie", media_type="tv", imdb_rating="7.0", poster_path="/s.jpg")

        response = self.client.get(reverse("movies:list"), {"type": "tv"})
        self.assertEqual(list(response.context["page_obj"].object_list), [serie])

        response = self.client.get(reverse("movies:list"), {"type": "movie"})
        self.assertEqual(list(response.context["page_obj"].object_list), [pelicula])

        response = self.client.get(reverse("movies:list"), {"type": "all"})
        self.assertEqual(set(response.context["page_obj"].object_list), {pelicula, serie})

    @patch("apps.movies.views.tmdb_search")
    def test_busqueda_en_tv_usa_el_endpoint_de_series(self, mock_search):
        mock_search.return_value = []
        self.client.get(reverse("movies:list"), {"query": "dark", "type": "tv"})
        mock_search.assert_called_once_with("dark", media_type="tv")

    @patch("apps.movies.views.tmdb_search")
    def test_busqueda_con_tipo_todas_junta_peliculas_y_series(self, mock_search):
        mock_search.side_effect = lambda term, media_type: (
            [self._tmdb_result(1, "Una película", "movie")] if media_type == "movie"
            else [self._tmdb_result(2, "Una serie", "tv")]
        )
        response = self.client.get(reverse("movies:list"), {"query": "algo", "type": "all"})
        results = [r for r, _ in response.context["movies"]]
        self.assertEqual({r.tmdb_id for r in results}, {1, 2})


class MovieAdminAutocompleteImportTests(TestCase):
    """El selector de "portada" (autocompletar del campo `movie`, usado
    desde Película secreta y Tier list) solo miraba el catálogo local — un
    título nunca buscado antes en "Cine" no aparecía. Ahora, si la búsqueda
    local no encuentra nada, se importa de TMDb antes de repetirla."""

    def setUp(self):
        from apps.movies.admin import MovieAdmin
        self.admin = MovieAdmin(Movie, admin.site)

    def _tmdb_result(self, tmdb_id, title, media_type="movie"):
        from apps.movies.services import TMDbResult
        return TMDbResult(tmdb_id=tmdb_id, title=title, year="2010", poster_path="/x.jpg", overview="...", media_type=media_type)

    @patch("apps.movies.admin.tmdb_search")
    def test_titulo_no_cacheado_se_importa_de_tmdb(self, mock_search):
        mock_search.side_effect = lambda term, media_type: (
            [self._tmdb_result(1, "El prestigio", media_type)] if media_type == "movie" else []
        )
        results, _ = self.admin.get_search_results(None, Movie.objects.all(), "El prestigio")
        self.assertEqual(list(results.values_list("title", flat=True)), ["El prestigio"])
        self.assertTrue(Movie.objects.filter(tmdb_id=1, media_type="movie").exists())

    @patch("apps.movies.admin.tmdb_search")
    def test_titulo_ya_en_catalogo_no_repite_llamada_a_tmdb(self, mock_search):
        make_movie(1, "El prestigio", None)
        results, _ = self.admin.get_search_results(None, Movie.objects.all(), "prestigio")
        self.assertEqual(list(results.values_list("title", flat=True)), ["El prestigio"])
        mock_search.assert_not_called()

    @patch("apps.movies.admin.tmdb_search", side_effect=MovieAPIError("fallo de red"))
    def test_fallo_de_tmdb_no_rompe_el_autocompletar(self, mock_search):
        results, _ = self.admin.get_search_results(None, Movie.objects.all(), "loquesea")
        self.assertEqual(list(results), [])


class MovieListInfiniteScrollTests(TestCase):
    """El catálogo ya no pagina con botones "anterior/siguiente" (llegaba a
    16 páginas): la primera carga trae un tramo y un "sensor" al final que,
    al aparecer en pantalla, pide el siguiente tramo por HTMX."""

    def setUp(self):
        # Fichas completas: sin buscar solo salen las que tienen portada y nota.
        for i in range(1, 30):
            Movie.objects.create(tmdb_id=i, title=f"Película {i}", imdb_rating="7.0", poster_path="/p.jpg")

    def test_primera_carga_trae_un_tramo_y_el_sensor_de_la_siguiente(self):
        response = self.client.get(reverse("movies:list"))
        self.assertEqual(len(response.context["page_obj"].object_list), 24)
        self.assertContains(response, "movie-grid__sentinel")
        self.assertContains(response, "?page=2")

    def test_htmx_devuelve_solo_el_fragmento_sin_la_pagina_completa(self):
        response = self.client.get(
            reverse("movies:list"), {"page": 2}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(len(response.context["page_obj"].object_list), 5)
        self.assertContains(response, "movie-card")
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, "movie-grid__sentinel")


class SeedMoviesCommandTests(TestCase):
    """`seed_movies` debe combinar populares/mejor valoradas con discover por
    franja de nota, para que el catálogo no quede sesgado hacia notas altas
    (si no, ciertos rangos del Modo 1 de la ruleta se quedan sin candidatas)."""

    def _fake_tmdb_get(self, url, params=None, timeout=None):
        from unittest.mock import MagicMock

        response = MagicMock()
        response.raise_for_status.return_value = None

        if url.endswith("/movie/popular"):
            response.json.return_value = {"results": [{"id": 1}, {"id": 2}]}
        elif url.endswith("/movie/top_rated"):
            response.json.return_value = {"results": [{"id": 2}, {"id": 3}]}
        elif url.endswith("/discover/movie"):
            # Cada franja (bucket) devuelve una peli distinta según su umbral,
            # simulando que discover trae candidatas de nota baja/media.
            if params.get("vote_average.lte") == 4:
                response.json.return_value = {"results": [{"id": 100}]}
            elif params.get("vote_average.lte") == 6:
                response.json.return_value = {"results": [{"id": 101}]}
            else:
                response.json.return_value = {"results": [{"id": 102}]}
        elif "themoviedb.org/3/movie/" in url:
            tmdb_id = int(url.rstrip("/").split("/")[-1])
            response.json.return_value = {
                "id": tmdb_id, "title": f"Película {tmdb_id}", "release_date": "2020-01-01",
                "poster_path": "/p.jpg", "overview": "...",
                "external_ids": {"imdb_id": f"tt{tmdb_id:07d}"},
            }
        elif "omdbapi.com" in url:
            response.json.return_value = {"imdbRating": "5.5"}
        else:
            raise AssertionError(f"URL inesperada en el test: {url}")
        return response

    @override_settings(TMDB_API_KEY="fake-tmdb-key", OMDB_API_KEY="fake-omdb-key")
    @patch("requests.get")
    def test_incluye_peliculas_de_las_franjas_discover_ademas_de_populares(self, mock_get):
        mock_get.side_effect = self._fake_tmdb_get
        from django.core.management import call_command

        call_command("seed_movies", "--pages", "1")

        tmdb_ids = set(Movie.objects.values_list("tmdb_id", flat=True))
        # 1, 2, 3 vienen de popular/top_rated; 100/101/102 de las franjas discover.
        self.assertEqual(tmdb_ids, {1, 2, 3, 100, 101, 102})

    @override_settings(TMDB_API_KEY="", OMDB_API_KEY="")
    def test_sin_api_keys_no_hace_peticiones(self):
        from django.core.management import call_command

        call_command("seed_movies")
        self.assertEqual(Movie.objects.count(), 0)


class SavedMovieListSortableAdminTests(TestCase):
    """SortableAdminMixin (apps/core/admin.py) también en Listas de
    guardadas — arrastrar en el admin en vez de editar el número de
    `order` a mano, igual que Temas/Enlaces de contacto/etc."""

    def setUp(self):
        self.admin = User.objects.create(email="drag_savedlist@test.local", role=User.Role.ADMIN, is_staff=True, is_superuser=True)
        self.admin.set_password("Testpass123!")
        self.admin.save()
        self.client.login(username=self.admin.email, password="Testpass123!")
        self.user = make_user("dueno_listas@test.local")
        self.a = SavedMovieList.objects.create(user=self.user, name="Terror", order=0)
        self.b = SavedMovieList.objects.create(user=self.user, name="Familia", order=1)
        self.c = SavedMovieList.objects.create(user=self.user, name="Comedia", order=2)

    def test_arrastrar_actualiza_el_orden_de_todos(self):
        url = reverse("admin:movies_savedmovielist_reorder")
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

    def test_el_numero_ya_no_sale_en_el_formulario(self):
        response = self.client.get(reverse("admin:movies_savedmovielist_change", args=[self.a.pk]))
        self.assertNotContains(response, 'name="order"')

    def test_el_listado_tiene_el_tirador_de_arrastre(self):
        response = self.client.get(reverse("admin:movies_savedmovielist_changelist"))
        self.assertContains(response, "drag-handle")


class BackfillMovieRevenueTimeoutTests(TestCase):
    """backfill_movie_revenue va en el startCommand de Render, antes de
    gunicorn -- si TMDb va lento, sin un tope de tiempo el comando puede
    tardar tanto que Render se cansa de esperar un puerto abierto y tumba
    el despliegue entero (incidente real). Ver MAX_SECONDS en el comando."""

    def test_para_al_superar_el_limite_de_tiempo_sin_procesar_el_resto(self):
        from django.core.management import call_command

        from apps.movies.management.commands import backfill_movie_revenue as cmd_module

        Movie.objects.create(media_type=Movie.MediaType.MOVIE, tmdb_id=1, title="Una", revenue=None)
        Movie.objects.create(media_type=Movie.MediaType.MOVIE, tmdb_id=2, title="Dos", revenue=None)

        with override_settings(TMDB_API_KEY="fake-key"), \
             patch.object(cmd_module, "MAX_SECONDS", -1), \
             patch.object(cmd_module, "tmdb_get_details") as mock_details:
            call_command("backfill_movie_revenue")

        mock_details.assert_not_called()

    def test_sin_superar_el_limite_procesa_normalmente(self):
        from django.core.management import call_command

        from apps.movies.management.commands import backfill_movie_revenue as cmd_module

        movie = Movie.objects.create(media_type=Movie.MediaType.MOVIE, tmdb_id=1, title="Una", revenue=None)

        with override_settings(TMDB_API_KEY="fake-key"), \
             patch.object(cmd_module, "MAX_SECONDS", 60), \
             patch.object(cmd_module, "tmdb_get_details", return_value={"revenue": 1_000_000}):
            call_command("backfill_movie_revenue")

        movie.refresh_from_db()
        self.assertEqual(movie.revenue, 1_000_000)


class RefreshImdbRatingsTests(TestCase):
    """refresh_imdb_ratings: renueva solo las notas con más de 30 días, sin
    borrar una nota buena si OMDb ya no la tiene, y parando en seco si OMDb
    falla (cuota agotada) para no gastar peticiones en balde."""

    def _movie(self, tmdb_id, rating, days_ago):
        checked = timezone.now() - timedelta(days=days_ago) if days_ago is not None else None
        return Movie.objects.create(
            tmdb_id=tmdb_id, title=f"Peli {tmdb_id}", imdb_id=f"tt{tmdb_id:07d}",
            imdb_rating=rating, imdb_rating_checked_at=checked,
        )

    def _run(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("refresh_imdb_ratings", stdout=StringIO(), stderr=StringIO())

    @override_settings(OMDB_API_KEY="fake-omdb-key")
    @patch("apps.movies.management.commands.refresh_imdb_ratings.omdb_fetch_imdb_rating")
    def test_solo_renueva_las_notas_antiguas(self, mock_fetch):
        mock_fetch.return_value = 8.1
        old = self._movie(1, "7.5", days_ago=40)
        never = self._movie(2, "6.0", days_ago=None)
        fresh = self._movie(3, "5.0", days_ago=3)
        self._run()
        old.refresh_from_db(); never.refresh_from_db(); fresh.refresh_from_db()
        self.assertEqual(str(old.imdb_rating), "8.1")
        self.assertEqual(str(never.imdb_rating), "8.1")
        self.assertEqual(str(fresh.imdb_rating), "5.0")
        self.assertEqual(mock_fetch.call_count, 2)

    @override_settings(OMDB_API_KEY="fake-omdb-key")
    @patch("apps.movies.management.commands.refresh_imdb_ratings.omdb_fetch_imdb_rating")
    def test_sin_nota_en_omdb_conserva_la_anterior(self, mock_fetch):
        mock_fetch.return_value = None
        movie = self._movie(1, "7.5", days_ago=40)
        self._run()
        movie.refresh_from_db()
        self.assertEqual(str(movie.imdb_rating), "7.5")
        self.assertLess((timezone.now() - movie.imdb_rating_checked_at).days, 1)

    @override_settings(OMDB_API_KEY="fake-omdb-key")
    @patch("apps.movies.management.commands.refresh_imdb_ratings.omdb_fetch_imdb_rating")
    def test_fallo_de_omdb_para_y_no_marca_como_comprobada(self, mock_fetch):
        mock_fetch.side_effect = MovieAPIError("Cuota diaria de OMDb agotada.")
        first = self._movie(1, "7.5", days_ago=40)
        self._movie(2, "6.0", days_ago=50)
        self._run()
        first.refresh_from_db()
        self.assertEqual(str(first.imdb_rating), "7.5")
        self.assertEqual(mock_fetch.call_count, 1)
        self.assertGreater((timezone.now() - first.imdb_rating_checked_at).days, 30)


    @override_settings(OMDB_API_KEY="fake-omdb-key")
    @patch("apps.movies.management.commands.refresh_imdb_ratings.omdb_fetch_imdb_rating")
    def test_primero_las_que_estan_en_alguna_lista(self, mock_fetch):
        from io import StringIO

        from django.core.management import call_command

        from apps.secret.models import SecretMovie

        mock_fetch.return_value = 8.1
        sin_lista = self._movie(1, None, days_ago=None)
        en_lista = self._movie(2, None, days_ago=None)
        SecretMovie.objects.create(title="En mi lista", personal_rating="7.0", movie=en_lista)
        call_command("refresh_imdb_ratings", limit=1, stdout=StringIO(), stderr=StringIO())
        en_lista.refresh_from_db(); sin_lista.refresh_from_db()
        self.assertEqual(str(en_lista.imdb_rating), "8.1")
        self.assertIsNone(sin_lista.imdb_rating)

class SyncNewReleasesTests(TestCase):
    """sync_new_releases: da de alta solo lo que no está ya en el catálogo,
    sin duplicar lo que aparece en varios listados y respetando --limit."""

    def _run(self, **kwargs):
        from io import StringIO

        from django.core.management import call_command

        call_command("sync_new_releases", pages=1, stdout=StringIO(), stderr=StringIO(), **kwargs)

    @override_settings(TMDB_API_KEY="fake-tmdb-key")
    @patch("apps.movies.models.Movie.get_or_create_from_tmdb")
    @patch("requests.get")
    def test_anade_solo_los_que_faltan(self, mock_get, mock_create):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {"results": [{"id": 10}, {"id": 11}]}
        Movie.objects.create(tmdb_id=10, title="Ya está", media_type="movie")
        mock_create.side_effect = lambda tmdb_id, media_type: Movie.objects.create(
            tmdb_id=tmdb_id, title=f"Nueva {tmdb_id}", media_type=media_type,
        )
        self._run()
        created = sorted((c.args[0], c.kwargs["media_type"]) for c in mock_create.call_args_list)
        self.assertEqual(created, [(10, "tv"), (11, "movie"), (11, "tv")])

    @override_settings(TMDB_API_KEY="fake-tmdb-key")
    @patch("apps.movies.models.Movie.get_or_create_from_tmdb")
    @patch("requests.get")
    def test_respeta_el_limite(self, mock_get, mock_create):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = {"results": [{"id": i} for i in range(1, 30)]}
        mock_create.side_effect = lambda tmdb_id, media_type: Movie.objects.create(
            tmdb_id=tmdb_id, title=f"Nueva {tmdb_id}", media_type=media_type,
        )
        self._run(limit=5)
        self.assertEqual(mock_create.call_count, 5)


class DailyCatalogUpdateTests(TestCase):
    """La actualización diaria se lanza como mucho una vez cada RUN_EVERY,
    y nunca fuera del despliegue real (CATALOG_AUTO_UPDATE)."""

    def setUp(self):
        from . import maintenance

        maintenance._next_check_at = 0.0

    def test_claim_daily_run_solo_una_vez(self):
        from .models import CatalogSync

        self.assertTrue(CatalogSync.claim_daily_run(timedelta(hours=20)))
        self.assertFalse(CatalogSync.claim_daily_run(timedelta(hours=20)))
        CatalogSync.objects.filter(pk=1).update(last_started_at=timezone.now() - timedelta(hours=21))
        self.assertTrue(CatalogSync.claim_daily_run(timedelta(hours=20)))

    @override_settings(CATALOG_AUTO_UPDATE=False)
    @patch("apps.movies.maintenance.subprocess.Popen")
    def test_desactivada_no_lanza_nada(self, mock_popen):
        self.client.get(reverse("movies:list"))
        mock_popen.assert_not_called()

    @override_settings(CATALOG_AUTO_UPDATE=True)
    @patch("apps.movies.maintenance.subprocess.Popen")
    def test_activada_lanza_update_catalog_una_vez(self, mock_popen):
        from . import maintenance

        self.client.get(reverse("movies:list"))
        maintenance._next_check_at = 0.0
        self.client.get(reverse("movies:list"))
        self.assertEqual(mock_popen.call_count, 1)
        self.assertIn("update_catalog", mock_popen.call_args.args[0])


@override_settings(OMDB_API_KEY="fake-omdb-key", TMDB_API_KEY="fake-tmdb-key")
class ImdbRatingOnOpenTests(TestCase):
    """Movie.ensure_imdb_rating: al abrir la ficha de una película sin nota
    IMDb se pide en el momento, como mucho una vez al día por película."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        self.movie = Movie.objects.create(tmdb_id=77, title="Sin nota", imdb_id="tt0000077")

    @patch("apps.movies.services.omdb_get_imdb_rating", return_value=7.3)
    def test_al_abrir_la_ficha_se_rellena_la_nota(self, mock_omdb):
        response = self.client.get(reverse("movies:detail", args=[self.movie.pk]))
        self.assertEqual(response.status_code, 200)
        self.movie.refresh_from_db()
        self.assertEqual(str(self.movie.imdb_rating), "7.3")
        self.assertIsNotNone(self.movie.imdb_rating_checked_at)
        mock_omdb.assert_called_once_with("tt0000077")

    @patch("apps.movies.services.omdb_get_imdb_rating", return_value=None)
    def test_sin_nota_en_omdb_no_se_vuelve_a_pedir_hasta_el_dia_siguiente(self, mock_omdb):
        self.client.get(reverse("movies:detail", args=[self.movie.pk]))
        self.client.get(reverse("movies:detail", args=[self.movie.pk]))
        self.assertEqual(mock_omdb.call_count, 1)
        self.movie.refresh_from_db()
        self.assertIsNone(self.movie.imdb_rating)
        self.assertIsNone(self.movie.imdb_rating_checked_at)

    @patch("apps.movies.services.omdb_get_imdb_rating", return_value=6.4)
    @patch("apps.movies.services.tmdb_get_details", return_value={"external_ids": {"imdb_id": "tt0000099"}})
    def test_sin_id_de_imdb_lo_busca_en_tmdb(self, mock_tmdb, mock_omdb):
        movie = Movie.objects.create(tmdb_id=99, title="Sin id")
        self.client.get(reverse("movies:detail", args=[movie.pk]))
        movie.refresh_from_db()
        self.assertEqual(movie.imdb_id, "tt0000099")
        self.assertEqual(str(movie.imdb_rating), "6.4")

    @patch("apps.movies.services.omdb_get_imdb_rating")
    def test_si_ya_tiene_nota_no_pide_nada(self, mock_omdb):
        self.movie.imdb_rating = "8.0"
        self.movie.save()
        self.client.get(reverse("movies:detail", args=[self.movie.pk]))
        mock_omdb.assert_not_called()


class MovieBrowseTests(TestCase):
    """Películas y series sin buscar: solo fichas completas (portada y nota
    IMDb), en un orden que cambia cada día pero es estable dentro del día."""

    def _movie(self, tmdb_id, rating="7.0", poster="/p.jpg", media_type="movie"):
        return Movie.objects.create(
            tmdb_id=tmdb_id, title=f"Peli {tmdb_id}", media_type=media_type,
            imdb_rating=rating, poster_path=poster,
        )

    def _browse(self, **params):
        return self.client.get(reverse("movies:list"), params)

    def test_solo_salen_fichas_con_portada_y_nota(self):
        completa = self._movie(1)
        self._movie(2, rating=None)
        self._movie(3, poster="")
        response = self._browse()
        self.assertEqual(list(response.context["page_obj"].object_list), [completa])

    def test_el_filtro_de_series_tambien_solo_muestra_completas(self):
        serie = self._movie(4, media_type="tv")
        self._movie(5, media_type="tv", rating=None)
        self._movie(6)
        response = self._browse(type="tv")
        self.assertEqual(list(response.context["page_obj"].object_list), [serie])

    def test_el_orden_cambia_de_un_dia_a_otro_y_no_se_repite_ninguna(self):
        from datetime import date

        movies = [self._movie(100 + i) for i in range(40)]

        def order_on(day):
            with patch("apps.movies.views.timezone.localdate", return_value=day):
                first = list(self._browse().context["page_obj"].object_list)
                second = list(self._browse(page=2).context["page_obj"].object_list)
            return first + second

        hoy = order_on(date(2026, 10, 26))
        self.assertEqual(sorted(m.pk for m in hoy), sorted(m.pk for m in movies))
        self.assertEqual(hoy, order_on(date(2026, 10, 26)))
        self.assertNotEqual(hoy, order_on(date(2026, 10, 27)))
