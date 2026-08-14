import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.mail import get_connection, send_mail
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.push import send_push_to_users

from .forms import ArticleCommentForm, ArticleForm
from .models import Article, ArticleView, Tag
from .permissions import (
    can_create_articles,
    can_delete_article,
    can_edit_article,
    can_feature_articles,
    can_manage_private_articles,
)

logger = logging.getLogger(__name__)


def article_list(request):
    """Scroll infinito: cada tanda de tarjetas trae pegado al final un
    sensor invisible (`hx-trigger="revealed"`) que, en cuanto entra en la
    pantalla al hacer scroll, pide la siguiente página y se reemplaza a sí
    mismo por las nuevas tarjetas + su propio sensor — así hasta que no
    queda página siguiente. Si la petición viene de ahí (cabecera
    HX-Request), se devuelve solo el fragmento de tarjetas, no la página
    entera."""
    articles = Article.objects.select_related("author").prefetch_related("tags")
    if not can_manage_private_articles(request.user):
        articles = articles.filter(is_private=False)

    if request.user.is_authenticated and not request.headers.get("HX-Request"):
        # Entrar en el tablón marca todo lo visible como visto, igual que
        # abrir cada artículo suelto — si no, la campanita se quedaba
        # "atascada" en un número aunque ya hubieras pasado por aquí,
        # porque solo contaba como visto lo que abrías uno a uno. Solo en
        # la carga completa de la página (no en cada tanda del scroll
        # infinito, que ya iría siendo redundante tras la primera).
        seen_ids = ArticleView.objects.filter(user=request.user).values_list("article_id", flat=True)
        unseen_ids = articles.exclude(pk__in=seen_ids).exclude(author=request.user).values_list("pk", flat=True)
        ArticleView.objects.bulk_create(
            [ArticleView(article_id=pk, user=request.user) for pk in unseen_ids],
            ignore_conflicts=True,
        )

    tag_slug = request.GET.get("tag")
    active_tag = None
    if tag_slug == "none":
        articles = articles.filter(tags__isnull=True)
    elif tag_slug:
        active_tag = get_object_or_404(Tag, slug=tag_slug)
        articles = articles.filter(tags=active_tag)

    query = request.GET.get("q", "").strip()
    if query:
        articles = articles.filter(Q(title__icontains=query) | Q(body__icontains=query)).distinct()

    paginator = Paginator(articles, 9)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page,
        "tags": Tag.objects.all(),
        "active_tag": active_tag,
        "tag_param": tag_slug or "",
        "query": query,
        "can_create": can_create_articles(request.user),
        "can_feature": can_feature_articles(request.user),
    }
    if request.headers.get("HX-Request"):
        return render(request, "articles/_article_cards.html", context)
    return render(request, "articles/list.html", context)


def article_detail(request, slug):
    article = get_object_or_404(
        Article.objects.select_related("author").prefetch_related("tags", "comments__author"),
        slug=slug,
    )
    if article.is_private and not can_manage_private_articles(request.user):
        raise Http404

    comment_form = None
    if request.user.is_authenticated:
        view, created = ArticleView.objects.get_or_create(article=article, user=request.user)
        if not created:
            view.save()
        if request.method == "POST":
            comment_form = ArticleCommentForm(request.POST)
            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.article = article
                comment.author = request.user
                comment.save()
                messages.success(request, "Comentario publicado.")
                return redirect("articles:detail", slug=article.slug)
        else:
            comment_form = ArticleCommentForm()

    latest_articles = Article.objects.exclude(pk=article.pk)
    if not can_manage_private_articles(request.user):
        latest_articles = latest_articles.filter(is_private=False)
    latest_articles = latest_articles[:5]

    return render(request, "articles/detail.html", {
        "article": article,
        "comment_form": comment_form,
        "can_edit": can_edit_article(request.user, article),
        "can_delete": can_delete_article(request.user, article),
        "latest_articles": latest_articles,
    })


