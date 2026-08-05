import json
import secrets

import requests
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.google_calendar import exchange_code_for_tokens, get_authorization_url, google_calendar_enabled
from apps.core.models import SiteConfig
from apps.movies.models import Movie
from apps.movies.services import MovieAPIError, tmdb_search
from apps.secret.models import ReleaseEvent

from .forms import EmailAuthenticationForm, ProfileForm, RegisterForm
from .models import EmailVerificationToken, FavoriteMovie, GoogleCalendarConnection, PushSubscription, User


def _send_verification_email(request, user):
    token = EmailVerificationToken.objects.create(user=user)
    verify_url = request.build_absolute_uri(
        reverse("accounts:verify-email", args=[token.token])
    )
    message = render_to_string(
        "accounts/email/verify_email.txt",
        {"user": user, "verify_url": verify_url},
    )
    send_mail(
        subject="Confirma tu email en La Sala de Bygui",
        message=message,
        from_email=None,
        recipient_list=[user.email],
    )


def register(request):
    if request.user.is_authenticated:
        return redirect("core:home")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            config = SiteConfig.load()
            if config.require_email_verification:
                _send_verification_email(request, user)
                messages.success(
                    request,
                    "¡Cuenta creada! Te hemos enviado un email para confirmarla.",
                )
            else:
                messages.success(request, "¡Bienvenido/a a La Sala de Bygui!")
            return redirect("core:home")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


class EmailLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


def logout_view(request):
    auth_logout(request)
    messages.info(request, "Has cerrado sesión.")
    return redirect("core:home")


def verify_email(request, token):
    verification = get_object_or_404(EmailVerificationToken, token=token)
    if verification.is_used:
        messages.warning(request, "Ese enlace de verificación ya se usó.")
        return redirect("accounts:login")

    user = verification.user
    user.email_verified = True
    user.save(update_fields=["email_verified"])
    from django.utils import timezone

    verification.used_at = timezone.now()
    verification.save(update_fields=["used_at"])

    messages.success(request, "Email confirmado. Ya puedes iniciar sesión.")
    return redirect("accounts:login")


@login_required
def profile(request):
    context = {
        "essential_count": FavoriteMovie.objects.filter(user=request.user, category="essential").count(),
        "suggested_count": FavoriteMovie.objects.filter(user=request.user, category="suggested").count(),
    }
    return render(request, "accounts/profile.html", context)


