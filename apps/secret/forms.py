from django import forms

from .models import Genre, SecretMovie, SecretPhoto, TierLevel

RATING_CHOICES = [(i, str(i)) for i in range(1, 11)]


class SecretMovieForm(forms.ModelForm):
    # Antes era un único campo de texto ("sepáralas con comas") — había que
    # recordar y volver a escribir el nombre exacto de cada lista existente
    # cada vez, con riesgo de typos creando listas duplicadas casi iguales.
    # Ahora las que ya existen se marcan con casillas (rápido, sin errores)
    # y solo hace falta escribir algo si la lista es de verdad nueva.
    #
    # El admin ahora ve TODAS las entradas (la de Bygui y la propia de
    # cada usuario, ver SecretMovieAdmin) -- las listas (Genre) que se
    # ofrecen aquí son las del MISMO dueño que la entrada que se está
    # editando (Bygui al crear una nueva desde aquí), nunca una mezcla.
    genres = forms.ModelMultipleChoiceField(
        label="Listas existentes",
        queryset=Genre.objects.none(),
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
        fields = ["title", "personal_rating", "tie_break", "comment", "movie", "series_watch_status", "admin_only"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._genre_owner = self.instance.owner if self.instance.pk else None
        self.fields["genres"].queryset = Genre.objects.filter(owner=self._genre_owner)
        if self.instance.pk:
            self.fields["genres"].initial = self.instance.genres.filter(owner=self._genre_owner)

    def save(self, commit=True):
        movie = super().save(commit=commit)

        def sync_genres():
            genres = list(self.cleaned_data["genres"])
            new_names = [n.strip() for n in self.cleaned_data["new_genres_input"].split(",") if n.strip()]
            genres += [Genre.objects.get_or_create(owner=self._genre_owner, name=name)[0] for name in new_names]
            other_genres = movie.genres.exclude(owner=self._genre_owner)
            movie.genres.set(genres + list(other_genres))

        if commit:
            sync_genres()
        else:
            self.save_m2m = sync_genres
        return movie


class SecretMovieQuickEditForm(forms.ModelForm):
    """Version reducida de SecretMovieForm para editar desde una lista
    completa (no el admin): título, nota, desempate y listas -- la portada
    se busca y enlaza aparte (ver movie_poster_search/movie_poster_set en
    views.py). `owner` decide de qué lista son las listas (Genre)
    disponibles para marcar/crear: la de Bygui (owner=None) o la propia de
    quien edita -- cada una con su propio espacio de nombres, ver
    Genre.Meta.constraints."""

    genres = forms.ModelMultipleChoiceField(
        label="Listas existentes",
        queryset=Genre.objects.none(),
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
        fields = ["title", "personal_rating", "tie_break", "comment"]

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._genre_owner = owner
        self.fields["genres"].queryset = Genre.objects.filter(owner=owner)
        if self.instance.pk:
            self.fields["genres"].initial = self.instance.genres.filter(owner=owner)

    def save(self, commit=True):
        movie = super().save(commit=commit)

        def sync_genres():
            genres = list(self.cleaned_data["genres"])
            new_names = [n.strip() for n in self.cleaned_data["new_genres_input"].split(",") if n.strip()]
            genres += [Genre.objects.get_or_create(owner=self._genre_owner, name=name)[0] for name in new_names]
            # Solo se tocan las listas del mismo dueño que se estaban
            # editando -- si la película tuviera listas de otro origen (no
            # debería, pero por si acaso) no se pierden al guardar.
            other_genres = movie.genres.exclude(owner=self._genre_owner)
            movie.genres.set(genres + list(other_genres))

        if commit:
            sync_genres()
        else:
            self.save_m2m = sync_genres
        return movie


class GenreQuickForm(forms.ModelForm):
    class Meta:
        model = Genre
        fields = ["name"]
        labels = {"name": "Nombre de la lista nueva"}


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
        queryset=Genre.objects.none(),
        to_field_name="slug",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Marca varias para cruzarlas: solo aparecen las películas que estén en todas las marcadas.",
    )

    def __init__(self, *args, owner=None, admin_user=False, **kwargs):
        super().__init__(*args, **kwargs)
        genres = Genre.objects.filter(owner=owner)
        if owner is None and not admin_user:
            genres = genres.filter(admin_only=False)
        self.fields["genres"].queryset = genres


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