def _notify_users_of_new_article(request, article):
    """Avisa por email — nunca debe poder romper la publicación del
    artículo (ya guardado antes de llegar aquí): un fallo de SMTP o una
    lista larga de destinatarios no puede tirar la petición abajo. Cada
    envío va sin fail_silently (para que un fallo real quede registrado en
    los logs, en vez de desaparecer sin dejar pista) pero atrapado uno a
    uno, así un destinatario que falle no se lleva por delante al resto."""
    User = get_user_model()
    recipients = User.objects.filter(
        is_active=True, email_notify_new_articles=True,
    ).exclude(pk=article.author_id).exclude(email="")
    if not recipients.exists():
        return

    url = request.build_absolute_uri(article.get_absolute_url())
    subject = f"Nuevo artículo en La Sala de Bygui: {article.title}"
    message = (
        f"{article.author} ha publicado un nuevo artículo:\n\n"
        f"{article.title}\n{url}\n\n"
        "Puedes desactivar estos avisos desde Ajustes > Notificaciones."
    )
    connection = get_connection()
    connection.open()
    sent = 0
    try:
        for user in recipients:
            try:
                send_mail(
                    subject=subject, message=message, from_email=None,
                    recipient_list=[user.email], connection=connection,
                )
                sent += 1
            except Exception:
                logger.exception("No se pudo avisar por email a %s del artículo «%s»", user.email, article.title)
    finally:
        connection.close()
    logger.info("Aviso de artículo nuevo «%s»: %d/%d emails enviados.", article.title, sent, recipients.count())


@login_required
def article_create(request):
    if not can_create_articles(request.user):
        raise Http404

    if request.method == "POST":
        form = ArticleForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            form.save_m2m()
            messages.success(request, "Artículo publicado.")
            if not article.is_private:
                # El artículo ya está guardado a estas alturas: un fallo al
                # avisar (push o email) nunca debe impedir que se vea la
                # página del artículo recién publicado.
                try:
                    User = get_user_model()
                    subscribers = User.objects.filter(push_subscriptions__isnull=False).exclude(pk=article.author_id).distinct()
                    send_push_to_users(
                        subscribers,
                        title="Nuevo artículo",
                        body=article.title,
                        url=article.get_absolute_url(),
                    )
                    _notify_users_of_new_article(request, article)
                except Exception:
                    logger.exception("Fallo al avisar del artículo nuevo «%s»", article.title)
            return redirect(article.get_absolute_url())
    else:
        form = ArticleForm(user=request.user)

    return render(request, "articles/form.html", {"form": form, "is_new": True})


@login_required
def article_update(request, slug):
    article = get_object_or_404(Article, slug=slug)
    if not can_edit_article(request.user, article):
        raise Http404

    if request.method == "POST":
        form = ArticleForm(request.POST, request.FILES, instance=article, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Artículo actualizado.")
            return redirect(article.get_absolute_url())
    else:
        form = ArticleForm(instance=article, user=request.user)

    return render(request, "articles/form.html", {"form": form, "is_new": False, "article": article})


def _delete_articles_and_orphan_tags(articles):
    # Un tag que se quede sin ningún artículo tras borrar estos ya no sirve
    # para nada (no hay forma de llegar a él desde ningún sitio), así que se
    # borra también — salvo que otro artículo lo siga usando.
    tags = set(Tag.objects.filter(articles__in=articles))
    count = len(articles)
    for article in articles:
        article.delete()
    for tag in tags:
        if not tag.articles.exists():
            tag.delete()
    return count


@login_required
def article_delete(request, slug):
    article = get_object_or_404(Article, slug=slug)
    if not can_delete_article(request.user, article):
        raise Http404

    if request.method == "POST":
        _delete_articles_and_orphan_tags([article])
        messages.success(request, "Artículo eliminado.")
        return redirect("articles:list")

    return render(request, "articles/confirm_delete.html", {"article": article})


@login_required
def article_bulk_delete(request):
    if request.method != "POST":
        raise Http404

    slugs = request.POST.getlist("slugs")
    articles = [
        article for article in Article.objects.filter(slug__in=slugs)
        if can_delete_article(request.user, article)
    ]
    if articles:
        count = _delete_articles_and_orphan_tags(articles)
        messages.success(request, f"{count} artículo(s) eliminado(s).")
    else:
        messages.info(request, "No se ha eliminado ningún artículo.")
    return redirect("articles:list")


@login_required
def article_bulk_feature(request):
    """Marcar en tanda cuáles salen en el carrusel destacado de la
    portada — misma selección de checkboxes que borrar, pero mandando a
    esta URL en vez de a bulk-delete (ver `formaction` en list.html)."""
    if request.method != "POST":
        raise Http404
    if not can_feature_articles(request.user):
        raise Http404

    slugs = request.POST.getlist("slugs")
    count = Article.objects.filter(slug__in=slugs).update(is_featured=True)
    if count:
        messages.success(request, f"{count} artículo(s) marcado(s) como destacados.")
    else:
        messages.info(request, "No se ha marcado ningún artículo.")
    return redirect("articles:list")
