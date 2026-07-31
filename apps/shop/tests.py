from django.test import TestCase
from django.urls import reverse

from .models import Product


class ShopListTests(TestCase):
    """La Tienda es un escaparate puro: se listan los artículos que ponga el
    admin, sin ningún botón de compra ni carrito."""

    def test_lista_los_articulos(self):
        Product.objects.create(name="Taza La Sala de Bygui", price="12.50")
        response = self.client.get(reverse("shop:list"))
        self.assertContains(response, "Taza La Sala de Bygui")

    def test_no_hay_boton_de_compra(self):
        Product.objects.create(name="Póster", price="8.00")
        response = self.client.get(reverse("shop:list"))
        self.assertNotContains(response, "Comprar")
        self.assertNotContains(response, "Añadir al carrito")

    def test_sin_articulos_muestra_mensaje(self):
        response = self.client.get(reverse("shop:list"))
        self.assertContains(response, "Todavía no hay artículos")
