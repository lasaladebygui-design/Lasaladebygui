import random
from functools import wraps

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CodeForm, NumberSelectForm, RatingSearchForm
from .models import SecretMovie, TopSecretConfig

SESSION_KEY = "top_secret_unlocked"


def secret_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.session.get(SESSION_KEY):
            messages.info(request, "Introduce el código para entrar en el maletín.")
            return redirect("secret:gate")
        return view_func(request, *args, **kwargs)
    return wrapped


def gate(request):
    if request.session.get(SESSION_KEY):
        return redirect("secret:home")

    if request.method == "POST":
        form = CodeForm(request.POST)
        if form.is_valid():
            config = TopSecretConfig.load()
            if config.check_code(form.cleaned_data["code"]):
                request.session[SESSION_KEY] = True
                return redirect("secret:home")
            form.add_error("code", "Código incorrecto.")
    else:
        form = CodeForm()

    return render(request, "secret/gate.html", {"form": form})


def lock(request):
    request.session.pop(SESSION_KEY, None)
    messages.info(request, "Maletín cerrado.")
    return redirect("secret:gate")


@secret_required
def home(request):
    return render(request, "secret/home.html")


@secret_required
def by_number(request):
    form = NumberSelectForm(request.GET or None)
    result = None
    if request.GET and form.is_valid():
        result = get_object_or_404(SecretMovie, number=form.cleaned_data["number"])
    return render(request, "secret/by_number.html", {"form": form, "result": result})


@secret_required
def by_rating(request):
    form = RatingSearchForm(request.GET or None)
    result = None
    searched = False
    if request.GET and form.is_valid():
        searched = True
        min_r, max_r = int(form.cleaned_data["min_rating"]), int(form.cleaned_data["max_rating"])
        matches = list(SecretMovie.objects.filter(personal_rating__gte=min_r, personal_rating__lte=max_r))
        if matches:
            result = random.choice(matches)
    return render(request, "secret/by_rating.html", {"form": form, "result": result, "searched": searched})


@secret_required
def full_list(request):
    movies = SecretMovie.objects.all()
    return render(request, "secret/list.html", {"movies": movies})
