from django import forms


class ContactForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=120)
    email = forms.EmailField(label="Tu email")
    message = forms.CharField(label="Mensaje", widget=forms.Textarea(attrs={"rows": 5}))

    # Honeypot anti-spam: invisible para personas, casi siempre relleno por bots.
    # Si llega con contenido, se descarta en la vista sin decírselo al remitente.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"autocomplete": "off"}))

    def is_spam(self):
        return bool(self.cleaned_data.get("website"))
