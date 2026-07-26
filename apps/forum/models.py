from django.conf import settings
from django.db import models
from django.urls import reverse


class Thread(models.Model):
    title = models.CharField("título", max_length=200)
    body = models.TextField("mensaje")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="autor",
        on_delete=models.SET_NULL,
        null=True,
        related_name="threads",
    )
    is_locked = models.BooleanField(
        "cerrado",
        default=False,
        help_text="Si está cerrado, ya no se pueden añadir comentarios (moderación).",
    )
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "hilo"
        verbose_name_plural = "hilos"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("forum:detail", args=[self.pk])


class ThreadComment(models.Model):
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="thread_comments"
    )
    body = models.TextField("comentario")
    is_deleted = models.BooleanField("eliminado", default=False)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "comentario de foro"
        verbose_name_plural = "comentarios de foro"
        ordering = ["created_at"]

    def __str__(self):
        return f"Comentario de {self.author} en {self.thread}"

    @property
    def display_body(self):
        return "[comentario eliminado]" if self.is_deleted else self.body

    @property
    def display_author(self):
        if self.is_deleted:
            return "—"
        return self.author or "usuario eliminado"
