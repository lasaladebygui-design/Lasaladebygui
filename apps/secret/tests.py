from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

from .models import MovieQuote, SecretMovie, TierListEntry, TopSecretConfig


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


class TierListTests(TestCase):
    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})

    def test_agrupa_por_nivel(self):
        TierListEntry.objects.create(tier="S", title="Pulp Fiction", order=1)
        TierListEntry.objects.create(tier="S", title="Kill Bill", order=2)
        TierListEntry.objects.create(tier="D", title="Una película mala", order=1)

        response = self.client.get(reverse("secret:tier-list"))
        tiers = response.context["tiers"]
        self.assertEqual([e.title for e in tiers["S"]], ["Pulp Fiction", "Kill Bill"])
        self.assertEqual([e.title for e in tiers["D"]], ["Una película mala"])
        self.assertEqual(tiers["A"], [])

    def test_requiere_haber_entrado_al_maletin(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:tier-list"))
        self.assertRedirects(response, reverse("secret:gate"))


class QuoteGameTests(TestCase):
    def setUp(self):
        self.client.post(reverse("secret:gate"), {"code": "8888"})
        self.quote = MovieQuote.objects.create(
            quote="Que la Fuerza te acompañe.",
            correct_title="Star Wars",
            wrong_title_1="Regreso al futuro",
            wrong_title_2="El padrino",
        )

    def test_requiere_haber_entrado_al_maletin(self):
        self.client.post(reverse("secret:lock"))
        response = self.client.get(reverse("secret:quote-game"))
        self.assertRedirects(response, reverse("secret:gate"))

    def test_muestra_una_frase_con_tres_opciones(self):
        response = self.client.get(reverse("secret:quote-game"))
        self.assertIsNotNone(response.context["quote"])
        self.assertEqual(len(response.context["options"]), 3)
        self.assertIn("Star Wars", response.context["options"])

    def test_acertar_incrementa_la_racha(self):
        response = self.client.post(reverse("secret:quote-game"), {
            "quote_id": self.quote.pk, "answer": "Star Wars",
        })
        self.assertEqual(response.context["streak"], 1)

    def test_fallar_reinicia_la_racha(self):
        session = self.client.session
        session["quote_streak"] = 4
        session.save()

        response = self.client.post(reverse("secret:quote-game"), {
            "quote_id": self.quote.pk, "answer": "El padrino",
        })
        self.assertEqual(response.context["streak"], 0)

    def test_racha_se_guarda_en_el_perfil_si_esta_logueado(self):
        user = User.objects.create(email="lector@test.local", role=User.Role.LECTOR)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

        session = self.client.session
        session["quote_streak"] = 3
        session.save()

        self.client.post(reverse("secret:quote-game"), {
            "quote_id": self.quote.pk, "answer": "El padrino",
        })
        user.refresh_from_db()
        self.assertEqual(user.quote_streak_best, 3)

    def test_no_baja_el_record_si_la_racha_es_menor(self):
        user = User.objects.create(email="lector2@test.local", role=User.Role.LECTOR, quote_streak_best=10)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

        session = self.client.session
        session["quote_streak"] = 2
        session.save()

        self.client.post(reverse("secret:quote-game"), {
            "quote_id": self.quote.pk, "answer": "El padrino",
        })
        user.refresh_from_db()
        self.assertEqual(user.quote_streak_best, 10)

    def test_fallar_muestra_pantalla_de_fin_de_partida(self):
        session = self.client.session
        session["quote_streak"] = 3
        session.save()

        response = self.client.post(reverse("secret:quote-game"), {
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
        self.client.post(reverse("secret:gate"), {"code": "8888"})

        session = self.client.session
        session["quote_streak"] = 5
        session.save()

        response = self.client.post(reverse("secret:quote-game"), {
            "quote_id": self.quote.pk, "answer": "El padrino",
        })
        self.assertTrue(response.context["is_new_record"])

    def test_fallar_sin_superar_el_record_no_lo_marca(self):
        user = User.objects.create(email="lector4@test.local", role=User.Role.LECTOR, quote_streak_best=10)
        user.set_password("Testpass123!")
        user.save()
        self.client.login(username=user.email, password="Testpass123!")
        self.client.post(reverse("secret:gate"), {"code": "8888"})

        session = self.client.session
        session["quote_streak"] = 2
        session.save()

        response = self.client.post(reverse("secret:quote-game"), {
            "quote_id": self.quote.pk, "answer": "El padrino",
        })
        self.assertFalse(response.context["is_new_record"])

    def test_acertar_no_muestra_pantalla_de_fin_de_partida(self):
        response = self.client.post(reverse("secret:quote-game"), {
            "quote_id": self.quote.pk, "answer": "Star Wars",
        })
        self.assertFalse(response.context["game_over"])
        self.assertIsNotNone(response.context["quote"])
