from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.movies.models import Movie
from apps.movies.services import MovieAPIError
from apps.social.models import FriendRequest, Message

from .models import Duel, DuelRecord, GameTierEntry, GameTierLevel, MovieQuote


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
    catálogo. Películas y series van cada una con su propia racha."""

    def setUp(self):
        self.movie_a = Movie.objects.create(tmdb_id=1, title="Peli A", media_type="movie", imdb_rating="8.5")
        self.movie_b = Movie.objects.create(tmdb_id=2, title="Peli B", media_type="movie", imdb_rating="6.0")
        self.tv_a = Movie.objects.create(tmdb_id=1, title="Serie A", media_type="tv", imdb_rating="9.0")
        self.tv_b = Movie.objects.create(tmdb_id=2, title="Serie B", media_type="tv", imdb_rating="7.0")

    def test_accesible_sin_cuenta(self):
        response = self.client.get(reverse("games:rating-duel"))
        self.assertEqual(response.status_code, 200)

    def test_muestra_dos_peliculas_por_defecto(self):
        response = self.client.get(reverse("games:rating-duel"))
        self.assertEqual(response.context["media_type"], "movie")
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
        response = self.client.get(reverse("games:rating-duel"))
        self.assertIsNone(response.context["left"])
        self.assertContains(response, "Todavía no hay suficientes")

    def test_acertar_la_mas_valorada_incrementa_la_racha(self):
        response = self.client.post(reverse("games:rating-duel"), {
            "type": "movie", "left_id": self.movie_a.pk, "right_id": self.movie_b.pk, "choice": "left",
        })
        self.assertEqual(response.context["streak"], 1)
        self.assertFalse(response.context["game_over"])

    def test_fallar_reinicia_la_racha_y_muestra_fin_de_partida(self):
        session = self.client.session
        session["rating_duel_streak_movie"] = 3
        session.save()

        response = self.client.post(reverse("games:rating-duel"), {
            "type": "movie", "left_id": self.movie_a.pk, "right_id": self.movie_b.pk, "choice": "right",
        })
        self.assertEqual(response.context["streak"], 0)
        self.assertTrue(response.context["game_over"])
        self.assertEqual(response.context["final_streak"], 3)

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
        self.assertEqual(len(duel.quote_ids), 1)
        self.assertRedirects(response, reverse("games:duel-detail", kwargs={"pk": duel.pk}))

    def test_el_retador_ve_pantalla_de_espera_mientras_esta_pendiente(self):
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-invite", kwargs={"username": self.bob.username}))
        duel = Duel.objects.get()

        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertContains(response, "Esperando a que")

    def test_el_retado_puede_aceptar_el_duelo(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
        )
        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-accept", kwargs={"pk": duel.pk}))
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.Status.ACTIVE)

    def test_el_retado_puede_rechazar_el_duelo(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
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
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
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
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertEqual(response.context["quote"], self.quotes[0])

        self.client.login(username="bob@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertEqual(response.context["quote"], self.quotes[0])

    def test_responder_bien_y_esperar_al_rival(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[0].pk, "answer": "Película 0",
        })
        duel.refresh_from_db()
        self.assertEqual(duel.challenger_streak, 1)
        self.assertTrue(duel.challenger_answered)
        self.assertEqual(duel.current_index, 0)
        self.assertTemplateUsed(response, "games/duel_waiting.html")

    def test_cuando_los_dos_aciertan_avanza_la_ronda_para_los_dos(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[0].pk, "answer": "Película 0",
        })
        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[0].pk, "answer": "Película 0",
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
            challenger=self.alice, opponent=self.bob, quote_ids=[self.quotes[0].pk],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[0].pk, "answer": "Película 0",
        })
        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[0].pk, "answer": "Película 0",
        })
        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.Status.ACTIVE)
        self.assertEqual(duel.current_index, 1)
        self.assertEqual(len(duel.quote_ids), 2)

    def test_no_muestra_pregunta_x_de_n(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertNotContains(response, " de 10")

    def test_terminar_el_duelo_actualiza_el_marcador(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[0].pk, "answer": "Otra",
        })
        record = DuelRecord.get_for(self.alice, self.bob)
        self.assertIsNotNone(record)
        self.assertEqual(record.wins_for(self.bob), 1)
        self.assertEqual(record.losses_for(self.bob), 0)

    def test_salir_de_un_duelo_terminado_lo_borra(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
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
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-leave", kwargs={"pk": duel.pk}))
        self.assertTrue(Duel.objects.filter(pk=duel.pk).exists())

    def test_fallar_termina_el_duelo_al_instante_para_los_dos(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
            status=Duel.Status.ACTIVE,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[0].pk, "answer": "Otra",
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
            "quote_id": self.quotes[0].pk, "answer": "Otra",
        })

        self.assertFalse(Message.objects.filter(sender=self.alice, recipient=self.bob).exists())
        # El duelo en sí sigue existiendo hasta que alguien pulse "salir" —
        # solo el mensaje de invitación desaparece al instante.
        self.assertTrue(Duel.objects.filter(pk=duel.pk).exists())

    def test_ganador_ve_has_ganado_y_perdedor_ve_ganador_contrario(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
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
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
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
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
        )
        carol = User.objects.create(email="carol2@test.local", role=User.Role.LECTOR, username="carol2")
        carol.set_password("Testpass123!")
        carol.save()
        self.client.login(username="carol2@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertEqual(response.status_code, 404)


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
