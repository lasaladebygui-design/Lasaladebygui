from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import FavoriteMovie, User
from apps.core.push import send_push_to_user
from apps.games.models import DuelRecord

from .models import CONTACT_BOT_EMAIL, FriendRequest, Message, friends_of, friendship_status


@login_required
def public_profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    if profile_user.pk == request.user.pk:
        return redirect("accounts:profile")

    status = friendship_status(request.user, profile_user)
    incoming_request = None
    outgoing_request = None
    if status == "pending_incoming":
        incoming_request = FriendRequest.objects.filter(
            from_user=profile_user, to_user=request.user, accepted=False
        ).first()
    elif status == "pending_outgoing":
        outgoing_request = FriendRequest.objects.filter(
            from_user=request.user, to_user=profile_user, accepted=False
        ).first()

    duel_record = DuelRecord.get_for(request.user, profile_user)
    duel_wins = duel_record.wins_for(request.user) if duel_record else 0
    duel_losses = duel_record.losses_for(request.user) if duel_record else 0
    duel_draws = duel_record.draws if duel_record else 0

    favorites = FavoriteMovie.objects.filter(user=profile_user)

    return render(request, "social/public_profile.html", {
        "profile_user": profile_user, "status": status, "incoming_request": incoming_request,
        "outgoing_request": outgoing_request,
        "duel_wins": duel_wins, "duel_losses": duel_losses, "duel_draws": duel_draws,
        "essential_count": favorites.filter(category="essential").count(),
        "suggested_count": favorites.filter(category="suggested").count(),
    })


@login_required
def send_friend_request(request, username):
    other = get_object_or_404(User, username=username)
    if request.method == "POST" and other.pk != request.user.pk:
        incoming = FriendRequest.objects.filter(from_user=other, to_user=request.user, accepted=False).first()
        if incoming:
            incoming.accepted = True
            incoming.save(update_fields=["accepted"])
            messages.success(request, f"Ahora eres amigo de {other.username}.")
        else:
            _, created = FriendRequest.objects.get_or_create(from_user=request.user, to_user=other)
            if created:
                messages.success(request, "Solicitud de amistad enviada.")
    return redirect("social:public-profile", username=username)


@login_required
def respond_friend_request(request, pk, action):
    friend_request = get_object_or_404(FriendRequest, pk=pk, to_user=request.user, accepted=False)
    if request.method == "POST":
        if action == "accept":
            friend_request.accepted = True
            friend_request.save(update_fields=["accepted"])
            messages.success(request, f"Ahora eres amigo de {friend_request.from_user.username}.")
        elif action == "decline":
            friend_request.delete()
            messages.info(request, "Solicitud rechazada.")
        else:
            raise Http404
    return redirect("social:friends")


@login_required
def withdraw_friend_request(request, pk):
    """Retirar una solicitud que TÚ enviaste (antes solo se podía aceptar o
    rechazar la que te llegaba a ti, no deshacer la tuya). Al borrarla deja
    de contar para la campanita del destinatario — no queda ningún aviso
    de una solicitud que ya no existe."""
    friend_request = get_object_or_404(FriendRequest, pk=pk, from_user=request.user, accepted=False)
    if request.method == "POST":
        friend_request.delete()
        messages.info(request, "Solicitud retirada.")
    return redirect("social:friends")


@login_required
def remove_friend(request, username):
    other = get_object_or_404(User, username=username)
    if request.method == "POST":
        FriendRequest.objects.filter(
            Q(from_user=request.user, to_user=other) | Q(from_user=other, to_user=request.user)
        ).delete()
        messages.info(request, f"Ya no eres amigo de {other.username}.")
    return redirect("social:public-profile", username=username)


@login_required
def friends_list(request):
    friends = friends_of(request.user)
    incoming = FriendRequest.objects.filter(to_user=request.user, accepted=False).select_related("from_user")
    outgoing = FriendRequest.objects.filter(from_user=request.user, accepted=False).select_related("to_user")

    return render(request, "social/friends_list.html", {
        "friends": friends, "incoming": incoming, "outgoing": outgoing,
    })


@login_required
def social_home(request):
    query = request.GET.get("q", "").strip()
    results = []
    if query:
        results = (
            User.objects.filter(username__icontains=query)
            .exclude(pk=request.user.pk).exclude(email=CONTACT_BOT_EMAIL)[:20]
        )

    thread_messages = Message.objects.filter(
        Q(sender=request.user) | Q(recipient=request.user)
    ).select_related("sender", "recipient").order_by("-created_at")

    conversations = {}
    for msg in thread_messages:
        other = msg.recipient if msg.sender_id == request.user.pk else msg.sender
        entry = conversations.setdefault(other.pk, {"user": other, "last_message": msg, "unread": 0})
        if msg.recipient_id == request.user.pk and msg.read_at is None:
            entry["unread"] += 1

    pending_incoming = FriendRequest.objects.filter(to_user=request.user, accepted=False).count()

    return render(request, "social/home.html", {
        "query": query,
        "results": results,
        "conversations": conversations.values(),
        "pending_incoming": pending_incoming,
    })


@login_required
def message_edit(request, pk):
    msg = get_object_or_404(Message, pk=pk, sender=request.user)
    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            msg.body = body
            msg.save(update_fields=["body"])
    return redirect("social:conversation", username=msg.recipient.username)


@login_required
def message_delete(request, pk):
    msg = get_object_or_404(Message, pk=pk, sender=request.user)
    other_username = msg.recipient.username
    if request.method == "POST":
        msg.delete()
    return redirect("social:conversation", username=other_username)


@login_required
def conversation(request, username):
    other = get_object_or_404(User, username=username)
    if friendship_status(request.user, other) != "friends":
        raise Http404

    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            Message.objects.create(sender=request.user, recipient=other, body=body)
            send_push_to_user(
                other,
                title="Nuevo mensaje",
                body=f"{request.user}: {body[:80]}",
                url=reverse("social:conversation", args=[request.user.username]),
            )
        return redirect("social:conversation", username=username)

    Message.objects.filter(sender=other, recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())

    thread = Message.objects.filter(
        Q(sender=request.user, recipient=other) | Q(sender=other, recipient=request.user)
    )

    return render(request, "social/conversation.html", {"other": other, "thread": thread})
