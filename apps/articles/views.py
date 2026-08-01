from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.push import send_push_to_users

from .forms import ArticleCommentForm, ArticleForm
from .models import Article, Tag
from .permissions import can_create_articles, can_delete_article, can_edit_article


def article_list(request):
    articles = Article.objects.select_related("author").prefetch_related("tags")

    tag_slug = request.GET.get("tag")
    active_tag = None
    if tag_slug:
        active_tag = get_object_or_404(Tag, slug=tag_slug)
        articles = articles.filter(tags=active_tag)

    paginator = Paginator(articles, 9)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "articles/list.html", {
        "page_obj": page,
        "tags": Tag.objects.all(),
        "active_tag": active_tag,
        "can_create": can_create_articles(request.user),
    })


def article_detail(request, slug):
    article = get_object_or_404(
        Article.objects.select_related("author").prefetch_related("tags", "comments__author"),
        slug=slug,
    )

    comment_form = None
    if request.user.is_authenticated:
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

    latest_articles = Article.objects.exclude(pk=article.pk)[:5]

    return render(request, "articles/detail.html", {
        "article": article,
        "comment_form": comment_form,
        "can_edit": can_edit_article(request.user, article),
        "can_delete": can_delete_article(request.user, article),
        "latest_articles": latest_articles,
    })


@login_required
def article_create(request):
    if not can_create_articles(request.user):
        raise Http404

    if request.method == "POST":
        form = ArticleForm(request.POST, request.FILES)
        if form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            form.save_m2m()
            messages.success(request, "Artículo publicado.")
            User = get_user_model()
            subscribers = User.objects.filter(push_subscriptions__isnull=False).exclude(pk=article.author_id).distinct()
            send_push_to_users(
                subscribers,
                title="Nuevo artículo",
                body=article.title,
                url=article.get_absolute_url(),
            )
            return redirect(article.get_absolute_url())
    else:
        form = ArticleForm()

    return render(request, "articles/form.html", {"form": form, "is_new": True})


@login_required
def article_update(request, slug):
    article = get_object_or_404(Article, slug=slug)
    if not can_edit_article(request.user, article):
        raise Http404

    if request.method == "POST":
        form = ArticleForm(request.POST, request.FILES, instance=article)
        if form.is_valid():
            form.save()
            messages.success(request, "Artículo actualizado.")
            return redirect(article.get_absolute_url())
    else:
        form = ArticleForm(instance=article)

    return render(request, "articles/form.html", {"form": form, "is_new": False, "article": article})


@login_required
def article_delete(request, slug):
    article = get_object_or_404(Article, slug=slug)
    if not can_delete_article(request.user, article):
        raise Http404

    if request.method == "POST":
        # Un tag que se quede sin ningún artículo tras borrar este ya no
        # sirve para nada (no hay forma de llegar a él desde ningún sitio),
        # así que se borra también — salvo que otro artículo lo siga usando.
        tags = list(article.tags.all())
        article.delete()
        for tag in tags:
            if not tag.articles.exists():
                tag.delete()
        messages.success(request, "Artículo eliminado.")
        return redirect("articles:list")

    return render(request, "articles/confirm_delete.html", {"article": article})
