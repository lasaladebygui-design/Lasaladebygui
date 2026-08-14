from django import forms

from .models import Genre, SecretMovie, SecretPhoto, TierLevel

RATING_CHOICES = [(i, str(i)) for i in range(1, 11)]


class SecretMovieForm(forms.ModelForm):
    # Antes era un único campo de texto ("sepáralas con comas") — había que
    # recordar y volver a escribir el nombre exacto de cada lista existente
    # cada vez, con riesgo de typos creando listas duplicadas casi iguales.
    # Ahora las que ya existen se marcan con casillas (rápido, sin errores)
    # y solo hace falta escribir algo si la lista es de verdad nueva.
    genres = forms.ModelMultipleChoiceField(
        label="Listas existentes",
        queryset=Genre.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    new_genres_input = forms.CharField(
        label="Listas nuevas",
        required=False,
        help_text="Solo para listas que todavía no existan — sepáralas con comas.",
    )

    class Meta:
        model = SecretMovie
        fields = ["title", "personal_rating", "tie_break", "comment", "movie"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["genres"].initial = self.instance.genres.all()

    def save(self, commit=True):
        movie = super().save(commit=commit)

        def sync_genres():
            genres = list(self.cleaned_data["genres"])
            new_names = [n.strip() for n in self.cleaned_data["new_genres_input"].split(",") if n.strip()]
            genres += [Genre.objects.get_or_create(name=name)[0] for name in new_names]
            movie.genres.set(genres)

        if commit:
            sync_genres()
        else:
            self.save_m2m = sync_genres
        return movie


class CodeForm(forms.Form):
    code = forms.CharField(label="Código", widget=forms.PasswordInput(attrs={"autocomplete": "off", "autofocus": True}))


class NumberSelectForm(forms.Form):
    # Antes era un desplegable con todos los números existentes — con
    # varias decenas de películas, buscar el número a mano en una lista
    # larga es más lento que teclearlo directamente.
    number = forms.IntegerField(
        label="Número", min_value=1,
        widget=forms.NumberInput(attrs={"inputmode": "numeric", "class": "input-number-plain"}),
    )


class RatingSearchForm(forms.Form):
    min_rating = forms.ChoiceField(label="Nota mínima", choices=RATING_CHOICES, initial=7)
    max_rating = forms.ChoiceField(label="Nota máxima", choices=RATING_CHOICES, initial=9)

    def clean(self):
        cleaned = super().clean()
        min_r, max_r = cleaned.get("min_rating"), cleaned.get("max_rating")
        if min_r and max_r and int(min_r) > int(max_r):
            raise forms.ValidationError("La nota mínima no puede ser mayor que la máxima.")
        return cleaned


class FullListFilterForm(forms.Form):
    genres = forms.ModelMultipleChoiceField(
        label="Listas",
        queryset=Genre.objects.all(),
        to_field_name="slug",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Marca varias para cruzarlas: solo aparecen las películas que estén en todas las marcadas.",
    )

    def __init__(self, *args, admin_user=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not admin_user:
            self.fields["genres"].queryset = Genre.objects.filter(admin_only=False)


class TierLevelForm(forms.ModelForm):
    class Meta:
        model = TierLevel
        fields = ["name", "color"]
        labels = {"name": "Nombre", "color": "Color"}
        widgets = {
            "name": forms.TextInput(attrs={"maxlength": 30}),
            "color": forms.TextInput(attrs={"type": "color"}),
        }


class SecretPhotoForm(forms.ModelForm):
    class Meta:
        model = SecretPhoto
        fields = ["image", "description"]
        labels = {"image": "Foto", "description": "Descripción"}
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "Una pequeña descripción..."}),
        }
