from django import forms
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from apps.core.admin import SingletonAdmin, SortableAdminMixin
from apps.movies.models import Movie

from .forms import SecretMovieForm
from .models import (
    CalendarDayNote,
    CalendarShareMember,
    Genre,
    PhotoBoardMember,
    RatingColorBand,
    ReleaseEvent,
    SecretListMember,
    SecretMovie,
    SecretPhoto,
    TierLevel,
    TierListEntry,
    TopSecretConfig,
    TopSecretTab,
)


class TopSecretConfigForm(forms.ModelForm):
    new_code = forms.CharField(
        label="Nuevo código de acceso",
        required=False,
        help_text=(
            "El código actual está hasheado y no se puede consultar. "
            "Déjalo vacío para no cambiarlo."
        ),
    )

    class Meta:
        model = TopSecretConfig
        fields = ["rating_guide", "allow_web_editing"]
        widgets = {"rating_guide": forms.Textarea(attrs={"rows": 10})}

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_code = self.cleaned_data.get("new_code")
        if new_code:
            instance.set_code(new_code)
        if commit:
            instance.save()
        return instance


class RatingColorBandInline(admin.TabularInline):
    """Tantos tramos de nota→color como se quiera (no solo "bueno/medio/
    malo" fijo) — p. ej. "1 a 4: rojo", "4.1 a 7: naranja", "7.1 a 10: verde",
    o cualquier otro reparto. El primer tramo cuyo rango incluya la nota es
    el que se usa (ver TopSecretConfig.rating_color)."""

    model = RatingColorBand
    extra = 1
    fields = ("min_rating", "max_rating", "color", "order")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "color":
            kwargs["widget"] = forms.TextInput(attrs={"type": "color"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(TopSecretConfig)
class TopSecretConfigAdmin(SingletonAdmin):
    form = TopSecretConfigForm
    inlines = [RatingColorBandInline]
    fieldsets = (
        (None, {"fields": ("new_code",)}),
        ("Guía para entender la lista", {
            "fields": ("rating_guide",),
            "description": "Se enseña colapsada, en un desplegable con un icono ℹ️, en Top Secret → Lista completa.",
        }),
        ("Edición desde la web", {
            "fields": ("allow_web_editing",),
            "description": "Interruptor temporal: con esto activo, la nota, el desempate y las listas de cada película se pueden editar directamente en Lista completa, sin pasar por aquí.",
        }),
    )


@admin.register(TopSecretTab)
class TopSecretTabAdmin(SortableAdminMixin, admin.ModelAdmin):
    """Arrastra las filas para decidir en qué orden salen las pestañas de
    arriba del maletín (Lista, Calendario, Tablón...) -- para todo el
    mundo por igual, ver templates/secret/_shell.html. Es un conjunto
    fijo: no se puede añadir ni borrar desde aquí, solo reordenar."""

    list_display = ("__str__",)
    list_display_links = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Genre)
class GenreAdmin(SortableAdminMixin, admin.ModelAdmin):
    # Se ve TODO -- la de Bygui (owner vacío) y la de cada usuario -- para
    # que el Admin pueda moderar cualquier lista propia si hace falta
    # (borrar algo inapropiado, etc.), aunque el alta normal de las
    # propias se siga haciendo desde la web (Top Secret → tu lista).
    list_display = ("name", "owner", "admin_only")
    list_display_links = ("name",)
    list_editable = ("admin_only",)
    list_filter = ("admin_only", "owner")
    exclude = ("slug", "order")
    search_fields = ("name", "owner__username")
    autocomplete_fields = ("owner",)


@admin.register(SecretMovie)
class SecretMovieAdmin(admin.ModelAdmin):
    # Se ve TODO -- la lista de Bygui (owner vacío) y la propia de cada
    # usuario -- para poder moderar cualquiera desde aquí si hace falta,
    # aunque el alta normal de las propias se siga haciendo desde la web.
    form = SecretMovieForm
    list_display = ("number", "title", "owner", "personal_rating", "tie_break", "genre_list", "admin_only")
    # Por defecto Django solo deja clicable la primera columna (number) —
    # aquí cualquiera de las columnas visibles lleva a la ficha de edición.
    # `owner` NO está aquí para poder tenerlo en list_editable (Django no
    # permite que una columna sea link Y editable a la vez) -- así se
    # puede reasignar de quién es una entrada directamente desde el
    # listado, sin abrir cada una, con el mismo desplegable de siempre.
    list_display_links = ("number", "title", "personal_rating", "tie_break", "genre_list")
    list_editable = ("admin_only", "owner")
    # RelatedOnlyFieldListFilter: solo enseña en el filtro a quien de
    # verdad tiene alguna entrada, en vez de listar a todos los usuarios
    # del sitio tengan o no película alguna -- mucho más corto y directo
    # para encontrar la lista de alguien en concreto.
    list_filter = ("admin_only", ("owner", admin.RelatedOnlyFieldListFilter))
    search_fields = ("title", "owner__username")
    autocomplete_fields = ("movie", "owner")
    ordering = ("owner", "number")

    def save_model(self, request, obj, form, change):
        if not change:
            # Solo al crear una nueva desde aquí: por defecto es de Bygui,
            # igual que siempre (crear a nombre de otro usuario se hace
            # desde su propia lista en la web, no desde aquí).
            obj.owner = None
        super().save_model(request, obj, form, change)
        # Igual que al enlazar portada desde la web (movie_poster_set): si
        # acabas de catalogar la película aquí, ya no hace falta que siga
        # en tus propias Guardadas de "quiero verla".
        if obj.movie_id:
            from apps.movies.models import SavedMovie
            SavedMovie.objects.filter(user=request.user, movie_id=obj.movie_id).delete()

    class Media:
        js = ("js/admin_secret_movie_watch_status.js",)

    @admin.display(description="listas")
    def genre_list(self, obj):
        return ", ".join(obj.genres.values_list("name", flat=True))

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path(
                "movie-is-tv/<int:movie_id>/",
                self.admin_site.admin_view(self.movie_is_tv_view),
                name="%s_%s_movie_is_tv" % info,
            ),
        ]
        return custom + super().get_urls()

    def movie_is_tv_view(self, request, movie_id):
        # El campo "series_watch_status" siempre está en el formulario (ver
        # forms.SecretMovieForm) para poder mostrarlo/ocultarlo al vuelo
        # según la portada elegida — static/js/admin_secret_movie_watch_status.js
        # llama aquí cada vez que cambia el campo "movie" (select2), en vez
        # de esperar a guardar y volver a abrir la entrada.
        is_tv = Movie.objects.filter(pk=movie_id, media_type=Movie.MediaType.TV).exists()
        return JsonResponse({"is_tv": is_tv})