@login_required
def settings_page(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Foto de perfil actualizada.")
            return redirect("accounts:settings")
    else:
        form = ProfileForm(instance=request.user)

    return render(request, "accounts/settings.html", {
        "form": form,
        "google_calendar_enabled": google_calendar_enabled(),
        "google_calendar_connected": hasattr(request.user, "google_calendar_connection"),
    })


@login_required
@require_POST
def set_intro_animation(request):
    value = request.POST.get("value")
    if value == "on":
        request.user.show_intro_animation = True
    elif value == "off":
        request.user.show_intro_animation = False
    else:
        request.user.show_intro_animation = None
    request.user.save(update_fields=["show_intro_animation"])
    messages.success(request, "Preferencia de animación guardada.")
    return redirect("accounts:settings")


@login_required
@require_POST
def toggle_pwa_prompt(request):
    request.user.hide_pwa_install_prompt = not request.user.hide_pwa_install_prompt
    request.user.save(update_fields=["hide_pwa_install_prompt"])
    return redirect("accounts:settings")


@login_required
@require_POST
def change_email(request):
    new_email = request.POST.get("email", "").strip().lower()
    try:
        validate_email(new_email)
    except ValidationError:
        messages.error(request, "Ese email no es válido.")
        return redirect("accounts:settings")

    if User.objects.filter(email=new_email).exclude(pk=request.user.pk).exists():
        messages.error(request, "Ya hay una cuenta con ese email.")
        return redirect("accounts:settings")

    if new_email == request.user.email:
        messages.info(request, "Ese ya es tu email.")
        return redirect("accounts:settings")

    request.user.email = new_email
    config = SiteConfig.load()
    request.user.email_verified = not config.require_email_verification
    request.user.save(update_fields=["email", "email_verified"])

    if config.require_email_verification:
        _send_verification_email(request, request.user)
        messages.success(request, "Email actualizado. Te hemos enviado un correo para confirmarlo.")
    else:
        messages.success(request, "Email actualizado.")
    return redirect("accounts:settings")


def _favorites_context(favorites):
    def group(category, media_type):
        return [f for f in favorites if f.category == category and f.movie.media_type == media_type]

    return {
        "essential_movies": group(FavoriteMovie.Category.ESSENTIAL, "movie"),
        "essential_tv": group(FavoriteMovie.Category.ESSENTIAL, "tv"),
        "suggested_movies": group(FavoriteMovie.Category.SUGGESTED, "movie"),
        "suggested_tv": group(FavoriteMovie.Category.SUGGESTED, "tv"),
    }


@login_required
def favorites_page(request, category, username=None):
    """Página propia para Imprescindibles o Sugeridas — ya no van integradas
    como pestañas dentro del perfil, sino con dos botones que llevan aquí.
    Sin `username`, es la del propio usuario (editable); con `username`, la
    de otro (solo lectura, se llega desde su perfil público)."""
    if category not in FavoriteMovie.Category.values:
        raise Http404

    if username:
        profile_user = get_object_or_404(User, username=username)
        editable = False
    else:
        profile_user = request.user
        editable = True

    favorites = FavoriteMovie.objects.filter(user=profile_user).select_related("movie")
    note_field = "essential_note" if category == FavoriteMovie.Category.ESSENTIAL else "suggested_note"
    context = {
        "category": category,
        "editable": editable,
        "profile_user": profile_user,
        "category_note": getattr(profile_user, note_field),
        **_favorites_context(favorites),
    }
    return render(request, "accounts/favorites_page.html", context)


@login_required
def favorite_search(request, category, media_type):
    if category not in FavoriteMovie.Category.values or media_type not in ("movie", "tv", "all"):
        raise Http404

    query = request.GET.get("query", "").strip()
    results = []
    error = None
    if query:
        types_to_search = ("movie", "tv") if media_type == "all" else (media_type,)
        try:
            found = []
            for t in types_to_search:
                found += tmdb_search(query, media_type=t)
        except MovieAPIError as exc:
            error = str(exc)
        else:
            results = found[:8]
    return render(request, "accounts/_favorite_search_results.html", {
        "results": results, "error": error, "query": query, "category": category, "media_type": media_type,
    })


@login_required
def favorite_add(request, category, media_type, tmdb_id):
    if request.method == "POST" and category in FavoriteMovie.Category.values and media_type in ("movie", "tv"):
        current_count = FavoriteMovie.objects.filter(
            user=request.user, category=category, movie__media_type=media_type,
        ).count()
        try:
            movie = Movie.get_or_create_from_tmdb(tmdb_id, media_type=media_type)
        except MovieAPIError as exc:
            messages.error(request, str(exc))
        else:
            _, created = FavoriteMovie.objects.get_or_create(
                user=request.user, category=category, movie=movie,
                defaults={"order": current_count},
            )
            if not created:
                messages.info(request, "Ya estaba en la lista.")
    return redirect("accounts:favorites-page", category)


@login_required
def favorite_remove(request, pk):
    favorite = get_object_or_404(FavoriteMovie, pk=pk, user=request.user)
    category = favorite.category
    if request.method == "POST":
        favorite.delete()
    return redirect("accounts:favorites-page", category)


@login_required
def favorite_move(request, pk, direction):
    if request.method != "POST" or direction not in ("up", "down"):
        raise Http404
    favorite = get_object_or_404(FavoriteMovie, pk=pk, user=request.user)
    siblings = list(
        FavoriteMovie.objects.filter(
            user=request.user, category=favorite.category, movie__media_type=favorite.movie.media_type,
        ).select_related("movie").order_by("order", "created_at")
    )
    index = next((i for i, f in enumerate(siblings) if f.pk == favorite.pk), None)
    if index is None:
        raise Http404

    swap_index = index - 1 if direction == "up" else index + 1
    if 0 <= swap_index < len(siblings):
        other = siblings[swap_index]
        favorite.order, other.order = swap_index, index
        FavoriteMovie.objects.bulk_update([favorite, other], ["order"])
    return redirect("accounts:favorites-page", favorite.category)


@login_required
def favorite_category_note(request, category):
    if category not in FavoriteMovie.Category.values:
        raise Http404
    if request.method == "POST":
        field = "essential_note" if category == FavoriteMovie.Category.ESSENTIAL else "suggested_note"
        setattr(request.user, field, request.POST.get("note", "").strip()[:280])
        request.user.save(update_fields=[field])
    return redirect("accounts:favorites-page", category)


@login_required
def resend_verification(request):
    user = request.user
    if user.email_verified:
        messages.info(request, "Tu email ya está verificado.")
    else:
        _send_verification_email(request, user)
        messages.success(request, "Te hemos reenviado el email de verificación.")
    return redirect("core:home")


@login_required
@require_POST
def push_subscribe(request):
    try:
        data = json.loads(request.body)
        endpoint = data["endpoint"]
        p256dh = data["keys"]["p256dh"]
        auth = data["keys"]["auth"]
    except (ValueError, KeyError):
        return JsonResponse({"ok": False, "error": "datos inválidos"}, status=400)

    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={"user": request.user, "p256dh": p256dh, "auth": auth},
    )
    return JsonResponse({"ok": True})


