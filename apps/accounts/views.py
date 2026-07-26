from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core.models import SiteConfig

from .forms import EmailAuthenticationForm, ProfileThemeForm, RegisterForm
from .models import EmailVerificationToken, User


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
        form = ProfileThemeForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Preferencias actualizadas.")
            return redirect("accounts:profile")
    else:
        form = ProfileThemeForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})


@login_required
def resend_verification(request):
    user = request.user
    if user.email_verified:
        messages.info(request, "Tu email ya está verificado.")
    else:
        _send_verification_email(request, user)
        messages.success(request, "Te hemos reenviado el email de verificación.")
    return redirect("core:home")
