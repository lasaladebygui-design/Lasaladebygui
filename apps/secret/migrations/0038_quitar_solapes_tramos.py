from django.db import migrations

from apps.secret.models import ajustar_solapes


def quitar_solapes(apps, schema_editor):
    """Antes de quitar `order` (ver 0039), deja sin solapes los tramos ya
    guardados sin cambiar el color de ninguna nota: hasta ahora, en un
    solape ganaba el de menor `order`, así que ese es el que se respeta y
    los demás se recortan hasta su borde (o se borran si estaban tapados
    enteros). Va en una migración aparte: en Postgres no se puede alterar
    la tabla en la misma transacción en que se han tocado sus filas
    ("pending trigger events")."""
    RatingColorBand = apps.get_model('secret', 'RatingColorBand')
    guias = RatingColorBand.objects.values_list('config_id', flat=True).distinct()
    for config_id in guias:
        tramos = list(RatingColorBand.objects.filter(config_id=config_id).order_by('order', 'min_rating', 'pk'))
        vivos, descartados = ajustar_solapes(tramos, prioridad=tramos)
        for b in descartados:
            b.delete()
        for b in vivos:
            b.save(update_fields=['min_rating', 'max_rating'])


class Migration(migrations.Migration):

    dependencies = [
        ('secret', '0037_listfilterpreference'),
    ]

    operations = [
        migrations.RunPython(quitar_solapes, migrations.RunPython.noop),
    ]
