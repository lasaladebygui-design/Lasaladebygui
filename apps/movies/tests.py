from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

from .models import Movie, RouletteCandidate, RouletteRatingSeen, Vote


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
