from django import forms

from .models import GameTierLevel


class GameTierLevelForm(forms.ModelForm):
    class Meta:
        model = GameTierLevel
        fields = ["name", "color"]
        labels = {"name": "Nombre", "color": "Color"}
        widgets = {
            "name": forms.TextInput(attrs={"maxlength": 30}),
            "color": forms.TextInput(attrs={"type": "color"}),
        }
