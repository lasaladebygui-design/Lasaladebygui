from django.conf import settings
from django.db import models
from django.db.models import Q


class FriendRequest(models.Model):
    """Solicitud de amistad. Mientras `accepted=False` es una solicitud
    pendiente; al aceptarla, ambos usuarios pasan a ser amigos (no hay un
    modelo Friendship aparte: la propia fila aceptada ES la amistad)."""

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_friend_requests"
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_friend_requests"
    )
    accepted = models.BooleanField("aceptada", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "solicitud de amistad"
        verbose_name_plural = "solicitudes de amistad"
        constraints = [models.UniqueConstraint(fields=["from_user", "to_user"], name="una_solicitud_por_par")]

    def __str__(self):
        estado = "amigos" if self.accepted else "pendiente"
        return f"{self.from_user} → {self.to_user} ({estado})"


def are_friends(user_a, user_b):
    return FriendRequest.objects.filter(
        Q(from_user=user_a, to_user=user_b) | Q(from_user=user_b, to_user=user_a),
        accepted=True,
    ).exists()


def friends_of(user):
    accepted = FriendRequest.objects.filter(
        Q(from_user=user, accepted=True) | Q(to_user=user, accepted=True)
    ).select_related("from_user", "to_user")
    return [fr.to_user if fr.from_user_id == user.pk else fr.from_user for fr in accepted]


def friendship_status(viewer, other):
    """'self' | 'friends' | 'pending_outgoing' | 'pending_incoming' | 'none',
    desde el punto de vista de `viewer` mirando el perfil de `other`."""
    if viewer.pk == other.pk:
        return "self"
    if are_friends(viewer, other):
        return "friends"
    if FriendRequest.objects.filter(from_user=viewer, to_user=other, accepted=False).exists():
        return "pending_outgoing"
    if FriendRequest.objects.filter(from_user=other, to_user=viewer, accepted=False).exists():
        return "pending_incoming"
    return "none"


class Message(models.Model):
    """Mensaje privado entre dos amigos (o de "Escríbenos" hacia un admin,
    ver `is_contact`)."""

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_messages")
    body = models.TextField("mensaje")
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    is_contact = models.BooleanField(
        "mensaje de «Escríbenos»", default=False,
        help_text="Llegó desde el formulario de contacto, no escrito a mano en un chat.",
    )

    class Meta:
        verbose_name = "mensaje"
        verbose_name_plural = "mensajes"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender} → {self.recipient}: {self.body[:40]}"


CONTACT_BOT_EMAIL = "buzon-contacto@lasaladebygui.local"


def get_contact_bot_user():
    """Cuenta fija que agrupa los mensajes de "Escríbenos" de quien no
    tiene cuenta en el sitio — así el mensaje sigue siendo un `Message`
    normal (sender != recipient) en vez del autoenvío de antes, que
    rompía la conversación al abrirla (ver `ensure_friends`)."""
    from apps.accounts.models import User

    bot = User.objects.filter(email=CONTACT_BOT_EMAIL).first()
    if bot is None:
        bot = User(email=CONTACT_BOT_EMAIL, username="buzon-contacto", role=User.Role.LECTOR)
        bot.set_unusable_password()
        bot.save()
    return bot


def ensure_friends(user_a, user_b):
    """Dos usuarios quedan como amigos (aceptados) sin pasar por una
    solicitud manual — usado para que quien escribe desde /contacto/ (o el
    Buzón de contacto, si no tiene cuenta) pueda abrir una conversación de
    verdad con cada admin, ya que `conversation` exige amistad."""
    if user_a.pk == user_b.pk:
        return
    existing = FriendRequest.objects.filter(
        Q(from_user=user_a, to_user=user_b) | Q(from_user=user_b, to_user=user_a)
    ).first()
    if existing:
        if not existing.accepted:
            existing.accepted = True
            existing.save(update_fields=["accepted"])
    else:
        FriendRequest.objects.create(from_user=user_a, to_user=user_b, accepted=True)
