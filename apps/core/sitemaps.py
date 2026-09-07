"""Sitemap para que Google indexe el contenido público del sitio --
Top Secret y todo lo que exige código de acceso/cuenta queda fuera a
propósito, no tiene sentido ofrecerlo a un buscador."""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.articles.models import Article
from apps.forum.models import Thread
from apps.movies.models import Movie


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.5

    def items(self):
        return ["core:home", "articles:list", "forum:list", "movies:list", "shop:list", "core:donations"]

    def location(self, item):
        return reverse(item)


class ArticleSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.7

    def items(self):
        return Article.objects.filter(is_private=False)

    def lastmod(self, obj):
        return obj.updated_at


class ThreadSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.4

    def items(self):
        return Thread.objects.all()

    def lastmod(self, obj):
        return obj.created_at


class MovieSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return Movie.objects.all()

    def location(self, obj):
        return reverse("movies:detail", args=[obj.pk])
