from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.movies.models import Movie
from apps.movies.services import MovieAPIError
from apps.social.models import FriendRequest, Message

from .models import (
    Duel, DuelRecord, GameTierEntry, GameTierLevel, MovieQuote, OscarCandidate, OscarCategory, OscarVote,
    PersonalityAnswer, PersonalityCharacter, PersonalityQuestion, TriviaQuestion, TrueFalseStatement,
)


class GamesHubTests(TestCase):
    def test_juegos_enlaza_a_ruleta_y_frases(self):
        response = self.client.get(reverse("games:hub"))
        self.assertContains(response, reverse("movies:roulette-home"))
        self.assertContains(response, reverse("games:quote-game"))


class QuoteGameTests(TestCase):
    """Frases célebres vivía antes detrás del código de Top Secret; ahora es
    de acceso directo (parte de 'Juegos'), sin cuenta ni código."""

    def setUp(self):
        self.quote = MovieQuote.objects.create(
            quote="Que la Fuerza te acompañe.",
            correct_title="Star Wars",
            wrong_title_1="Regreso al futuro",
            wrong_title_2="El padrino",
        )

    def test_accesible_sin_codigo_de_top_secret_ni_cuenta(self):
        response = self.client.get(reverse("games:quote-game"))
        self.assertEqual(response.status_code, 200)

    def test_muestra_una_frase_con_tres_opciones(self):
        response = self.client.get(reverse("games:quote-game"))
        self.assertIsNotNone(response.context["quote"])
        self.assertEqual(len(response.context["options"]), 3)
        self.assertIn("Star Wars", response.context["options"])

    def test_acertar_incrementa_la_racha(self):
        response = self.client.post(reverse("games:quote-game"), {
            "quote_id": self.quote.pk, "answer": "Star Wars",
        })
        self.assertEqual(response.context["streak"], 1)

    def test_fallar_reinicia_la_racha(self):
        session = self.client.session
        session["quote_streak"] = 4
        session.save()

        response = self.client.post(reverse("games:quote-game"), {
            "quote_id": self.quote.pk, "answer": "El padrino",
        })
        self.assertEqual(response.context["streak"], 0)

    def test_racha_se_guarda_en_el_perfil_si_esta_logueado(self):
        user = User.objects.create(email="lector@test.local", role=User.Role.LECTOR)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        session = self.client.session
        session["quote_streak"] = 3
        session.save()

        self.client.post(reverse("games:quote-game"), {
            "quote_id": self.quote.pk, "answer": "El padrino",
        })
        user.refresh_from_db()
        self.assertEqual(user.quote_streak_best, 3)

    def test_no_baja_el_record_si_la_racha_es_menor(self):
        user = User.objects.create(email="lector2@test.local", role=User.Role.LECTOR, quote_streak_best=10)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        session = self.client.session
        session["quote_streak"] = 2
        session.save()

        self.client.post(reverse("games:quote-game"), {
            "quote_id": self.quote.pk, "answer": "El padrino",
        })
        user.refresh_from_db()
        self.assertEqual(user.quote_streak_best, 10)

    def test_fallar_muestra_pantalla_de_fin_de_partida(self):
        session = self.client.session
        session["quote_streak"] = 3
        session.save()

        response = self.client.post(reverse("games:quote-game"), {
            "quote_id": self.quote.pk, "answer": "El padrino",
        })
        self.assertTrue(response.context["game_over"])
        self.assertEqual(response.context["final_streak"], 3)
        self.assertEqual(response.context["wrong_answer_title"], "Star Wars")
        self.assertIsNone(response.context["quote"])

    def test_fallar_con_racha_record_marca_nuevo_record(self):
        user = User.objects.create(email="lector3@test.local", role=User.Role.LECTOR, quote_streak_best=2)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        session = self.client.session
        session["quote_streak"] = 5
        session.save()

        response = self.client.post(reverse("games:quote-game"), {
            "quote_id": self.quote.pk, "answer": "El padrino",
        })
        self.assertTrue(response.context["is_new_record"])

    def test_fallar_sin_superar_el_record_no_lo_marca(self):
        user = User.objects.create(email="lector4@test.local", role=User.Role.LECTOR, quote_streak_best=10)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        session = self.client.session
        session["quote_streak"] = 2
        session.save()

        response = self.client.post(reverse("games:quote-game"), {
            "quote_id": self.quote.pk, "answer": "El padrino",
        })
        self.assertFalse(response.context["is_new_record"])

    def test_acertar_no_muestra_pantalla_de_fin_de_partida(self):
        response = self.client.post(reverse("games:quote-game"), {
            "quote_id": self.quote.pk, "answer": "Star Wars",
        })
        self.assertFalse(response.context["game_over"])
        self.assertIsNotNone(response.context["quote"])


