from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

from .models import FriendRequest, Message, are_friends, friendship_status


def make_user(email, **extra):
    user = User.objects.create(email=email, role=User.Role.LECTOR, **extra)
    user.set_password("Testpass123!")
    user.save()
    return user


class FriendshipHelpersTests(TestCase):
    def setUp(self):
        self.ana = make_user("ana@test.local")
        self.bea = make_user("bea@test.local")

    def test_sin_solicitud_no_son_amigos(self):
        self.assertFalse(are_friends(self.ana, self.bea))
        self.assertEqual(friendship_status(self.ana, self.bea), "none")

    def test_solicitud_pendiente_se_ve_desde_ambos_lados(self):
        FriendRequest.objects.create(from_user=self.ana, to_user=self.bea)
        self.assertEqual(friendship_status(self.ana, self.bea), "pending_outgoing")
        self.assertEqual(friendship_status(self.bea, self.ana), "pending_incoming")

    def test_solicitud_aceptada_los_hace_amigos(self):
        FriendRequest.objects.create(from_user=self.ana, to_user=self.bea, accepted=True)
        self.assertTrue(are_friends(self.ana, self.bea))
        self.assertTrue(are_friends(self.bea, self.ana))
        self.assertEqual(friendship_status(self.ana, self.bea), "friends")

    def test_uno_mismo_es_self(self):
        self.assertEqual(friendship_status(self.ana, self.ana), "self")


class FriendRequestFlowTests(TestCase):
    def setUp(self):
        self.ana = make_user("ana@test.local")
        self.bea = make_user("bea@test.local")

    def test_enviar_solicitud_crea_pendiente(self):
        self.client.login(username="ana@test.local", password="Testpass123!")
        self.client.post(reverse("social:friend-request-send", kwargs={"username": self.bea.username}))
        self.assertTrue(
            FriendRequest.objects.filter(from_user=self.ana, to_user=self.bea, accepted=False).exists()
        )

    def test_responder_con_solicitud_mutua_los_hace_amigos_directamente(self):
        FriendRequest.objects.create(from_user=self.bea, to_user=self.ana)
        self.client.login(username="ana@test.local", password="Testpass123!")
        self.client.post(reverse("social:friend-request-send", kwargs={"username": self.bea.username}))
        self.assertTrue(are_friends(self.ana, self.bea))

    def test_aceptar_solicitud(self):
        req = FriendRequest.objects.create(from_user=self.ana, to_user=self.bea)
        self.client.login(username="bea@test.local", password="Testpass123!")
        self.client.post(reverse("social:friend-request-accept", kwargs={"pk": req.pk}))
        req.refresh_from_db()
        self.assertTrue(req.accepted)

    def test_rechazar_solicitud_la_elimina(self):
        req = FriendRequest.objects.create(from_user=self.ana, to_user=self.bea)
        self.client.login(username="bea@test.local", password="Testpass123!")
        self.client.post(reverse("social:friend-request-decline", kwargs={"pk": req.pk}))
        self.assertFalse(FriendRequest.objects.filter(pk=req.pk).exists())

    def test_no_se_puede_aceptar_una_solicitud_ajena(self):
        carla = make_user("carla@test.local")
        req = FriendRequest.objects.create(from_user=self.ana, to_user=self.bea)
        self.client.login(username="carla@test.local", password="Testpass123!")
        response = self.client.post(reverse("social:friend-request-accept", kwargs={"pk": req.pk}))
        self.assertEqual(response.status_code, 404)

    def test_eliminar_amistad(self):
        FriendRequest.objects.create(from_user=self.ana, to_user=self.bea, accepted=True)
        self.client.login(username="ana@test.local", password="Testpass123!")
        self.client.post(reverse("social:friend-remove", kwargs={"username": self.bea.username}))
        self.assertFalse(are_friends(self.ana, self.bea))


class PublicProfileTests(TestCase):
    def setUp(self):
        self.ana = make_user("ana@test.local")
        self.bea = make_user("bea@test.local")

    def test_requiere_login(self):
        response = self.client.get(reverse("social:public-profile", kwargs={"username": self.bea.username}))
        self.assertEqual(response.status_code, 302)

    def test_ver_perfil_de_otro(self):
        self.client.login(username="ana@test.local", password="Testpass123!")
        response = self.client.get(reverse("social:public-profile", kwargs={"username": self.bea.username}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["status"], "none")

    def test_ver_el_propio_perfil_redirige_a_cuenta(self):
        self.client.login(username="ana@test.local", password="Testpass123!")
        response = self.client.get(reverse("social:public-profile", kwargs={"username": self.ana.username}))
        self.assertRedirects(response, reverse("accounts:profile"))


class MessagingTests(TestCase):
    def setUp(self):
        self.ana = make_user("ana@test.local")
        self.bea = make_user("bea@test.local")
        self.carla = make_user("carla@test.local")

    def test_no_se_puede_escribir_a_quien_no_es_amigo(self):
        self.client.login(username="ana@test.local", password="Testpass123!")
        response = self.client.get(reverse("social:conversation", kwargs={"username": self.bea.username}))
        self.assertEqual(response.status_code, 404)

    def test_enviar_mensaje_a_un_amigo(self):
        FriendRequest.objects.create(from_user=self.ana, to_user=self.bea, accepted=True)
        self.client.login(username="ana@test.local", password="Testpass123!")
        self.client.post(
            reverse("social:conversation", kwargs={"username": self.bea.username}),
            {"body": "Hola Bea"},
        )
        self.assertTrue(Message.objects.filter(sender=self.ana, recipient=self.bea, body="Hola Bea").exists())

    def test_leer_conversacion_marca_como_leidos_los_mensajes_recibidos(self):
        FriendRequest.objects.create(from_user=self.ana, to_user=self.bea, accepted=True)
        Message.objects.create(sender=self.bea, recipient=self.ana, body="Hola Ana")
        self.client.login(username="ana@test.local", password="Testpass123!")
        self.client.get(reverse("social:conversation", kwargs={"username": self.bea.username}))
        msg = Message.objects.get(sender=self.bea, recipient=self.ana)
        self.assertIsNotNone(msg.read_at)

    def test_inbox_agrupa_por_conversacion(self):
        FriendRequest.objects.create(from_user=self.ana, to_user=self.bea, accepted=True)
        Message.objects.create(sender=self.ana, recipient=self.bea, body="Uno")
        Message.objects.create(sender=self.bea, recipient=self.ana, body="Dos")
        self.client.login(username="ana@test.local", password="Testpass123!")
        response = self.client.get(reverse("social:inbox"))
        conversations = list(response.context["conversations"])
        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0]["user"], self.bea)
