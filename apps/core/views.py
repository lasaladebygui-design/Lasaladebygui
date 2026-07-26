from django.contrib import messages
from django.core.mail import EmailMessage
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from django.views.decorators.cache import cache_control

from apps.articles.models import Article

from .forms import ContactForm
from .models import SiteConfig, get_effective_theme


def home(request):
    articles = Article.objects.select_related("author").prefetch_related("tags")[:4]
    return TemplateResponse(request, "core/home.html", {"featured_articles": articles})


def donations(request):
    return render(request, "core/donations.html", {"site_config": SiteConfig.load()})


def contact(request):
    config = SiteConfig.load()

    if not config.contact_email:
        return render(request, "core/contact.html", {"form": None})

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            if not form.is_spam():
                EmailMessage(
                    subject=f"[Contacto La Sala de Bygui] {form.cleaned_data['name']}",
                    body=(
                        f"De: {form.cleaned_data['name']} <{form.cleaned_data['email']}>\n\n"
                        f"{form.cleaned_data['message']}"
                    ),
                    to=[config.contact_email],
                    reply_to=[form.cleaned_data["email"]],
                ).send()
            messages.success(request, "¡Mensaje enviado! Te responderemos lo antes posible.")
            return redirect("core:contact")
    else:
        form = ContactForm()

    return render(request, "core/contact.html", {"form": form})


@cache_control(private=True, max_age=30)
def theme_css(request):
    theme = get_effective_theme(request.user)
    return TemplateResponse(
        request, "core/theme.css", {"theme": theme}, content_type="text/css"
    )
