from django.conf import settings
from django.db import models
from django.utils import timezone


class Product(models.Model):
    """Artículo del escaparate de la Tienda: solo para enseñar (merchandising,
    deseos...), no hay carrito ni pago — se gestiona entero desde el admin."""

    name = models.CharField("nombre", max_length=200)
    description = models.TextField("descripción", blank=True)
    image = models.ImageField("imagen", upload_to="shop/products/", blank=True, null=True)
    price = models.DecimalField("precio orientativo", max_digits=8, decimal_places=2, blank=True, null=True)
    url = models.URLField("enlace externo (opcional)", blank=True)
    order = models.PositiveIntegerField("orden", default=0)
    created_at = models.DateTimeField("añadido", default=timezone.now)

    class Meta:
        verbose_name = "artículo"
        verbose_name_plural = "artículos"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class ProductView(models.Model):
    """Quién ha visto ya cada artículo del escaparate — antes la campanita
    avisaba de "artículo nuevo en la tienda" a TODO el mundo durante 30
    días sin ninguna forma de que un usuario concreto lo marcara como
    visto (a diferencia de los artículos del tablón), así que el aviso
    parecía no desaparecer nunca aunque ya lo hubieras visto."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="views")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="usuario", on_delete=models.CASCADE, related_name="+",
    )
    viewed_at = models.DateTimeField("visto por última vez", auto_now_add=True)

    class Meta:
        verbose_name = "vista"
        verbose_name_plural = "vistas"
        constraints = [models.UniqueConstraint(fields=["product", "user"], name="una_vista_por_usuario_y_articulo_de_tienda")]

    def __str__(self):
        return f"{self.user} vio {self.product}"
