from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.staticfiles import finders
from django.core.mail import EmailMessage
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST

from apps.articles.models import Article
from apps.articles.permissions import can_manage_private_articles

from .forms import ContactForm
from .models import SESSION_THEME_KEY, ContactLink, SiteConfig, Theme, get_effective_theme


def home(request):
    articles = Article.objects.select_related("author").prefetch_related("tags")
    if not can_manage_private_articles(request.user):
        articles = articles.filter(is_private=False)
    return TemplateResponse(request, "core/home.html", {"featured_articles": articles[:5]})


def donations(request):
    return render(request, "core/donations.html", {"site_config": SiteConfig.load()})


def contact(request):
    config = SiteConfig.load()
    contact_links = ContactLink.objects.all()

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

    return render(request, "core/contact.html", {"form": form, "contact_links": contact_links})


@staff_member_required
def theme_preview(request):
    """Página de muestra (header, tarjetas, botones, texto) que se carga en
    un <iframe> dentro del formulario de tema del admin — el JS de ahí
    (static/js/admin_theme_preview.js) cambia las variables CSS de este
    documento en vivo, según se editan los campos, sin tener que guardar
    para verlo. Vive en su propia página (no en el propio admin) para que
    los estilos de main.css no puedan chocar con los del admin."""
    return render(request, "core/theme_preview.html")


@cache_control(private=True, no_cache=True)
def theme_css(request):
    theme = get_effective_theme(request.user, request.session)
    return TemplateResponse(
        request, "core/theme.css", {"theme": theme}, content_type="text/css"
    )


def _theme_redirect_or_json(request, slug):
    """El selector de temas de la cabecera lo llama por fetch() (espera
    JSON), pero el de Ajustes usa un <form> normal con un campo oculto
    "next" — sin JS que reaccione a la respuesta, así que ahí hace falta
    una redirección de verdad en vez de un JSON en pantalla."""
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return JsonResponse({"ok": True, "slug": slug})


@require_POST
def set_theme(request, slug):
    theme = get_object_or_404(Theme, slug=slug)
    if request.user.is_authenticated:
        request.user.theme = theme
        request.user.save(update_fields=["theme"])
    else:
        request.session[SESSION_THEME_KEY] = theme.slug
    return _theme_redirect_or_json(request, theme.slug)


@require_POST
def reset_theme(request):
    if request.user.is_authenticated:
        request.user.theme = None
        request.user.save(update_fields=["theme"])
    request.session.pop(SESSION_THEME_KEY, None)
    return _theme_redirect_or_json(request, None)


def service_worker(request):
    """Se sirve en /sw.js (no en /static/js/sw.js): el scope por defecto de
    un service worker es el directorio de su propia URL, así que si viviera
    bajo /static/js/ nunca podría controlar el resto del sitio."""
    path = finders.find("js/sw.js")
    if not path:
        raise Http404
    response = FileResponse(open(path, "rb"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response
