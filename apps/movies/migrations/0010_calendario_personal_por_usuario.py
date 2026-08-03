from django.db import migrations


def borrar_calendario_compartido(apps, schema_editor):
    """El calendario de Top Secret deja de ser compartido (todo el mundo con
    el código veía lo mismo) y pasa a ser personal de cada usuario. Los
    datos que hubiera bajo el modelo antiguo no tienen un dueño claro al que
    asignárselos, así que se empieza de cero en vez de adivinar de quién
    eran — es una función recién añadida esta misma sesión, con poco o
    ningún dato real todavía.

    Va en su propia migración (en vez de junto con los cambios de esquema
    de la siguiente) porque Postgres no deja hacer ALTER TABLE sobre una
    tabla en la misma transacción en la que un DELETE acaba de disparar
    triggers de claves foráneas pendientes sobre ella."""
    ReleaseEvent = apps.get_model("movies", "ReleaseEvent")
    ReleaseEventGoogleLink = apps.get_model("movies", "ReleaseEventGoogleLink")
    CalendarDayNote = apps.get_model("movies", "CalendarDayNote")
    ReleaseEventGoogleLink.objects.all().delete()
    ReleaseEvent.objects.all().delete()
    CalendarDayNote.objects.all().delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("movies", "0009_savedmovielist_savedmovie_sublist_and_more"),
    ]

    operations = [
        migrations.RunPython(borrar_calendario_compartido, noop),
    ]
