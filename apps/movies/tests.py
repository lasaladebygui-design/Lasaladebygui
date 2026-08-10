import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User

from .models import Movie, RouletteRatingSeen, RouletteSavedSeen, SavedMovie, SavedMovieList, Vote
from .services import MovieAPIError, tmdb_search_person


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

    def test_la_ficha_muestra_la_recaudacion_si_se_conoce(self):
        self.movie.revenue = 2_798_000_000
        self.movie.save(update_fields=["revenue"])
        response = self.client.get(reverse("movies:detail", args=[self.movie.pk]))
        self.assertContains(response, "$2.798.000.000")

    def test_la_ficha_no_muestra_recaudacion_si_no_se_conoce(self):
        response = self.client.get(reverse("movies:detail", args=[self.movie.pk]))
        self.assertNotContains(response, "💰")

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


class SavedMovieSublistTests(TestCase):
    def setUp(self):
        self.user = make_user("sublistas@test.local")
        self.client.login(username=self.user.email, password="Testpass123!")
        self.movie_a = make_movie(1, "A", None)
        self.movie_b = make_movie(2, "B", None)

    def test_crear_sublista(self):
        self.client.post(reverse("movies:saved-list-create"), {"name": "Terror"})
        self.assertTrue(SavedMovieList.objects.filter(user=self.user, name="Terror").exists())

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
    """El catálogo local es limitado a lo ya sembrado/visto; al buscar debe
    complementarse con una búsqueda en vivo a TMDb para cualquier título."""

    def _tmdb_result(self, tmdb_id, title):
        from apps.movies.services import TMDbResult
        return TMDbResult(tmdb_id=tmdb_id, title=title, year="2020", poster_path="/x.jpg", overview="...")

    def test_sin_query_no_busca_en_tmdb(self):
        with patch("apps.movies.views.tmdb_search") as mock_search:
            response = self.client.get(reverse("movies:list"))
            self.assertEqual(response.status_code, 200)
            mock_search.assert_not_called()

    @patch("apps.movies.views.tmdb_search")
    def test_pelicula_no_cacheada_aparece_como_resultado_externo(self, mock_search):
        mock_search.return_value = [self._tmdb_result(603, "The Matrix")]
        response = self.client.get(reverse("movies:list"), {"query": "matrix"})
        mock_search.assert_called_once_with("matrix", media_type="movie")
        external = response.context["external_results"]
        self.assertEqual(len(external), 1)
        self.assertEqual(external[0].tmdb_id, 603)

    @patch("apps.movies.views.tmdb_search")
    def test_pelicula_ya_cacheada_no_se_duplica_en_externos(self, mock_search):
        make_movie(603, "Matrix", None)
        mock_search.return_value = [self._tmdb_result(603, "The Matrix")]
        response = self.client.get(reverse("movies:list"), {"query": "matrix"})
        self.assertEqual(len(response.context["page_obj"].object_list), 1)
        self.assertEqual(response.context["external_results"], [])

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

    def test_catalogo_filtra_por_tipo(self):
        pelicula = make_movie(1, "Una película", None)
        serie = Movie.objects.create(tmdb_id=2, title="Una serie", media_type="tv")

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


class MovieListInfiniteScrollTests(TestCase):
    """El catálogo ya no pagina con botones "anterior/siguiente" (llegaba a
    16 páginas): la primera carga trae un tramo y un "sensor" al final que,
    al aparecer en pantalla, pide el siguiente tramo por HTMX."""

    def setUp(self):
        for i in range(1, 30):
            make_movie(i, f"Película {i}", None)

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

    @patch("apps.movies.views.tmdb_search")
    def test_htmx_no_repite_la_busqueda_en_tmdb(self, mock_search):
        self.client.get(
            reverse("movies:list"), {"page": 1, "query": "película"}, HTTP_HX_REQUEST="true",
        )
        mock_search.assert_not_called()


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
