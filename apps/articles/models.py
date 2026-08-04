from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from django_ckeditor_5.fields import CKEditor5Field


class Tag(models.Model):
    """Lista temática de Artículos (p. ej. "drama", "años 90") — mismo
    patrón que las listas de Guardadas: texto libre, se crea sobre la
    marcha al escribirla, y sirve tanto para clasificar como para
    filtrar el tablón."""

    name = models.CharField("nombre", max_length=50, unique=True)
    slug = models.SlugField("slug", max_length=60, unique=True, blank=True)

    class Meta:
        verbose_name = "lista"
        verbose_name_plural = "listas"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Article(models.Model):
    title = models.CharField("título", max_length=200)
    slug = models.SlugField("slug", max_length=220, unique=True, blank=True)
    cover = models.ImageField("portada", upload_to="articles/covers/", blank=True, null=True)
    body = CKEditor5Field("cuerpo", config_name="default")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="autor",
        on_delete=models.SET_NULL,
        null=True,
        related_name="articles",
    )
    tags = models.ManyToManyField(Tag, verbose_name="listas", blank=True, related_name="articles")
    created_at = models.DateTimeField("fecha de publicación", auto_now_add=True)
    updated_at = models.DateTimeField("última edición", auto_now=True)

    class Meta:
        verbose_name = "artículo"
        verbose_name_plural = "artículos"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or "articulo"
            candidate = base
            suffix = 0
            while Article.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                suffix += 1
                candidate = f"{base}-{suffix}"
            self.slug = candidate
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("articles:detail", args=[self.slug])


class ArticleComment(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="article_comments")
    body = models.TextField("comentario")
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "comentario"
        verbose_name_plural = "comentarios"
        ordering = ["created_at"]

    def __str__(self):
        return f"Comentario de {self.author} en {self.article}"


class ArticleView(models.Model):
    """Quién ha leído cada artículo — no es visible en la web pública, solo
    para el equipo desde el admin, para poder trackear quién los lee."""

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="views")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.CASCADE, related_name="+",
    )
    viewed_at = models.DateTimeField("visto por última vez", auto_now=True)

    class Meta:
        verbose_name = "vista"
        verbose_name_plural = "vistas"
        constraints = [models.UniqueConstraint(fields=["article", "user"], name="una_vista_por_usuario_y_articulo")]

    def __str__(self):
        return f"{self.user} vio «{self.article}»"
