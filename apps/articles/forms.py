from django import forms

from .models import Article, ArticleComment, Tag


class ArticleForm(forms.ModelForm):
    tags_input = forms.CharField(
        label="Listas",
        required=False,
        help_text="Sepáralas con comas, ej: drama, años 90, animación",
    )

    class Meta:
        model = Article
        fields = ["title", "cover", "body"]
        labels = {"title": "Título", "cover": "Portada"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["tags_input"].initial = ", ".join(
                self.instance.tags.values_list("name", flat=True)
            )

    def save(self, commit=True):
        article = super().save(commit=commit)

        def sync_tags():
            names = [n.strip() for n in self.cleaned_data["tags_input"].split(",") if n.strip()]
            tags = [Tag.objects.get_or_create(name=name)[0] for name in names]
            article.tags.set(tags)

        if commit:
            sync_tags()
        else:
            self.save_m2m = sync_tags
        return article


class ArticleCommentForm(forms.ModelForm):
    class Meta:
        model = ArticleComment
        fields = ["body"]
        labels = {"body": ""}
        widgets = {
            "body": forms.Textarea(attrs={"rows": 3, "placeholder": "Escribe un comentario…"}),
        }
