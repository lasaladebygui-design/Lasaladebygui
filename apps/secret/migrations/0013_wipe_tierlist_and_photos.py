from django.db import migrations


def wipe(apps, schema_editor):
    """El tier list y el tablón de fotos pasan de compartidos (entre
    cualquiera con el código de Top Secret) a personales por usuario —
    igual que ya se hizo con el calendario. No hay forma fiable de repartir
    entre usuarios concretos los datos compartidos que hubiera hasta ahora,
    así que se empieza de cero (mismo criterio que con el calendario). Va
    en su propia migración, separada de los cambios de esquema de la
    siguiente, porque Postgres no permite un ALTER TABLE sobre una tabla en
    la misma transacción en la que un DELETE acaba de disparar sus
    triggers de claves foráneas pendientes sobre ella."""
    TierListEntry = apps.get_model("secret", "TierListEntry")
    TierLevel = apps.get_model("secret", "TierLevel")
    SecretPhoto = apps.get_model("secret", "SecretPhoto")
    TierListEntry.objects.all().delete()
    TierLevel.objects.all().delete()
    SecretPhoto.objects.all().delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("secret", "0012_alter_genre_options_alter_secretmovie_genres"),
    ]

    operations = [
        migrations.RunPython(wipe, noop),
    ]