class RatingDuelGameTests(TestCase):
    """'Cuál está mejor valorada': higher/lower con la nota IMDb del
    catálogo. Películas y series van cada una con su propia racha. Cada
    ronda se juega en dos pasos: elegir -> ver el resultado en color ->
    "Siguiente" (round_result en sesión/contexto)."""

    def setUp(self):
        self.movie_a = Movie.objects.create(tmdb_id=1, title="Peli A", media_type="movie", imdb_rating="8.5")
        self.movie_b = Movie.objects.create(tmdb_id=2, title="Peli B", media_type="movie", imdb_rating="6.0")
        self.tv_a = Movie.objects.create(tmdb_id=1, title="Serie A", media_type="tv", imdb_rating="9.0")
        self.tv_b = Movie.objects.create(tmdb_id=2, title="Serie B", media_type="tv", imdb_rating="7.0")

    def test_sin_tipo_elegido_muestra_pantalla_de_inicio(self):
        response = self.client.get(reverse("games:rating-duel"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "games/rating_duel_start.html")

    def test_accesible_sin_cuenta_una_vez_elegido_el_tipo(self):
        response = self.client.get(reverse("games:rating-duel"), {"type": "movie"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["media_type"], "movie")

    def test_muestra_dos_peliculas_del_tipo_elegido(self):
        response = self.client.get(reverse("games:rating-duel"), {"type": "movie"})
        self.assertIsNotNone(response.context["left"])
        self.assertIsNotNone(response.context["right"])
        self.assertEqual(response.context["left"].media_type, "movie")

    def test_tipo_series_usa_solo_series(self):
        response = self.client.get(reverse("games:rating-duel"), {"type": "tv"})
        self.assertEqual(response.context["media_type"], "tv")
        self.assertEqual(response.context["left"].media_type, "tv")
        self.assertEqual(response.context["right"].media_type, "tv")

    def test_sin_suficientes_peliculas_lo_indica(self):
        Movie.objects.filter(media_type="movie").delete()
        response = self.client.get(reverse("games:rating-duel"), {"type": "movie"})
        self.assertIsNone(response.context["left"])
        self.assertContains(response, "Todavía no hay suficientes")

    def test_acertar_la_mas_valorada_incrementa_la_racha_y_se_ve_en_verde(self):
        response = self.client.post(reverse("games:rating-duel"), {
            "type": "movie", "left_id": self.movie_a.pk, "right_id": self.movie_b.pk, "choice": "left",
        })
        self.assertEqual(response.context["streak"], 1)
        result = response.context["round_result"]
        self.assertTrue(result["correct"])
        self.assertFalse(result["game_over"])
        self.assertEqual(result["winner_side"], "left")
        self.assertContains(response, "rating-duel__card--correct")

    def test_fallar_reinicia_la_racha_y_muestra_fin_de_partida(self):
        session = self.client.session
        session["rating_duel_streak_movie"] = 3
        session.save()

        response = self.client.post(reverse("games:rating-duel"), {
            "type": "movie", "left_id": self.movie_a.pk, "right_id": self.movie_b.pk, "choice": "right",
        })
        self.assertEqual(response.context["streak"], 0)
        result = response.context["round_result"]
        self.assertTrue(result["game_over"])
        self.assertEqual(result["final_streak"], 3)
        self.assertContains(response, "rating-duel__card--wrong")

    def test_siguiente_ronda_limpia_el_resultado_y_sigue_jugando(self):
        self.client.post(reverse("games:rating-duel"), {
            "type": "movie", "left_id": self.movie_a.pk, "right_id": self.movie_b.pk, "choice": "left",
        })
        response = self.client.post(reverse("games:rating-duel"), {"type": "movie", "advance": "1"})
        self.assertIsNone(response.context["round_result"])
        self.assertIsNotNone(response.context["left"])

    def test_modo_anonimo_no_muestra_la_nota_en_el_resultado(self):
        response = self.client.post(reverse("games:rating-duel"), {
            "type": "movie", "anon": "1", "left_id": self.movie_a.pk, "right_id": self.movie_b.pk, "choice": "left",
        })
        self.assertNotContains(response, "⭐ 8.5")
        self.assertNotContains(response, "⭐ 6.0")

    def test_racha_de_series_es_independiente_de_peliculas(self):
        session = self.client.session
        session["rating_duel_streak_movie"] = 5
        session.save()

        response = self.client.get(reverse("games:rating-duel"), {"type": "tv"})
        self.assertEqual(response.context["streak"], 0)

    def test_racha_se_guarda_en_el_perfil_si_esta_logueado(self):
        user = User.objects.create(email="rating_duel@test.local", role=User.Role.LECTOR)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        session = self.client.session
        session["rating_duel_streak_movie"] = 4
        session.save()

        self.client.post(reverse("games:rating-duel"), {
            "type": "movie", "left_id": self.movie_a.pk, "right_id": self.movie_b.pk, "choice": "right",
        })
        user.refresh_from_db()
        self.assertEqual(user.rating_duel_streak_best_movie, 4)
        self.assertEqual(user.rating_duel_streak_best_tv, 0)

    def test_no_repite_la_misma_pelicula_mas_del_tope_sorteado(self):
        Movie.objects.filter(media_type="movie").delete()
        movies = [
            Movie.objects.create(tmdb_id=i, title=f"Peli {i}", media_type="movie", imdb_rating=str(5 + i * 0.1))
            for i in range(1, 6)
        ]
        session = self.client.session
        session["rating_duel_seen_movie"] = {str(movies[0].pk): 2}
        session["rating_duel_max_repeats_movie"] = 2
        session.save()

        response = self.client.get(reverse("games:rating-duel"), {"type": "movie"})
        seen_ids = {response.context["left"].pk, response.context["right"].pk}
        self.assertNotIn(movies[0].pk, seen_ids)

    def test_el_tope_de_repeticiones_se_sortea_entre_uno_y_tres(self):
        response = self.client.get(reverse("games:rating-duel"), {"type": "movie"})
        self.assertIn(self.client.session["rating_duel_max_repeats_movie"], (1, 2, 3))

    def test_fallar_sortea_un_nuevo_tope_de_repeticiones_para_la_siguiente_partida(self):
        session = self.client.session
        session["rating_duel_max_repeats_movie"] = 3
        session.save()

        self.client.post(reverse("games:rating-duel"), {
            "type": "movie", "left_id": self.movie_a.pk, "right_id": self.movie_b.pk, "choice": "right",
        })
        self.assertNotIn("rating_duel_max_repeats_movie", self.client.session)

    def test_la_campeona_no_se_repite_mas_de_dos_rondas_seguidas(self):
        champion = Movie.objects.create(tmdb_id=50, title="Campeona", media_type="movie", imdb_rating="9.5")
        challenger_1 = Movie.objects.create(tmdb_id=51, title="Retadora 1", media_type="movie", imdb_rating="5.0")
        challenger_2 = Movie.objects.create(tmdb_id=52, title="Retadora 2", media_type="movie", imdb_rating="5.1")
        Movie.objects.create(tmdb_id=53, title="Retadora 3", media_type="movie", imdb_rating="5.2")

        session = self.client.session
        session["rating_duel_max_repeats_movie"] = 3  # fuera del experimento: que no interfiera el otro tope
        session["rating_duel_champion_id_movie"] = champion.pk
        session["rating_duel_champion_streak_movie"] = 1
        session.save()

        # Ronda 1: la campeona defiende el puesto (1ª defensa -> streak 2).
        self.client.post(reverse("games:rating-duel"), {
            "type": "movie", "left_id": champion.pk, "right_id": challenger_1.pk, "choice": "left",
        })
        self.assertEqual(self.client.session["rating_duel_champion_streak_movie"], 2)
        self.assertEqual(self.client.session["rating_duel_champion_id_movie"], champion.pk)
        self.client.post(reverse("games:rating-duel"), {"type": "movie", "advance": "1"})

        # Ronda 2: la campeona defiende otra vez -> llega al tope y se jubila.
        self.client.post(reverse("games:rating-duel"), {
            "type": "movie", "left_id": champion.pk, "right_id": challenger_2.pk, "choice": "left",
        })
        self.assertNotIn("rating_duel_champion_id_movie", self.client.session)
        self.assertNotIn("rating_duel_champion_streak_movie", self.client.session)

        # La racha del juego sigue intacta — no se ha fallado ninguna ronda.
        self.assertEqual(self.client.session["rating_duel_streak_movie"], 2)


class RevenueDuelGameTests(TestCase):
    """'Cuál recaudó más': mismo higher/lower que Cuál está mejor valorada,
    pero con la recaudación de TMDb en vez de la nota IMDb — solo
    películas, sin pantalla de tipo (no hay recaudación de series)."""

    def setUp(self):
        self.movie_a = Movie.objects.create(tmdb_id=1, title="Peli A", media_type="movie", revenue=800_000_000)
        self.movie_b = Movie.objects.create(tmdb_id=2, title="Peli B", media_type="movie", revenue=100_000_000)

    def test_accesible_directamente_sin_pantalla_de_inicio(self):
        response = self.client.get(reverse("games:revenue-duel"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["left"])
        self.assertIsNotNone(response.context["right"])

    def test_solo_usa_peliculas_con_recaudacion_conocida(self):
        Movie.objects.create(tmdb_id=3, title="Sin recaudación", media_type="movie", revenue=None)
        Movie.objects.create(tmdb_id=1, title="Serie", media_type="tv", revenue=None)
        response = self.client.get(reverse("games:revenue-duel"))
        seen = {response.context["left"].pk, response.context["right"].pk}
        self.assertTrue(seen.issubset({self.movie_a.pk, self.movie_b.pk}))

    def test_acertar_incrementa_la_racha(self):
        response = self.client.post(reverse("games:revenue-duel"), {
            "left_id": self.movie_a.pk, "right_id": self.movie_b.pk, "choice": "left",
        })
        self.assertEqual(response.context["round_result"]["correct"], True)
        self.assertEqual(self.client.session["revenue_duel_streak"], 1)

    def test_fallar_reinicia_la_racha_y_guarda_el_record(self):
        user = User.objects.create(email="taquilla@test.local", role=User.Role.LECTOR)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        session = self.client.session
        session["revenue_duel_streak"] = 4
        session.save()

        response = self.client.post(reverse("games:revenue-duel"), {
            "left_id": self.movie_a.pk, "right_id": self.movie_b.pk, "choice": "right",
        })
        self.assertTrue(response.context["round_result"]["game_over"])
        user.refresh_from_db()
        self.assertEqual(user.revenue_duel_streak_best, 4)

    def test_muestra_la_recaudacion_formateada(self):
        response = self.client.post(reverse("games:revenue-duel"), {
            "left_id": self.movie_a.pk, "right_id": self.movie_b.pk, "choice": "left",
        })
        self.assertEqual(response.context["round_result"]["left_revenue"], "$800.000.000")


class TriviaGameTests(TestCase):
    """Trivial, Malas descripciones y Cuál tiene al actor/actriz comparten
    el mismo motor genérico (_trivia_game) que Frases célebres — aquí solo
    se comprueba que cada categoría queda bien aislada de las demás."""

    def setUp(self):
        self.trivia = TriviaQuestion.objects.create(
            category=TriviaQuestion.Category.TRIVIA, prompt="¿Quién dirigió Origen?",
            correct_answer="Christopher Nolan", wrong_answer_1="Steven Spielberg", wrong_answer_2="Denis Villeneuve",
        )
        self.bad_description = TriviaQuestion.objects.create(
            category=TriviaQuestion.Category.BAD_DESCRIPTION, prompt="Un pez muy nervioso busca a su hijo.",
            correct_answer="Buscando a Nemo", wrong_answer_1="Buscando a Dory", wrong_answer_2="La vida de Pi",
        )
        self.actor = TriviaQuestion.objects.create(
            category=TriviaQuestion.Category.ACTOR, prompt="Robert Downey Jr.",
            correct_answer="Iron Man", wrong_answer_1="Batman Begins", wrong_answer_2="El hombre de acero",
        )

    def test_trivial_muestra_solo_preguntas_de_su_categoria(self):
        response = self.client.get(reverse("games:trivia-game"))
        self.assertEqual(response.context["question"], self.trivia)

    def test_trivial_acertar_incrementa_la_racha(self):
        # Segunda pregunta para que el pool no se agote con un solo acierto
        # (si no, entraría en juego la pantalla de victoria, no la racha).
        TriviaQuestion.objects.create(
            category=TriviaQuestion.Category.TRIVIA, prompt="¿Otra pregunta?",
            correct_answer="A", wrong_answer_1="B", wrong_answer_2="C",
        )
        response = self.client.post(reverse("games:trivia-game"), {
            "question_id": self.trivia.pk, "answer": "Christopher Nolan",
        })
        self.assertEqual(response.context["streak"], 1)

    def test_trivial_fallar_reinicia_la_racha_y_guarda_el_record(self):
        user = User.objects.create(email="trivial@test.local", role=User.Role.LECTOR)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        session = self.client.session
        session["trivia_streak_trivia"] = 4
        session.save()

        response = self.client.post(reverse("games:trivia-game"), {
            "question_id": self.trivia.pk, "answer": "nada que ver",
        })
        self.assertEqual(response.context["streak"], 0)
        self.assertTrue(response.context["game_over"])
        user.refresh_from_db()
        self.assertEqual(user.trivia_streak_best, 4)

    def test_no_repite_pregunta_ya_vista_en_la_misma_partida(self):
        trivia_2 = TriviaQuestion.objects.create(
            category=TriviaQuestion.Category.TRIVIA, prompt="¿Otra pregunta?",
            correct_answer="A", wrong_answer_1="B", wrong_answer_2="C",
        )
        self.client.post(reverse("games:trivia-game"), {
            "question_id": self.trivia.pk, "answer": "Christopher Nolan",
        })
        self.assertEqual(self.client.session["trivia_seen_trivia"], [self.trivia.pk])
        response = self.client.get(reverse("games:trivia-game"))
        self.assertEqual(response.context["question"], trivia_2)

    def test_agotar_el_pool_sin_fallar_muestra_pantalla_de_victoria(self):
        # setUp solo tiene una pregunta de categoría "trivia": acertarla ya
        # agota el pool en la misma respuesta, sin necesidad de un GET aparte.
        response = self.client.post(reverse("games:trivia-game"), {
            "question_id": self.trivia.pk, "answer": "Christopher Nolan",
        })
        self.assertTrue(response.context["game_won"])
        self.assertEqual(response.context["final_streak"], 1)
        self.assertIsNone(response.context["question"])
        self.assertNotIn("trivia_seen_trivia", self.client.session)

    def test_ganar_guarda_el_record(self):
        user = User.objects.create(email="ganador@test.local", role=User.Role.LECTOR)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        self.client.post(reverse("games:trivia-game"), {
            "question_id": self.trivia.pk, "answer": "Christopher Nolan",
        })
        self.client.get(reverse("games:trivia-game"))
        user.refresh_from_db()
        self.assertEqual(user.trivia_streak_best, 1)

    def test_malas_descripciones_muestra_solo_su_categoria(self):
        response = self.client.get(reverse("games:bad-description-game"))
        self.assertEqual(response.context["question"], self.bad_description)

    def test_actor_muestra_solo_su_categoria_y_su_racha_es_independiente(self):
        response = self.client.get(reverse("games:actor-game"))
        self.assertEqual(response.context["question"], self.actor)

        user = User.objects.create(email="actor@test.local", role=User.Role.LECTOR)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")
        self.client.post(reverse("games:actor-game"), {
            "question_id": self.actor.pk, "answer": "El hombre de acero",
        })
        user.refresh_from_db()
        self.assertEqual(user.actor_streak_best, 0)
        self.assertEqual(user.trivia_streak_best, 0)


class EmojiGameTests(TestCase):
    """A diferencia del resto, aquí se revela un emoji a la vez: fallar solo
    rompe la racha si ya no quedan más emojis por revelar."""

    def setUp(self):
        self.question = TriviaQuestion.objects.create(
            category=TriviaQuestion.Category.EMOJI, prompt="🦁 👑 🌍",
            correct_answer="El rey león", wrong_answer_1="Madagascar", wrong_answer_2="Tarzán",
        )

    def test_al_empezar_solo_se_revela_el_primer_emoji(self):
        response = self.client.get(reverse("games:emoji-game"))
        self.assertEqual(response.context["revealed_emojis"], "🦁")
        self.assertEqual(response.context["reveal_count"], 1)
        self.assertEqual(response.context["total_emojis"], 3)

    def test_fallar_con_pistas_restantes_no_rompe_la_racha_y_revela_otra(self):
        session = self.client.session
        session["trivia_streak_emoji"] = 2
        session.save()

        response = self.client.post(reverse("games:emoji-game"), {
            "question_id": self.question.pk, "answer": "Madagascar",
        })
        self.assertEqual(response.context["streak"], 2)
        self.assertFalse(response.context["game_over"])
        self.assertTrue(response.context["just_wrong"])
        self.assertEqual(response.context["revealed_emojis"], "🦁 👑")
        self.assertEqual(response.context["question"], self.question)

    def test_fallar_sin_pistas_restantes_rompe_la_racha(self):
        session = self.client.session
        session["trivia_streak_emoji"] = 2
        session["emoji_current_question_id"] = self.question.pk
        session["emoji_reveal_count"] = 3
        session.save()

        response = self.client.post(reverse("games:emoji-game"), {
            "question_id": self.question.pk, "answer": "Madagascar",
        })
        self.assertEqual(response.context["streak"], 0)
        self.assertTrue(response.context["game_over"])
        self.assertEqual(response.context["final_streak"], 2)
        self.assertEqual(response.context["wrong_answer"], "El rey león")

    def test_agotar_el_pool_sin_fallar_muestra_pantalla_de_victoria(self):
        response = self.client.post(reverse("games:emoji-game"), {
            "question_id": self.question.pk, "answer": "El rey león",
        })
        self.assertTrue(response.context["game_won"])
        self.assertEqual(response.context["final_streak"], 1)
        self.assertIsNone(response.context["question"])
        self.assertNotIn("trivia_seen_emoji", self.client.session)

    def test_acertar_con_pistas_a_medias_incrementa_la_racha_y_pasa_de_pregunta(self):
        # Segunda pregunta para que el pool no se agote con este acierto
        # (si no, entraría en juego la pantalla de victoria, no la racha).
        TriviaQuestion.objects.create(
            category=TriviaQuestion.Category.EMOJI, prompt="🕷️ 🧑",
            correct_answer="Spider-Man", wrong_answer_1="Venom", wrong_answer_2="Los 4 Fantásticos",
        )
        session = self.client.session
        session["emoji_current_question_id"] = self.question.pk
        session["emoji_reveal_count"] = 2
        session.save()

        response = self.client.post(reverse("games:emoji-game"), {
            "question_id": self.question.pk, "answer": "El rey león",
        })
        self.assertEqual(response.context["streak"], 1)
        # Acertar pasa a una pregunta nueva, siempre con la primera pista
        # (nunca sigue en la misma pregunta con las pistas ya reveladas).
        self.assertEqual(self.client.session["emoji_reveal_count"], 1)


class TrueFalseGameTests(TestCase):
    def setUp(self):
        self.true_statement = TrueFalseStatement.objects.create(
            statement="'Titanic' ganó 11 premios Óscar.", is_true=True,
        )

    def test_muestra_una_afirmacion(self):
        response = self.client.get(reverse("games:true-false-game"))
        self.assertEqual(response.context["statement"], self.true_statement)

    def test_acertar_incrementa_la_racha(self):
        # Segunda afirmación para que el pool no se agote con este acierto.
        TrueFalseStatement.objects.create(statement="'Matrix' está protagonizada por Brad Pitt.", is_true=False)
        response = self.client.post(reverse("games:true-false-game"), {
            "statement_id": self.true_statement.pk, "answer": "true",
        })
        self.assertEqual(response.context["streak"], 1)

    def test_agotar_el_pool_sin_fallar_muestra_pantalla_de_victoria(self):
        response = self.client.post(reverse("games:true-false-game"), {
            "statement_id": self.true_statement.pk, "answer": "true",
        })
        self.assertTrue(response.context["game_won"])
        self.assertEqual(response.context["final_streak"], 1)
        self.assertIsNone(response.context["statement"])
        self.assertNotIn("true_false_seen", self.client.session)

    def test_no_repite_afirmacion_ya_vista_en_la_misma_partida(self):
        statement_2 = TrueFalseStatement.objects.create(
            statement="'Matrix' está protagonizada por Brad Pitt.", is_true=False,
        )
        self.client.post(reverse("games:true-false-game"), {
            "statement_id": self.true_statement.pk, "answer": "true",
        })
        response = self.client.get(reverse("games:true-false-game"))
        self.assertEqual(response.context["statement"], statement_2)

    def test_fallar_reinicia_la_racha_y_guarda_el_record(self):
        user = User.objects.create(email="vf@test.local", role=User.Role.LECTOR)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")

        session = self.client.session
        session["true_false_streak"] = 3
        session.save()

        response = self.client.post(reverse("games:true-false-game"), {
            "statement_id": self.true_statement.pk, "answer": "false",
        })
        self.assertEqual(response.context["streak"], 0)
        self.assertTrue(response.context["game_over"])
        user.refresh_from_db()
        self.assertEqual(user.true_false_streak_best, 3)


class PersonalityQuizTests(TestCase):
    """'Qué personaje eres': preguntas en orden fijo, cada respuesta suma un
    punto a un personaje, gana el que más puntos tenga al final. No hay
    racha ni fallo — es un test de personalidad, no un juego de acertar."""

    def setUp(self):
        self.char_a = PersonalityCharacter.objects.create(name="Jinx", description="Caos.")
        self.char_b = PersonalityCharacter.objects.create(name="Miranda Priestly", description="Ambición.")
        self.q1 = PersonalityQuestion.objects.create(text="¿Pregunta 1?", order=0)
        self.q1_a = PersonalityAnswer.objects.create(question=self.q1, text="Opción caótica", character=self.char_a)
        self.q1_b = PersonalityAnswer.objects.create(question=self.q1, text="Opción ambiciosa", character=self.char_b)
        self.q2 = PersonalityQuestion.objects.create(text="¿Pregunta 2?", order=1)
        self.q2_a = PersonalityAnswer.objects.create(question=self.q2, text="Opción caótica 2", character=self.char_a)
        self.q2_b = PersonalityAnswer.objects.create(question=self.q2, text="Opción ambiciosa 2", character=self.char_b)

    def test_una_sesion_con_formato_antiguo_no_revienta(self):
        """Antes se guardaba un contador (int) por personaje; ahora se
        guarda la lista de respuestas elegidas. Una sesión vieja con el
        formato antiguo no debe reventar, solo descartarse."""
        session = self.client.session
        session["personality_quiz_scores"] = {str(self.char_a.pk): 3}
        session["personality_quiz_index"] = 1
        session.save()

        response = self.client.get(reverse("games:personality-quiz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["question"], self.q1)

    def test_empieza_mostrando_la_primera_pregunta(self):
        response = self.client.get(reverse("games:personality-quiz"))
        self.assertEqual(response.context["question"], self.q1)
        self.assertEqual(response.context["progress"], 1)
        self.assertEqual(response.context["total"], 2)

    def test_responder_avanza_a_la_siguiente_pregunta(self):
        response = self.client.post(reverse("games:personality-quiz"), {"answer_id": self.q1_a.pk})
        self.assertEqual(response.context["question"], self.q2)
        self.assertEqual(response.context["progress"], 2)

    def test_responder_todas_muestra_el_resultado_con_mas_puntos(self):
        self.client.post(reverse("games:personality-quiz"), {"answer_id": self.q1_a.pk})
        response = self.client.post(reverse("games:personality-quiz"), {"answer_id": self.q2_a.pk})
        self.assertTemplateUsed(response, "games/personality_quiz_result.html")
        self.assertEqual(response.context["character"], self.char_a)

    def test_el_resultado_explica_con_tus_propias_respuestas(self):
        self.client.post(reverse("games:personality-quiz"), {"answer_id": self.q1_a.pk})
        response = self.client.post(reverse("games:personality-quiz"), {"answer_id": self.q2_a.pk})
        self.assertEqual(response.context["why"], ["Opción caótica", "Opción caótica 2"])
        self.assertContains(response, "Opción caótica 2")

    def test_repetir_el_test_reinicia_el_progreso(self):
        self.client.post(reverse("games:personality-quiz"), {"answer_id": self.q1_a.pk})
        self.client.post(reverse("games:personality-quiz"), {"answer_id": self.q2_a.pk})
        response = self.client.post(reverse("games:personality-quiz"), {"restart": "1"}, follow=True)
        self.assertEqual(response.context["question"], self.q1)
        self.assertNotIn("personality_quiz_scores", self.client.session)


class SeedPersonalityQuizCommandTests(TestCase):
    """El comando crea los 12 personajes (Nikki Freeman en vez de Iron Man,
    tras el cambio pedido) y, si hay TMDB_API_KEY, rellena la foto de perfil
    del actor/actriz de cada uno (salvo Nikki, sin actor confirmado)."""

    @override_settings(TMDB_API_KEY="")
    def test_crea_nikki_freeman_no_iron_man(self):
        call_command("seed_personality_quiz")
        self.assertTrue(PersonalityCharacter.objects.filter(name="Nikki Freeman").exists())
        self.assertFalse(PersonalityCharacter.objects.filter(name__icontains="Iron Man").exists())
        self.assertEqual(PersonalityCharacter.objects.count(), 12)
        self.assertEqual(PersonalityQuestion.objects.count(), 18)

    @override_settings(TMDB_API_KEY="")
    def test_reejecutar_el_comando_no_duplica_preguntas(self):
        # Bug real: al reescribir el texto de las 18 preguntas (a decisiones
        # de película) se quedaban las 18 antiguas sueltas en la base de
        # datos junto a las 18 nuevas — 36 en vez de 18. get_or_create por
        # texto nunca las borra solo, hace falta podarlas explícitamente.
        call_command("seed_personality_quiz")
        call_command("seed_personality_quiz")
        self.assertEqual(PersonalityQuestion.objects.count(), 18)

    @override_settings(TMDB_API_KEY="")
    def test_poda_preguntas_de_una_version_anterior_del_cuestionario(self):
        old_question = PersonalityQuestion.objects.create(text="Un compañero de trabajo se lleva el mérito. ¿Qué haces?")
        call_command("seed_personality_quiz")
        self.assertFalse(PersonalityQuestion.objects.filter(pk=old_question.pk).exists())
        self.assertEqual(PersonalityQuestion.objects.count(), 18)

    @override_settings(TMDB_API_KEY="")
    def test_poda_personajes_y_respuestas_de_repartos_anteriores(self):
        """Simula lo que le pasó en real: la BD ya tenía a Tony Stark (Iron
        Man) de una versión anterior del reparto (antes de cambiarlo por
        Nikki Freeman) — el comando debe podarlo a él y a sus respuestas
        huérfanas, no dejarlos sueltos junto a los nuevos."""
        old_iron_man = PersonalityCharacter.objects.create(name="Tony Stark (Iron Man)", description="Viejo.")
        question = PersonalityQuestion.objects.create(
            text="Un atraco perfecto se tuerce en el último segundo y un miembro del equipo se queda atrás. ¿Qué haces?",
        )
        PersonalityAnswer.objects.create(
            question=question, text="Busco la manera de tenerlo todo, aunque sea complicado", character=old_iron_man,
        )

        call_command("seed_personality_quiz")

        self.assertFalse(PersonalityCharacter.objects.filter(name__icontains="Iron Man").exists())
        question.refresh_from_db()
        self.assertEqual(question.answers.count(), 4)
        self.assertFalse(question.answers.filter(text__icontains="Busco la manera de tenerlo todo").exists())

    @override_settings(TMDB_API_KEY="")
    def test_sin_api_key_no_rellena_fotos(self):
        call_command("seed_personality_quiz")
        self.assertFalse(PersonalityCharacter.objects.exclude(image_url="").exists())

    @override_settings(TMDB_API_KEY="fake-key")
    @patch("apps.games.management.commands.seed_personality_quiz.tmdb_search_person")
    def test_con_api_key_rellena_fotos_de_personajes_mapeados(self, mock_search):
        from apps.movies.services import TMDbPersonResult

        mock_search.return_value = [TMDbPersonResult(tmdb_id=1, name="Actor", profile_path="/foto.jpg")]
        call_command("seed_personality_quiz")

        jinx = PersonalityCharacter.objects.get(name="Jinx")
        self.assertIn("/foto.jpg", jinx.image_url)
        nikki = PersonalityCharacter.objects.get(name="Nikki Freeman")
        self.assertEqual(nikki.image_url, "")


class DuelTests(TestCase):
    """Duelo: los dos ven la misma pregunta a la vez y avanzan juntos ronda
    a ronda; en cuanto uno falla, se acaba para los dos. Empieza como
    invitación (PENDING) hasta que el retado la acepta."""

    def setUp(self):
        self.quotes = [
            MovieQuote.objects.create(
                quote=f"Frase número {i}", correct_title=f"Película {i}",
                wrong_title_1="Otra", wrong_title_2="Otra más",
            )
            for i in range(10)
        ]
        self.alice = User.objects.create(email="alice@test.local", role=User.Role.LECTOR, username="alice")
        self.alice.set_password("Testpass123!")
        self.alice.save()
        self.bob = User.objects.create(email="bob@test.local", role=User.Role.LECTOR, username="bob")
        self.bob.set_password("Testpass123!")
        self.bob.save()
        FriendRequest.objects.create(from_user=self.alice, to_user=self.bob, accepted=True)

    def test_no_se_puede_retar_a_quien_no_es_amigo(self):
        carol = User.objects.create(email="carol@test.local", role=User.Role.LECTOR, username="carol")
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-invite", kwargs={"username": carol.username}))
        self.assertFalse(Duel.objects.exists())

    def test_retar_a_un_amigo_crea_un_duelo_pendiente(self):
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.post(reverse("games:duel-invite", kwargs={"username": self.bob.username}))
        duel = Duel.objects.get()
        self.assertEqual(duel.challenger, self.alice)
        self.assertEqual(duel.opponent, self.bob)
        self.assertEqual(duel.status, Duel.Status.PENDING)
        self.assertEqual(len(duel.round_ids), 1)
        self.assertRedirects(response, reverse("games:duel-detail", kwargs={"pk": duel.pk}))

    def test_retar_permite_elegir_el_juego(self):
        TriviaQuestion.objects.create(
            category=TriviaQuestion.Category.TRIVIA, prompt="¿Pregunta?",
            correct_answer="A", wrong_answer_1="B", wrong_answer_2="C",
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-invite", kwargs={"username": self.bob.username}), {"game": "trivia"})
        duel = Duel.objects.get()
        self.assertEqual(duel.game, "trivia")

    def test_retar_sin_juego_indicado_usa_frases_celebres_por_defecto(self):
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-invite", kwargs={"username": self.bob.username}))
        duel = Duel.objects.get()
        self.assertEqual(duel.game, Duel.Game.QUOTES)

    def test_jugar_un_duelo_de_trivial_funciona_igual_que_el_de_frases(self):
        question = TriviaQuestion.objects.create(
            category=TriviaQuestion.Category.TRIVIA, prompt="¿Quién dirigió Origen?",
            correct_answer="Nolan", wrong_answer_1="Spielberg", wrong_answer_2="Scott",
        )
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, game=Duel.Game.TRIVIA,
            round_ids=[question.pk], status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertEqual(response.context["prompt"], "¿Quién dirigió Origen?")

        response = self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "round_id": question.pk, "answer": "Nolan",
        })
        duel.refresh_from_db()
        self.assertEqual(duel.challenger_streak, 1)

    def test_jugar_un_duelo_de_verdadero_o_falso(self):
        statement = TrueFalseStatement.objects.create(statement="'Titanic' ganó 11 Óscar.", is_true=True)
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, game=Duel.Game.TRUE_FALSE,
            round_ids=[statement.pk], status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertEqual(response.context["prompt"], "'Titanic' ganó 11 Óscar.")
        self.assertEqual(set(response.context["options"]), {"Verdadero", "Falso"})

        response = self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "round_id": statement.pk, "answer": "Verdadero",
        })
        duel.refresh_from_db()
        self.assertEqual(duel.challenger_streak, 1)

    def test_jugar_un_duelo_de_emoji_muestra_todos_los_emojis_de_golpe(self):
        question = TriviaQuestion.objects.create(
            category=TriviaQuestion.Category.EMOJI, prompt="🦁 👑 🌍",
            correct_answer="El rey león", wrong_answer_1="Madagascar", wrong_answer_2="Tarzán",
        )
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, game=Duel.Game.EMOJI,
            round_ids=[question.pk], status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertEqual(response.context["prompt"], "🦁 👑 🌍")

    def test_el_retador_ve_pantalla_de_espera_mientras_esta_pendiente(self):
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-invite", kwargs={"username": self.bob.username}))
        duel = Duel.objects.get()

        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertContains(response, "Esperando a que")

    def test_el_retado_puede_aceptar_el_duelo(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
        )
        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-accept", kwargs={"pk": duel.pk}))
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.Status.ACTIVE)

    def test_el_retado_puede_rechazar_el_duelo(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
        )
        self.client.login(username="bob@test.local", password="Testpass123!")
        response = self.client.post(reverse("games:duel-decline", kwargs={"pk": duel.pk}))
        self.assertRedirects(response, reverse("games:hub"))
        self.assertFalse(Duel.objects.filter(pk=duel.pk).exists())

    def test_rechazar_el_duelo_borra_el_mensaje_de_invitacion_en_social(self):
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-invite", kwargs={"username": self.bob.username}))
        duel = Duel.objects.get()
        self.client.logout()

        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-decline", kwargs={"pk": duel.pk}))
        self.assertFalse(Message.objects.filter(sender=self.alice, recipient=self.bob).exists())

    def test_el_retador_no_puede_aceptar_su_propio_duelo(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.post(reverse("games:duel-accept", kwargs={"pk": duel.pk}))
        self.assertEqual(response.status_code, 404)

    def test_retar_a_un_amigo_le_manda_el_enlace_por_social(self):
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-invite", kwargs={"username": self.bob.username}))
        duel = Duel.objects.get()

        message = Message.objects.get(sender=self.alice, recipient=self.bob)
        self.assertIn(reverse("games:duel-detail", kwargs={"pk": duel.pk}), message.body)

    def test_el_hub_de_juegos_lista_amigos_para_desafiar(self):
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:hub"))
        self.assertContains(response, "bob")
        self.assertContains(response, "Jugar con amigos")

    def test_el_hub_de_juegos_sin_amigos_lo_indica(self):
        self.client.login(username="bob@test.local", password="Testpass123!")
        FriendRequest.objects.filter(from_user=self.alice, to_user=self.bob).delete()
        response = self.client.get(reverse("games:hub"))
        self.assertContains(response, "Todavía no tienes amigos para retar")

    def test_los_dos_ven_la_misma_pregunta_a_la_vez(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertEqual(response.context["round_id"], self.quotes[0].pk)

        self.client.login(username="bob@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertEqual(response.context["round_id"], self.quotes[0].pk)

    def test_responder_bien_y_esperar_al_rival(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "round_id": self.quotes[0].pk, "answer": "Película 0",
        })
        duel.refresh_from_db()
        self.assertEqual(duel.challenger_streak, 1)
        self.assertTrue(duel.challenger_answered)
        self.assertEqual(duel.current_index, 0)
        self.assertTemplateUsed(response, "games/duel_waiting.html")

    def test_cuando_los_dos_aciertan_avanza_la_ronda_para_los_dos(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "round_id": self.quotes[0].pk, "answer": "Película 0",
        })
        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "round_id": self.quotes[0].pk, "answer": "Película 0",
        })
        duel.refresh_from_db()
        self.assertEqual(duel.current_index, 1)
        self.assertFalse(duel.challenger_answered)
        self.assertFalse(duel.opponent_answered)
        self.assertEqual(duel.challenger_streak, 1)
        self.assertEqual(duel.opponent_streak, 1)

    def test_no_hay_tanda_fija_se_juega_hasta_fallar(self):
        """Si los dos aciertan y ya no quedan más frases guardadas en el
        duelo, se añade una nueva en vez de terminar el duelo — no hay
        límite de preguntas, solo el fallo lo acaba."""
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[self.quotes[0].pk],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "round_id": self.quotes[0].pk, "answer": "Película 0",
        })
        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "round_id": self.quotes[0].pk, "answer": "Película 0",
        })
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.Status.ACTIVE)
        self.assertEqual(duel.current_index, 1)
        self.assertEqual(len(duel.round_ids), 2)

    def test_no_muestra_pregunta_x_de_n(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertNotContains(response, " de 10")

    def test_terminar_el_duelo_actualiza_el_marcador(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "round_id": self.quotes[0].pk, "answer": "Otra",
        })
        record = DuelRecord.get_for(self.alice, self.bob)
        self.assertIsNotNone(record)
        self.assertEqual(record.wins_for(self.bob), 1)
        self.assertEqual(record.losses_for(self.bob), 0)

    def test_salir_de_un_duelo_terminado_lo_borra(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
            status=Duel.Status.FINISHED, challenger_lost=True,
        )
        self.client.login(username="bob@test.local", password="Testpass123!")
        response = self.client.post(reverse("games:duel-leave", kwargs={"pk": duel.pk}))
        self.assertRedirects(response, reverse("games:hub"))
        self.assertFalse(Duel.objects.filter(pk=duel.pk).exists())

    def test_salir_de_un_duelo_terminado_borra_el_mensaje_de_invitacion(self):
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-invite", kwargs={"username": self.bob.username}))
        duel = Duel.objects.get()
        duel.status = Duel.Status.FINISHED
        duel.challenger_lost = True
        duel.save(update_fields=["status", "challenger_lost"])
        self.client.logout()

        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-leave", kwargs={"pk": duel.pk}))
        self.assertFalse(Message.objects.filter(sender=self.alice, recipient=self.bob).exists())

    def test_no_se_puede_salir_de_un_duelo_todavia_activo(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-leave", kwargs={"pk": duel.pk}))
        self.assertTrue(Duel.objects.filter(pk=duel.pk).exists())

    def test_fallar_termina_el_duelo_al_instante_para_los_dos(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "round_id": self.quotes[0].pk, "answer": "Otra",
        })
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.Status.FINISHED)
        self.assertTrue(duel.challenger_lost)
        self.assertEqual(duel.winner, self.bob)
        self.assertTemplateUsed(response, "games/duel_result.html")

    def test_el_mensaje_de_invitacion_desaparece_en_cuanto_el_duelo_termina(self):
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-invite", kwargs={"username": self.bob.username}))
        duel = Duel.objects.get()
        duel.status = Duel.Status.ACTIVE
        duel.save(update_fields=["status"])
        self.client.logout()

        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "round_id": self.quotes[0].pk, "answer": "Otra",
        })

        self.assertFalse(Message.objects.filter(sender=self.alice, recipient=self.bob).exists())
        # El duelo en sí sigue existiendo hasta que alguien pulse "salir" —
        # solo el mensaje de invitación desaparece al instante.
        self.assertTrue(Duel.objects.filter(pk=duel.pk).exists())

    def test_ganador_ve_has_ganado_y_perdedor_ve_ganador_contrario(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
            status=Duel.Status.FINISHED, challenger_lost=True,
        )
        self.client.login(username="bob@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertContains(response, "¡Has ganado!")

        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertContains(response, "Has perdido")

    def test_revancha_necesita_que_los_dos_le_den(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
            status=Duel.Status.FINISHED, challenger_lost=True,
            challenger_streak=3, opponent_streak=5,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        duel.refresh_from_db()
        self.assertTrue(duel.challenger_wants_rematch)
        self.assertEqual(duel.status, Duel.Status.FINISHED)

        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.Status.ACTIVE)
        self.assertEqual(duel.current_index, 0)
        self.assertEqual(duel.challenger_streak, 0)
        self.assertEqual(duel.opponent_streak, 0)
        self.assertFalse(duel.challenger_lost)
        self.assertFalse(duel.challenger_wants_rematch)

    def test_un_desconocido_no_puede_ver_el_duelo(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, round_ids=[q.pk for q in self.quotes],
        )
        carol = User.objects.create(email="carol2@test.local", role=User.Role.LECTOR, username="carol2")
        carol.set_password("Testpass123!")
        carol.save()
        self.client.login(username="carol2@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertEqual(response.status_code, 404)


class CompareDuelTests(TestCase):
    """Duelos de Cuál está mejor valorada / Cuál recaudó más: a diferencia
    de los de texto, la ronda son dos películas (round_ids guarda pares),
    y se elige entre dos portadas en vez de entre opciones de texto."""

    def setUp(self):
        self.high = Movie.objects.create(
            tmdb_id=1, title="Alta", media_type="movie", imdb_rating="9.0", revenue=800_000_000,
        )
        self.low = Movie.objects.create(
            tmdb_id=2, title="Baja", media_type="movie", imdb_rating="5.0", revenue=100_000_000,
        )
        self.alice = User.objects.create(email="cmp_alice@test.local", role=User.Role.LECTOR, username="cmp_alice")
        self.alice.set_password("Testpass123!")
        self.alice.save()
        self.bob = User.objects.create(email="cmp_bob@test.local", role=User.Role.LECTOR, username="cmp_bob")
        self.bob.set_password("Testpass123!")
        self.bob.save()

    def test_retar_a_cual_esta_mejor_valorada_guarda_un_par_de_ids(self):
        FriendRequest.objects.create(from_user=self.alice, to_user=self.bob, accepted=True)
        self.client.login(username="cmp_alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-invite", kwargs={"username": self.bob.username}), {"game": "rating"})
        duel = Duel.objects.get()
        self.assertEqual(duel.game, "rating")
        self.assertEqual(len(duel.round_ids[0]), 2)

    def test_jugar_una_ronda_de_cual_recaudo_mas(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, game=Duel.Game.REVENUE,
            round_ids=[[self.high.pk, self.low.pk]], status=Duel.Status.ACTIVE,
        )
        self.client.login(username="cmp_alice@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertTemplateUsed(response, "games/duel_play_compare.html")
        self.assertEqual(response.context["left"], self.high)
        self.assertEqual(response.context["right"], self.low)

        response = self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "left_id": self.high.pk, "right_id": self.low.pk, "choice": "left",
        })
        duel.refresh_from_db()
        self.assertEqual(duel.challenger_streak, 1)
        self.assertTemplateUsed(response, "games/duel_waiting.html")

    def test_fallar_una_ronda_de_cual_esta_mejor_valorada_termina_el_duelo(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, game=Duel.Game.RATING,
            round_ids=[[self.high.pk, self.low.pk]], status=Duel.Status.ACTIVE,
        )
        self.client.login(username="cmp_alice@test.local", password="Testpass123!")
        response = self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "left_id": self.high.pk, "right_id": self.low.pk, "choice": "right",
        })
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.Status.FINISHED)
        self.assertTrue(duel.challenger_lost)
        self.assertTemplateUsed(response, "games/duel_result.html")


