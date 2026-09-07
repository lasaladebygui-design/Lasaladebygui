from django.core.paginator import Paginator
from django.shortcuts import render

from .models import Product, ProductView

SORT_OPTIONS = {
    "new": ("-created_at", "Novedades primero"),
    "price_asc": ("price", "Precio: menor a mayor"),
    "price_desc": ("-price", "Precio: mayor a menor"),
}
DEFAULT_SORT = "new"


def product_list(request):
    sort = request.GET.get("sort") if request.GET.get("sort") in SORT_OPTIONS else DEFAULT_SORT
    products = Product.objects.order_by(SORT_OPTIONS[sort][0])

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

    page_obj = Paginator(products, 12).get_page(request.GET.get("page"))

    return render(request, "shop/list.html", {
        "page_obj": page_obj, "sort": sort, "sort_options": SORT_OPTIONS,
    })