@login_required
@require_POST
def push_unsubscribe(request):
    try:
        endpoint = json.loads(request.body)["endpoint"]
    except (ValueError, KeyError):
        return JsonResponse({"ok": False, "error": "datos inválidos"}, status=400)

    PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    return JsonResponse({"ok": True})


GOOGLE_OAUTH_STATE_SESSION_KEY = "google_oauth_state"


@login_required
def google_calendar_connect(request):
    if not google_calendar_enabled():
        raise Http404
    state = secrets.token_urlsafe(16)
    request.session[GOOGLE_OAUTH_STATE_SESSION_KEY] = state
    redirect_uri = request.build_absolute_uri(reverse("accounts:google-calendar-callback"))
    return redirect(get_authorization_url(redirect_uri, state))


@login_required
def google_calendar_callback(request):
    if not google_calendar_enabled():
        raise Http404

    expected_state = request.session.pop(GOOGLE_OAUTH_STATE_SESSION_KEY, None)
    state = request.GET.get("state")
    if not state or state != expected_state:
        messages.error(request, "No se pudo verificar la conexión con Google. Inténtalo de nuevo.")
        return redirect("secret:calendar")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "Google no autorizó la conexión.")
        return redirect("secret:calendar")

    redirect_uri = request.build_absolute_uri(reverse("accounts:google-calendar-callback"))
    try:
        tokens = exchange_code_for_tokens(code, redirect_uri)
    except requests.RequestException:
        messages.error(request, "No se pudo conectar con Google Calendar. Inténtalo de nuevo.")
        return redirect("secret:calendar")

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        messages.error(request, "Google no devolvió los permisos esperados. Inténtalo de nuevo.")
        return redirect("secret:calendar")

    GoogleCalendarConnection.objects.update_or_create(
        user=request.user,
        defaults={
            "refresh_token": refresh_token,
            "access_token": tokens.get("access_token", ""),
            "access_token_expires_at": timezone.now() + timezone.timedelta(seconds=tokens.get("expires_in", 3600)),
        },
    )
    messages.success(request, "Google Calendar conectado. Los estrenos que se añadan a partir de ahora se crearán solos en tu calendario.")
    return redirect("secret:calendar")


@login_required
@require_POST
def google_calendar_disconnect(request):
    GoogleCalendarConnection.objects.filter(user=request.user).delete()
    # Ese id ya no sirve para nada (no hay con qué borrar el evento del lado
    # de Google si algún día se quita del sitio) — se limpia aquí en vez de
    # dejarlo apuntando a una conexión que ya no existe.
    ReleaseEvent.objects.filter(user=request.user).exclude(google_event_id="").update(google_event_id="")
    messages.info(request, "Google Calendar desconectado.")
    return redirect("secret:calendar")