class OscarCandidateTests(TestCase):
    """Herramienta compartida (no un juego de racha personal): cualquiera
    propone candidatas por categoría y vota su favorita, un voto por
    categoría y usuario — votar de nuevo cambia el voto, no lo suma."""

    def setUp(self):
        self.user = User.objects.create(email="oscar@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")
        self.category = OscarCategory.objects.create(name="Mejor película")

    def test_pagina_accesible_sin_cuenta(self):
        self.client.logout()
        response = self.client.get(reverse("games:oscars"))
        self.assertEqual(response.status_code, 200)

    @patch("apps.games.views.Movie.get_or_create_from_tmdb")
    def test_proponer_candidata_la_anade_a_la_categoria(self, mock_get_or_create):
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=1, title="Peli candidata")
        response = self.client.post(reverse("games:oscar-candidate-add", args=[self.category.pk, 1]))
        self.assertRedirects(response, reverse("games:oscars"))
        self.assertTrue(OscarCandidate.objects.filter(category=self.category, movie__tmdb_id=1).exists())

    @patch("apps.games.views.Movie.get_or_create_from_tmdb")
    def test_no_duplica_la_misma_candidata_en_una_categoria(self, mock_get_or_create):
        movie = Movie.objects.create(tmdb_id=2, title="Repetida")
        mock_get_or_create.return_value = movie
        self.client.post(reverse("games:oscar-candidate-add", args=[self.category.pk, 2]))
        self.client.post(reverse("games:oscar-candidate-add", args=[self.category.pk, 2]))
        self.assertEqual(OscarCandidate.objects.filter(category=self.category, movie=movie).count(), 1)

    @patch("apps.games.views.Movie.get_or_create_from_tmdb")
    def test_proponer_registra_tu_voto_automaticamente(self, mock_get_or_create):
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=4, title="Propuesta")
        self.client.post(reverse("games:oscar-candidate-add", args=[self.category.pk, 4]))
        candidate = OscarCandidate.objects.get(category=self.category, movie__tmdb_id=4)
        vote = OscarVote.objects.get(category=self.category, user=self.user)
        self.assertEqual(vote.candidate, candidate)

    @patch("apps.games.views.Movie.get_or_create_from_tmdb")
    def test_proponer_otra_distinta_sobreescribe_tu_voto_anterior(self, mock_get_or_create):
        movie_a = Movie.objects.create(tmdb_id=5, title="Primera propuesta")
        movie_b = Movie.objects.create(tmdb_id=6, title="Segunda propuesta")
        mock_get_or_create.side_effect = [movie_a, movie_b]

        self.client.post(reverse("games:oscar-candidate-add", args=[self.category.pk, 5]))
        self.client.post(reverse("games:oscar-candidate-add", args=[self.category.pk, 6]))

        votes = OscarVote.objects.filter(category=self.category, user=self.user)
        self.assertEqual(votes.count(), 1)
        self.assertEqual(votes.first().candidate.movie, movie_b)

    @patch("apps.games.views.Movie.get_or_create_from_tmdb")
    def test_dos_personas_proponiendo_la_misma_suman_al_contador_de_votos(self, mock_get_or_create):
        movie = Movie.objects.create(tmdb_id=7, title="Popular")
        mock_get_or_create.return_value = movie
        other = User.objects.create(email="oscar2@test.local", role=User.Role.LECTOR)
        other.set_password("Testpass123!")
        other.save()

        self.client.post(reverse("games:oscar-candidate-add", args=[self.category.pk, 7]))
        self.client.logout()
        self.client.login(username=other.email, password="Testpass123!")
        self.client.post(reverse("games:oscar-candidate-add", args=[self.category.pk, 7]))

        candidate = OscarCandidate.objects.get(category=self.category, movie=movie)
        self.assertEqual(candidate.votes.count(), 2)

    def test_votar_registra_el_voto(self):
        movie = Movie.objects.create(tmdb_id=3, title="Votable")
        candidate = OscarCandidate.objects.create(category=self.category, movie=movie, submitted_by=self.user)
        response = self.client.post(reverse("games:oscar-vote", args=[candidate.pk]))
        self.assertRedirects(response, reverse("games:oscars"))
        self.assertTrue(OscarVote.objects.filter(category=self.category, user=self.user, candidate=candidate).exists())

    def test_votar_de_nuevo_en_la_misma_categoria_reemplaza_el_voto(self):
        movie_a = Movie.objects.create(tmdb_id=4, title="A")
        movie_b = Movie.objects.create(tmdb_id=5, title="B")
        candidate_a = OscarCandidate.objects.create(category=self.category, movie=movie_a, submitted_by=self.user)
        candidate_b = OscarCandidate.objects.create(category=self.category, movie=movie_b, submitted_by=self.user)

        self.client.post(reverse("games:oscar-vote", args=[candidate_a.pk]))
        self.client.post(reverse("games:oscar-vote", args=[candidate_b.pk]))

        votes = OscarVote.objects.filter(category=self.category, user=self.user)
        self.assertEqual(votes.count(), 1)
        self.assertEqual(votes.first().candidate, candidate_b)

    def test_no_se_puede_votar_en_una_categoria_cerrada(self):
        self.category.is_open = False
        self.category.save(update_fields=["is_open"])
        movie = Movie.objects.create(tmdb_id=6, title="Cerrada")
        candidate = OscarCandidate.objects.create(category=self.category, movie=movie, submitted_by=self.user)
        response = self.client.post(reverse("games:oscar-vote", args=[candidate.pk]))
        self.assertEqual(response.status_code, 404)

    @patch("apps.games.views.tmdb_search")
    def test_buscar_usa_el_servicio_tmdb(self, mock_search):
        mock_search.return_value = []
        response = self.client.get(reverse("games:oscar-candidate-search", args=[self.category.pk]), {"query": "matrix"})
        self.assertEqual(response.status_code, 200)
        mock_search.assert_called_once_with("matrix")

    def test_categoria_de_persona_proponer_la_anade(self):
        person_category = OscarCategory.objects.create(
            name="Mejor actor", candidate_type=OscarCategory.CandidateType.PERSON,
        )
        response = self.client.post(reverse("games:oscar-candidate-add-person", args=[person_category.pk]), {
            "tmdb_person_id": "42", "name": "Actor Ejemplo", "photo_url": "https://image.tmdb.org/t/p/w500/foto.jpg",
        })
        self.assertRedirects(response, reverse("games:oscars"))
        candidate = OscarCandidate.objects.get(category=person_category)
        self.assertEqual(candidate.person_name, "Actor Ejemplo")
        self.assertEqual(candidate.display_title, "Actor Ejemplo")
        self.assertEqual(candidate.display_photo, "https://image.tmdb.org/t/p/w500/foto.jpg")

    def test_categoria_de_pelicula_no_acepta_anadir_persona(self):
        response = self.client.post(reverse("games:oscar-candidate-add-person", args=[self.category.pk]), {
            "tmdb_person_id": "42", "name": "Actor Ejemplo", "photo_url": "",
        })
        self.assertEqual(response.status_code, 404)

    def test_categoria_de_persona_no_acepta_anadir_pelicula(self):
        person_category = OscarCategory.objects.create(
            name="Mejor actriz", candidate_type=OscarCategory.CandidateType.PERSON,
        )
        response = self.client.post(reverse("games:oscar-candidate-add", args=[person_category.pk, 1]))
        self.assertEqual(response.status_code, 404)

    def test_no_duplica_la_misma_persona_en_una_categoria(self):
        person_category = OscarCategory.objects.create(
            name="Mejor director/a", candidate_type=OscarCategory.CandidateType.PERSON,
        )
        for _ in range(2):
            self.client.post(reverse("games:oscar-candidate-add-person", args=[person_category.pk]), {
                "tmdb_person_id": "99", "name": "Repetido/a", "photo_url": "",
            })
        self.assertEqual(OscarCandidate.objects.filter(category=person_category, person_tmdb_id=99).count(), 1)

    @patch("apps.games.views.tmdb_search_person")
    def test_buscar_en_categoria_de_persona_usa_tmdb_search_person(self, mock_search):
        person_category = OscarCategory.objects.create(
            name="Mejor actor de reparto", candidate_type=OscarCategory.CandidateType.PERSON,
        )
        mock_search.return_value = []
        response = self.client.get(
            reverse("games:oscar-candidate-search", args=[person_category.pk]), {"query": "de niro"},
        )
        self.assertEqual(response.status_code, 200)
        mock_search.assert_called_once_with("de niro")


