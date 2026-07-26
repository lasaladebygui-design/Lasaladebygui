from django import forms

RATING_CHOICES = [(i, str(i)) for i in range(1, 11)]


class RatingRangeForm(forms.Form):
    min_rating = forms.ChoiceField(label="Nota mínima", choices=RATING_CHOICES, initial=7)
    max_rating = forms.ChoiceField(label="Nota máxima", choices=RATING_CHOICES, initial=9)

    def clean(self):
        cleaned = super().clean()
        min_r, max_r = cleaned.get("min_rating"), cleaned.get("max_rating")
        if min_r and max_r and int(min_r) > int(max_r):
            raise forms.ValidationError("La nota mínima no puede ser mayor que la máxima.")
        return cleaned


class VoteForm(forms.Form):
    score = forms.ChoiceField(label="Tu nota", choices=RATING_CHOICES)


class MovieSearchForm(forms.Form):
    query = forms.CharField(
        label="Buscar película",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Título de la película…", "autocomplete": "off"}),
    )
