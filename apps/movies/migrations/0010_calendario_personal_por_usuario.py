import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def borrar_calendario_compartido(apps, schema_editor):
    """El calendario de Top Secret deja de ser compartido (todo el mundo con
    el código veía lo mismo) y pasa a ser personal de cada usuario. Los
    datos que hubiera bajo el modelo antiguo no tienen un dueño claro al que
    asignárselos, así que se empieza de cero en vez de adivinar de quién
    eran — es una función recién añadida esta misma sesión, con poco o
    ningún dato real todavía."""
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
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(borrar_calendario_compartido, noop),
        migrations.RemoveConstraint(model_name="releaseeventgooglelink", name="un_evento_de_google_por_usuario"),
        migrations.DeleteModel(name="ReleaseEventGoogleLink"),
        migrations.AddField(
            model_name="releaseevent",
            name="google_event_id",
            field=models.CharField(blank=True, max_length=255, verbose_name="id del evento en Google Calendar"),
        ),
        migrations.AddField(
            model_name="releaseevent",
            name="user",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="release_events", to=settings.AUTH_USER_MODEL, verbose_name="usuario",
            ),
        ),
        migrations.AlterField(
            model_name="releaseevent",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="release_events", to=settings.AUTH_USER_MODEL, verbose_name="usuario",
            ),
        ),
        migrations.AddField(
            model_name="calendardaynote",
            name="user",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="calendar_day_notes", to=settings.AUTH_USER_MODEL, verbose_name="usuario",
            ),
        ),
        migrations.AlterField(
            model_name="calendardaynote",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="calendar_day_notes", to=settings.AUTH_USER_MODEL, verbose_name="usuario",
            ),
        ),
        migrations.AlterField(
            model_name="calendardaynote",
            name="date",
            field=models.DateField(verbose_name="fecha"),
        ),
        migrations.AddConstraint(
            model_name="calendardaynote",
            constraint=models.UniqueConstraint(fields=("user", "date"), name="un_comentario_por_usuario_y_fecha"),
        ),
        migrations.AlterField(
            model_name="releaseevent",
            name="movie",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name="+",
                to="movies.movie", verbose_name="película/serie",
            ),
        ),
    ]
