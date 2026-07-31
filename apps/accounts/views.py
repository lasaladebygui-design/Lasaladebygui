from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core.models import SiteConfig
from apps.movies.models import Movie
from apps.movies.services import MovieAPIError, tmdb_search

from .forms import EmailAuthenticationForm, ProfileForm, RegisterForm
from .models import EmailVerificationToken, FavoriteMovie, User


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
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil actualizado.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)

    favorites = FavoriteMovie.objects.filter(user=request.user).select_related("movie")
    return render(request, "accounts/profile.html", {
        "form": form,
        "essentials": [f for f in favorites if f.category == FavoriteMovie.Category.ESSENTIAL],
        "suggested": [f for f in favorites if f.category == FavoriteMovie.Category.SUGGESTED],
    })


@login_required
def favorite_search(request, category):
    if category not in FavoriteMovie.Category.values:
        raise Http404

    query = request.GET.get("query", "").strip()
    results = []
    error = None
    if query:
        try:
            results = tmdb_search(query)[:8]
        except MovieAPIError as exc:
            error = str(exc)
    return render(request, "accounts/_favorite_search_results.html", {
        "results": results, "error": error, "query": query, "category": category,
    })


@login_required
def favorite_add(request, category, tmdb_id):
    if request.method == "POST" and category in FavoriteMovie.Category.values:
        current_count = FavoriteMovie.objects.filter(user=request.user, category=category).count()
        if current_count >= FavoriteMovie.LIMITS[category]:
            messages.error(request, "Ya has llegado al máximo para ese apartado.")
        else:
            try:
                movie = Movie.get_or_create_from_tmdb(tmdb_id)
            except MovieAPIError as exc:
                messages.error(request, str(exc))
            else:
                _, created = FavoriteMovie.objects.get_or_create(
                    user=request.user, category=category, movie=movie,
                    defaults={"order": current_count},
                )
                if not created:
                    messages.info(request, "Esa película ya estaba en la lista.")
    return redirect("accounts:profile")


@login_required
def favorite_remove(request, pk):
    favorite = get_object_or_404(FavoriteMovie, pk=pk, user=request.user)
    if request.method == "POST":
        favorite.delete()
    return redirect("accounts:profile")


@login_required
def resend_verification(request):
    user = request.user
    if user.email_verified:
        messages.info(request, "Tu email ya está verificado.")
    else:
        _send_verification_email(request, user)
        messages.success(request, "Te hemos reenviado el email de verificación.")
    return redirect("core:home")