@admin.register(SecretPhoto)
class SecretPhotoAdmin(admin.ModelAdmin):
    list_display = ("description", "board_owner", "uploaded_by", "created_at")
    list_filter = ("board_owner",)
    search_fields = ("description", "board_owner__username", "uploaded_by__username")
    autocomplete_fields = ("board_owner", "uploaded_by")


@admin.register(PhotoBoardMember)
class PhotoBoardMemberAdmin(admin.ModelAdmin):
    list_display = ("owner", "member", "invited_at")
    search_fields = ("owner__username", "member__username")
    autocomplete_fields = ("owner", "member")


@admin.register(SecretListMember)
class SecretListMemberAdmin(admin.ModelAdmin):
    # Gestión normal: desde la propia web (Top Secret → tu lista →
    # compartir). Esto es solo para verlo/depurarlo desde el admin.
    list_display = ("owner", "member", "invited_at")
    search_fields = ("owner__username", "member__username")
    autocomplete_fields = ("owner", "member")


@admin.register(CalendarShareMember)
class CalendarShareMemberAdmin(admin.ModelAdmin):
    # Gestión normal: desde la propia web (Top Secret → calendario →
    # compartir). Esto es solo para verlo/depurarlo desde el admin.
    list_display = ("owner", "member", "invited_at")
    search_fields = ("owner__username", "member__username")
    autocomplete_fields = ("owner", "member")


@admin.register(TierLevel)
class TierLevelAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "color", "order")
    list_editable = ("color", "order")
    list_filter = ("user",)
    ordering = ("user_id", "order")


@admin.register(TierListEntry)
class TierListEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "tier", "order")
    list_display_links = ("title",)
    list_editable = ("tier", "order")
    list_filter = ("user", "tier")
    search_fields = ("title",)
    autocomplete_fields = ("movie",)
    ordering = ("user_id", "tier__order", "order")


@admin.register(ReleaseEvent)
class ReleaseEventAdmin(admin.ModelAdmin):
    list_display = ("user", "movie", "date", "note")
    list_filter = ("date",)
    search_fields = ("movie__title", "user__username")
    autocomplete_fields = ("movie",)
    ordering = ("date",)


@admin.register(CalendarDayNote)
class CalendarDayNoteAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "note")
    search_fields = ("user__username",)
    ordering = ("date",)