class SeedTriviaCommandTests(TestCase):
    def test_carga_un_buen_numero_de_preguntas_por_categoria_y_es_idempotente(self):
        call_command("seed_trivia")
        trivia_count = TriviaQuestion.objects.filter(category=TriviaQuestion.Category.TRIVIA).count()
        self.assertGreaterEqual(trivia_count, 80)
        self.assertGreater(TriviaQuestion.objects.filter(category=TriviaQuestion.Category.EMOJI).count(), 0)
        self.assertGreater(TrueFalseStatement.objects.count(), 0)

        call_command("seed_trivia")
        self.assertEqual(
            TriviaQuestion.objects.filter(category=TriviaQuestion.Category.TRIVIA).count(), trivia_count,
        )


class SeedOscarCategoriesCommandTests(TestCase):
    def test_carga_categorias_reales_con_su_tipo(self):
        call_command("seed_oscar_categories")
        self.assertTrue(OscarCategory.objects.filter(
            name="Mejor película", candidate_type=OscarCategory.CandidateType.MOVIE,
        ).exists())
        self.assertTrue(OscarCategory.objects.filter(
            name="Mejor actor", candidate_type=OscarCategory.CandidateType.PERSON,
        ).exists())
        self.assertGreaterEqual(OscarCategory.objects.count(), 15)

    def test_corrige_el_tipo_de_una_categoria_sembrada_por_una_version_antigua(self):
        # Antes de que existiera candidate_type, "Mejor actor" se creaba con
        # el valor por defecto del modelo ("movie") — get_or_create nunca
        # corregía esto en pases posteriores, así que la categoría se
        # quedaba bloqueada sin poder proponer personas ni mostrar su foto.
        OscarCategory.objects.create(name="Mejor actor", candidate_type=OscarCategory.CandidateType.MOVIE, order=99)
        call_command("seed_oscar_categories")
        category = OscarCategory.objects.get(name="Mejor actor")
        self.assertEqual(category.candidate_type, OscarCategory.CandidateType.PERSON)

    def test_elimina_categorias_obsoletas_que_ya_no_existen(self):
        OscarCategory.objects.create(name="Mejor serie", candidate_type=OscarCategory.CandidateType.MOVIE)
        call_command("seed_oscar_categories")
        self.assertFalse(OscarCategory.objects.filter(name="Mejor serie").exists())


