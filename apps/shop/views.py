from django.shortcuts import render

from .models import Product, ProductView


def product_list(request):
    products = Product.objects.all()

    if request.user.is_authenticated:
        # Igual que el tablón de artículos: entrar en el escaparate marca
        # todo lo visible como visto, así la campanita no avisa para
        # siempre del mismo artículo aunque ya hayas pasado por aquí.
        seen_ids = ProductView.objects.filter(user=request.user).values_list("product_id", flat=True)
        unseen_ids = products.exclude(pk__in=seen_ids).values_list("pk", flat=True)
        ProductView.objects.bulk_create(
            [ProductView(product_id=pk, user=request.user) for pk in unseen_ids],
            ignore_conflicts=True,
        )

    return render(request, "shop/list.html", {"products": products})
