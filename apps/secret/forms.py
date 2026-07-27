from django import forms

from .models import SecretMovie, SecretPhoto

RATING_CHOICES = [(i, str(i)) for i in range(1, 11)]


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


class SecretPhotoForm(forms.ModelForm):
    class Meta:
        model = SecretPhoto
        fields = ["image", "description"]
        labels = {"image": "Foto", "description": "Descripción"}
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "Una pequeña descripción..."}),
        }
