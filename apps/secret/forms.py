from django import forms

from .models import Genre, SecretMovie, SecretPhoto, TierLevel

RATING_CHOICES = [(i, str(i)) for i in range(1, 11)]


class SecretMovieForm(forms.ModelForm):
    genres_input = forms.CharField(
        label="Listas",
        required=False,
        help_text="Sepáralas con comas, ej: terror, slasher, años 80",
    )

    class Meta:
        model = SecretMovie
        fields = ["title", "personal_rating", "tie_break", "comment", "movie", "rating_verdict"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["genres_input"].initial = ", ".join(
                self.instance.genres.values_list("name", flat=True)
            )

    def save(self, commit=True):
        movie = super().save(commit=commit)

        def sync_genres():
            names = [n.strip() for n in self.cleaned_data["genres_input"].split(",") if n.strip()]
            genres = [Genre.objects.get_or_create(name=name)[0] for name in names]
            movie.genres.set(genres)

        if commit:
            sync_genres()
        else:
            self.save_m2m = sync_genres
        return movie


class CodeForm(forms.Form):
    code = forms.CharField(label="Código", widget=forms.PasswordInput(attrs={"autocomplete": "off", "autofocus": True}))


class NumberSelectForm(forms.Form):
    number = forms.ChoiceField(label="Número")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["number"].choices = [
            (n, n) for n in SecretMovie.objects.order_by("number").values_list("number", flat=True)
        ]


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
