from django.db import models


class Product(models.Model):
    """Artículo del escaparate de la Tienda: solo para enseñar (merchandising,
    deseos...), no hay carrito ni pago — se gestiona entero desde el admin."""

    name = models.CharField("nombre", max_length=200)
    description = models.TextField("descripción", blank=True)
    image = models.ImageField("imagen", upload_to="shop/products/", blank=True, null=True)
    price = models.DecimalField("precio orientativo", max_digits=8, decimal_places=2, blank=True, null=True)
    url = models.URLField("enlace externo (opcional)", blank=True)
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        verbose_name = "artículo"
        verbose_name_plural = "Tienda: artículos"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name
