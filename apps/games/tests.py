from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.social.models import FriendRequest

from .models import Duel, MovieQuote


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


class DuelTests(TestCase):
    """Duelo: mismo reto, misma tanda de frases (orden fijo), cada jugador
    la juega por su lado; al final se compara quién llegó más lejos."""

    def setUp(self):
        self.quotes = [
            MovieQuote.objects.create(
                quote=f"Frase número {i}", correct_title=f"Película {i}",
                wrong_title_1="Otra", wrong_title_2="Otra más",
            )
            for i in range(Duel.QUOTE_COUNT)
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

    def test_retar_a_un_amigo_crea_un_duelo_activo(self):
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.post(reverse("games:duel-invite", kwargs={"username": self.bob.username}))
        duel = Duel.objects.get()
        self.assertEqual(duel.challenger, self.alice)
        self.assertEqual(duel.opponent, self.bob)
        self.assertEqual(duel.status, Duel.Status.ACTIVE)
        self.assertEqual(len(duel.quote_ids), Duel.QUOTE_COUNT)
        self.assertRedirects(response, reverse("games:duel-detail", kwargs={"pk": duel.pk}))

    def test_ambos_juegan_la_misma_tanda_en_el_mismo_orden(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertEqual(response.context["quote"], self.quotes[0])

        self.client.login(username="bob@test.local", password="Testpass123!")
        response = self.client.get(reverse("games:duel-detail", kwargs={"pk": duel.pk}))
        self.assertEqual(response.context["quote"], self.quotes[0])

    def test_fallar_termina_la_tanda_y_fija_la_racha(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[0].pk, "answer": "Película 0",
        })
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[1].pk, "answer": "Otra",
        })
        duel.refresh_from_db()
        self.assertEqual(duel.challenger_streak, 1)
        self.assertTrue(duel.challenger_finished)
        self.assertFalse(duel.opponent_finished)

    def test_se_marca_terminado_cuando_ambos_acaban_y_hay_ganador(self):
        duel = Duel.objects.create(
            challenger=self.alice, opponent=self.bob, quote_ids=[q.pk for q in self.quotes],
            challenger_streak=0, opponent_streak=0,
        )
        self.client.login(username="alice@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[0].pk, "answer": "Otra",
        })

        self.client.login(username="bob@test.local", password="Testpass123!")
        self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[0].pk, "answer": "Película 0",
        })
        response = self.client.post(reverse("games:duel-detail", kwargs={"pk": duel.pk}), {
            "quote_id": self.quotes[1].pk, "answer": "Otra",
        })

        duel.refresh_from_db()
        self.assertEqual(duel.status, Duel.Status.FINISHED)
        self.assertEqual(duel.winner, self.bob)

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
