import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _copy_existing_guide_to_lasaladebygui(apps, schema_editor):
    """La guía y los tramos de color vivían en el TopSecretConfig único
    de todo el sitio -- en la práctica, eran los de lasaladebygui. Se
    trasladan tal cual a su RatingGuide propia (nueva), para no perder lo
    que ya hubiera configurado. Si esta base de datos no tiene todavía
    una cuenta "lasaladebygui" (instalación nueva/de pruebas) no hay nada
    que trasladar, y no pasa nada: cada cuenta se crea su RatingGuide
    vacía sola la primera vez que hace falta (ver RatingGuide.for_user)."""
    User = apps.get_model("accounts", "User")
    TopSecretConfig = apps.get_model("secret", "TopSecretConfig")
    RatingGuide = apps.get_model("secret", "RatingGuide")
    RatingColorBand = apps.get_model("secret", "RatingColorBand")

    bygui = User.objects.filter(username="lasaladebygui").first()
    if bygui is None:
        return

    config = TopSecretConfig.objects.first()
    guide = RatingGuide.objects.create(
        user=bygui, rating_guide=config.rating_guide if config else "",
    )
    RatingColorBand.objects.update(new_config=guide)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("secret", "0033_alter_genre_admin_only_alter_genre_owner_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RatingGuide",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "rating_guide",
                    models.TextField(
                        blank=True,
                        help_text="Explica tu criterio a la hora de puntuar (qué hunde una nota, qué la infla...). Se enseña colapsada, en un desplegable, en la lista completa.",
                        verbose_name="guía para entender la lista",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rating_guide_config",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="cuenta",
                    ),
                ),
            ],
            options={
                "verbose_name": "guía y colores de mi lista",
                "verbose_name_plural": "guía y colores de mi lista",
            },
        ),
        # Campo puente temporal: se rellena con datos antes de retirar el
        # antiguo `config` (a TopSecretConfig) y quedarse solo con este,
        # ya apuntando a RatingGuide -- así ningún RatingColorBand
        # existente se queda huérfano ni apuntando al pk equivocado.
        migrations.AddField(
            model_name="ratingcolorband",
            name="new_config",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="rating_bands", to="secret.ratingguide",
            ),
        ),
        migrations.RunPython(_copy_existing_guide_to_lasaladebygui, _noop_reverse),
        migrations.RemoveField(model_name="ratingcolorband", name="config"),
        migrations.RenameField(model_name="ratingcolorband", old_name="new_config", new_name="config"),
        migrations.AlterField(
            model_name="ratingcolorband",
            name="config",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="rating_bands", to="secret.ratingguide",
            ),
        ),
        migrations.RemoveField(model_name="topsecretconfig", name="rating_guide"),
        migrations.AlterModelOptions(
            name="topsecretconfig",
            options={"verbose_name": "código de acceso al maletín", "verbose_name_plural": "código de acceso al maletín"},
        ),
    ]