class GameTierListTests(TestCase):
    """Tier list personal por usuario, en Juegos — distinta de la de Top
    Secret (esa es una sola, del dueño del sitio). Los niveles son
    editables por cada usuario, igual que en Top Secret, pero sin
    compartir ninguno entre usuarios."""

    def setUp(self):
        self.user = User.objects.create(email="tierlist@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")

    def test_requiere_login(self):
        self.client.logout()
        response = self.client.get(reverse("games:tier-list"))
        self.assertIn("/cuenta/login/", response.url)

    def test_primera_visita_crea_los_niveles_por_defecto(self):
        self.client.get(reverse("games:tier-list"))
        names = list(GameTierLevel.objects.filter(user=self.user).order_by("order").values_list("name", flat=True))
        self.assertEqual(names, ["S", "A", "B", "C", "D"])

    def test_no_duplica_niveles_en_visitas_siguientes(self):
        self.client.get(reverse("games:tier-list"))
        self.client.get(reverse("games:tier-list"))
        self.assertEqual(GameTierLevel.objects.filter(user=self.user).count(), 5)

    def test_cada_usuario_ve_solo_las_suyas(self):
        other = User.objects.create(email="otro_tier@test.local", role=User.Role.LECTOR)
        movie_a = Movie.objects.create(tmdb_id=1, title="Mía", media_type="movie")
        movie_b = Movie.objects.create(tmdb_id=2, title="Ajena", media_type="movie")
        my_level = GameTierLevel.objects.create(user=self.user, name="S", color="#FFD700", order=0)
        other_level = GameTierLevel.objects.create(user=other, name="S", color="#FFD700", order=0)
        GameTierEntry.objects.create(user=self.user, movie=movie_a, tier=my_level)
        GameTierEntry.objects.create(user=other, movie=movie_b, tier=other_level)

        response = self.client.get(reverse("games:tier-list"))
        level_rows = dict(response.context["level_rows"])
        self.assertEqual([e.movie for e in level_rows[my_level]], [movie_a])

    def test_nueva_entrada_cae_en_sin_clasificar(self):
        movie = Movie.objects.create(tmdb_id=3, title="Nueva", media_type="movie")
        GameTierEntry.objects.create(user=self.user, movie=movie)
        response = self.client.get(reverse("games:tier-list"))
        self.assertEqual([e.movie for e in response.context["unsorted_entries"]], [movie])

    @patch("apps.games.views.tmdb_search")
    def test_buscar_usa_el_servicio_tmdb(self, mock_search):
        mock_search.return_value = []
        response = self.client.get(reverse("games:tier-list-search"), {"query": "matrix"})
        self.assertEqual(response.status_code, 200)
        mock_search.assert_called_once_with("matrix")

    @patch("apps.games.views.Movie.get_or_create_from_tmdb")
    def test_anadir_desde_busqueda_cae_en_sin_clasificar(self, mock_get_or_create):
        mock_get_or_create.return_value = Movie.objects.create(tmdb_id=99, title="Nueva película")
        response = self.client.post(reverse("games:tier-list-add", args=[99]))
        self.assertRedirects(response, reverse("games:tier-list"))
        entry = GameTierEntry.objects.get(user=self.user, movie__tmdb_id=99)
        self.assertIsNone(entry.tier)

    @patch("apps.games.views.Movie.get_or_create_from_tmdb", side_effect=MovieAPIError("fallo"))
    def test_error_de_tmdb_al_anadir_no_rompe_la_pagina(self, mock_get_or_create):
        response = self.client.post(reverse("games:tier-list-add", args=[99]))
        self.assertRedirects(response, reverse("games:tier-list"))
        self.assertFalse(GameTierEntry.objects.exists())

    def test_mover_cambia_de_nivel_y_se_coloca_al_final(self):
        s = GameTierLevel.objects.create(user=self.user, name="S", color="#FFD700", order=0)
        d = GameTierLevel.objects.create(user=self.user, name="D", color="#D98C8C", order=1)
        GameTierEntry.objects.create(user=self.user, movie=Movie.objects.create(tmdb_id=4, title="Ya en D"), tier=d, order=1)
        entry = GameTierEntry.objects.create(user=self.user, movie=Movie.objects.create(tmdb_id=5, title="Se mueve"), tier=s, order=1)

        response = self.client.post(reverse("games:tier-list-move", args=[entry.pk]), {"tier": d.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

        entry.refresh_from_db()
        self.assertEqual(entry.tier, d)
        self.assertEqual(entry.order, 2)

    def test_mover_a_sin_clasificar(self):
        s = GameTierLevel.objects.create(user=self.user, name="S", color="#FFD700", order=0)
        entry = GameTierEntry.objects.create(user=self.user, movie=Movie.objects.create(tmdb_id=6, title="X"), tier=s, order=1)
        response = self.client.post(reverse("games:tier-list-move", args=[entry.pk]), {"tier": ""})
        self.assertEqual(response.status_code, 200)
        entry.refresh_from_db()
        self.assertIsNone(entry.tier)

    def test_no_se_puede_mover_una_entrada_ajena(self):
        other = User.objects.create(email="otro_tier2@test.local", role=User.Role.LECTOR)
        movie = Movie.objects.create(tmdb_id=7, title="No es tuya", media_type="movie")
        entry = GameTierEntry.objects.create(user=other, movie=movie)

        response = self.client.post(reverse("games:tier-list-move", args=[entry.pk]), {"tier": ""})
        self.assertEqual(response.status_code, 404)

    def test_nivel_invalido_da_error(self):
        movie = Movie.objects.create(tmdb_id=8, title="X", media_type="movie")
        entry = GameTierEntry.objects.create(user=self.user, movie=movie)
        response = self.client.post(reverse("games:tier-list-move", args=[entry.pk]), {"tier": "9999"})
        self.assertEqual(response.status_code, 400)

    def test_no_se_puede_mover_al_nivel_de_otro_usuario(self):
        other = User.objects.create(email="otro_tier4@test.local", role=User.Role.LECTOR)
        other_level = GameTierLevel.objects.create(user=other, name="S", color="#FFD700", order=0)
        entry = GameTierEntry.objects.create(user=self.user, movie=Movie.objects.create(tmdb_id=9, title="X"))
        response = self.client.post(reverse("games:tier-list-move", args=[entry.pk]), {"tier": other_level.pk})
        self.assertEqual(response.status_code, 400)

    def test_reiniciar_borra_solo_las_del_usuario(self):
        other = User.objects.create(email="otro_tier3@test.local", role=User.Role.LECTOR)
        movie_a = Movie.objects.create(tmdb_id=10, title="Mía", media_type="movie")
        movie_b = Movie.objects.create(tmdb_id=11, title="Ajena", media_type="movie")
        GameTierEntry.objects.create(user=self.user, movie=movie_a)
        GameTierEntry.objects.create(user=other, movie=movie_b)

        self.client.post(reverse("games:tier-list-reset"))

        self.assertFalse(GameTierEntry.objects.filter(user=self.user).exists())
        self.assertTrue(GameTierEntry.objects.filter(user=other).exists())

    def test_reiniciar_no_borra_los_niveles(self):
        self.client.get(reverse("games:tier-list"))
        self.client.post(reverse("games:tier-list-reset"))
        self.assertEqual(GameTierLevel.objects.filter(user=self.user).count(), 5)


class GameTierLevelManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="tierlevel@test.local", role=User.Role.LECTOR)
        self.user.set_password("Testpass123!")
        self.user.save()
        self.client.login(username=self.user.email, password="Testpass123!")

    def test_anadir_nivel(self):
        response = self.client.post(reverse("games:tier-level-create"), {"name": "SS", "color": "#FF0000"})
        self.assertRedirects(response, reverse("games:tier-list"))
        level = GameTierLevel.objects.get(user=self.user, name="SS")
        self.assertEqual(level.color, "#FF0000")

    def test_nuevo_nivel_se_coloca_al_final(self):
        GameTierLevel.objects.create(user=self.user, name="S", color="#FFD700", order=0)
        self.client.post(reverse("games:tier-level-create"), {"name": "SS", "color": "#FF0000"})
        level = GameTierLevel.objects.get(user=self.user, name="SS")
        self.assertEqual(level.order, 1)

    def test_editar_nivel(self):
        level = GameTierLevel.objects.create(user=self.user, name="S", color="#FFD700", order=0)
        self.client.post(reverse("games:tier-level-update", args=[level.pk]), {"name": "Genial", "color": "#00FF00"})
        level.refresh_from_db()
        self.assertEqual(level.name, "Genial")
        self.assertEqual(level.color, "#00FF00")

    def test_no_se_puede_editar_el_nivel_de_otro_usuario(self):
        other = User.objects.create(email="otro_nivel@test.local", role=User.Role.LECTOR)
        level = GameTierLevel.objects.create(user=other, name="S", color="#FFD700", order=0)
        response = self.client.post(reverse("games:tier-level-update", args=[level.pk]), {"name": "Robado", "color": "#000000"})
        self.assertEqual(response.status_code, 404)

    def test_borrar_nivel_deja_sus_entradas_sin_clasificar(self):
        level = GameTierLevel.objects.create(user=self.user, name="S", color="#FFD700", order=0)
        movie = Movie.objects.create(tmdb_id=1, title="X", media_type="movie")
        entry = GameTierEntry.objects.create(user=self.user, movie=movie, tier=level)

        self.client.post(reverse("games:tier-level-delete", args=[level.pk]))

        self.assertFalse(GameTierLevel.objects.filter(pk=level.pk).exists())
        entry.refresh_from_db()
        self.assertIsNone(entry.tier)

    def test_no_se_puede_borrar_el_nivel_de_otro_usuario(self):
        other = User.objects.create(email="otro_nivel2@test.local", role=User.Role.LECTOR)
        level = GameTierLevel.objects.create(user=other, name="S", color="#FFD700", order=0)
        response = self.client.post(reverse("games:tier-level-delete", args=[level.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(GameTierLevel.objects.filter(pk=level.pk).exists())
