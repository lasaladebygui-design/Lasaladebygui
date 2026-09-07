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


class ShopPaginationSortTests(TestCase):
    def test_pagina_a_partir_de_12_articulos(self):
        for i in range(13):
            Product.objects.create(name=f"Artículo {i}", price="5.00")
        response = self.client.get(reverse("shop:list"))
        self.assertEqual(len(response.context["page_obj"].object_list), 12)
        self.assertContains(response, "Página 1 de 2")

    def test_ordena_por_precio_ascendente(self):
        Product.objects.create(name="Caro", price="50.00")
        Product.objects.create(name="Barato", price="5.00")
        response = self.client.get(reverse("shop:list"), {"sort": "price_asc"})
        content = response.content.decode()
        self.assertLess(content.index("Barato"), content.index("Caro"))

    def test_orden_por_defecto_es_novedades(self):
        response = self.client.get(reverse("shop:list"))
        self.assertEqual(response.context["sort"], "new")
