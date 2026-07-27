from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User

from .models import Movie, RouletteCandidate, RouletteRatingSeen, SavedMovie, Vote
from .services import MovieAPIError


def make_user(email):
    user = User(email=email, role=User.Role.LECTOR)
    user.set_password("Testpass123!")
    user.save()
    return user


def make_movie(tmdb_id, title, imdb_rating):
    return Movie.objects.create(tmdb_id=tmdb_id, title=title, imdb_rating=imdb_rating)


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

    def test_mis_peliculas_muestra_votadas_y_guardadas(self):
        other_movie = make_movie(2, "Movie B", "7.0")
        Vote.objects.create(movie=self.movie, user=self.user, score=9)
        SavedMovie.objects.create(user=self.user, movie=other_movie)

        response = self.client.get(reverse("movies:my-movies"))
        self.assertEqual(list(response.context["votes"].values_list("movie", flat=True)), [self.movie.pk])
        self.assertEqual(list(response.context["saved"].values_list("movie", flat=True)), [other_movie.pk])


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
        self.assertIn("roulette-machine\" x-data='{", content)
        self.assertNotIn('roulette-machine" x-data="{', content)


class RouletteListTests(TestCase):
    def setUp(self):
        self.user = make_user("lector@test.local")
        self.client.login(username=self.user.email, password="Testpass123!")
        self.movie_a = make_movie(1, "A", None)
        self.movie_b = make_movie(2, "B", None)
        RouletteCandidate.objects.create(user=self.user, movie=self.movie_a)
        RouletteCandidate.objects.create(user=self.user, movie=self.movie_b)

    def test_girar_marca_como_vista_y_no_repite(self):
        seen_ids = set()
        for _ in range(2):
            response = self.client.post(reverse("movies:roulette-list-draw"))
            result = response.context["result"]
            self.assertIsNotNone(result)
            seen_ids.add(result.pk)

        self.assertEqual(seen_ids, {self.movie_a.pk, self.movie_b.pk})
        self.assertTrue(RouletteCandidate.objects.filter(user=self.user, is_seen=False).count() == 0)

        response = self.client.post(reverse("movies:roulette-list-draw"))
        self.assertIsNone(response.context["result"])

    def test_reiniciar_lista(self):
        RouletteCandidate.objects.filter(user=self.user).update(is_seen=True)
        self.client.post(reverse("movies:roulette-list-reset"))
        self.assertEqual(RouletteCandidate.objects.filter(user=self.user, is_seen=False).count(), 2)

    @patch("apps.movies.views.Movie.get_or_create_from_tmdb")
    def test_anadir_candidata_desde_busqueda(self, mock_get_or_create):
        mock_get_or_create.return_value = make_movie(99, "Nueva", None)
        response = self.client.post(reverse("movies:roulette-candidate-add", args=[99]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(RouletteCandidate.objects.filter(user=self.user, movie__tmdb_id=99).exists())

    def test_quitar_candidata_de_otro_usuario_da_404(self):
        otro = make_user("otro@test.local")
        candidate = RouletteCandidate.objects.create(user=otro, movie=make_movie(50, "C", None))
        response = self.client.post(reverse("movies:roulette-candidate-remove", args=[candidate.pk]))
        self.assertEqual(response.status_code, 404)


class MovieSearchViewTests(TestCase):
    @patch("apps.movies.views.tmdb_search")
    def test_busqueda_usa_el_servicio_tmdb(self, mock_search):
        mock_search.return_value = []
        user = make_user("lector@test.local")
        self.client.login(username=user.email, password="Testpass123!")
        response = self.client.get(reverse("movies:roulette-list-search"), {"query": "matrix"})
        self.assertEqual(response.status_code, 200)
        mock_search.assert_called_once_with("matrix")


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
        mock_search.assert_called_once_with("matrix")
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
        response = self.client.get(reverse("movies:from-tmdb", args=[603]))
        self.assertRedirects(response, reverse("movies:detail", args=[mock_get_or_create.return_value.pk]))


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
