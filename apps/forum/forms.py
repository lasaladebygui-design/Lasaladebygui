from django import forms

from .models import Thread, ThreadComment


class ThreadForm(forms.ModelForm):
    class Meta:
        model = Thread
        fields = ["title", "body"]
        labels = {"title": "Título del hilo", "body": "Mensaje"}
        widgets = {
            "body": forms.Textarea(attrs={"rows": 5, "placeholder": "Abre el debate…"}),
        }


class ThreadCommentForm(forms.ModelForm):
    class Meta:
        model = ThreadComment
        fields = ["body"]
        labels = {"body": ""}
        widgets = {
            "body": forms.Textarea(attrs={"rows": 3, "placeholder": "Responder…"}),
        }
