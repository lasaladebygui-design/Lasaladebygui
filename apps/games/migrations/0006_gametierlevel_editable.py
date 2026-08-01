import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

DEFAULT_LEVELS = [
    ("S", "#FFD700"),
    ("A", "#FFA94D"),
    ("B", "#A9E34B"),
    ("C", "#74C0FC"),
    ("D", "#D98C8C"),
]


def seed_levels_and_migrate_entries(apps, schema_editor):
    """Los niveles S/A/B/C/D dejan de ser fijos y pasan a ser editables por
    usuario (como en Top Secret): cada usuario que ya tuviera entradas se
    lleva su propio juego de niveles S/A/B/C/D (mismo nombre/color de
    siempre) y sus entradas se re-enlazan a ellos por nombre. 'U' (sin
    clasificar) pasa a `tier=None`, igual que en Top Secret."""
    GameTierEntry = apps.get_model("games", "GameTierEntry")
    GameTierLevel = apps.get_model("games", "GameTierLevel")

    user_ids = GameTierEntry.objects.values_list("user_id", flat=True).distinct()
    for user_id in user_ids:
        levels_by_name = {}
        for order, (name, color) in enumerate(DEFAULT_LEVELS):
            levels_by_name[name] = GameTierLevel.objects.create(
                user_id=user_id, name=name, color=color, order=order,
            )
        for entry in GameTierEntry.objects.filter(user_id=user_id):
            level = levels_by_name.get(entry.tier)
            if level is not None:
                entry.new_tier = level
                entry.save(update_fields=["new_tier"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0005_gametierentry"),
    ]

    operations = [
        migrations.CreateModel(
            name="GameTierLevel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=30, verbose_name="nombre")),
                ("color", models.CharField(default="#2DD4BF", max_length=7, verbose_name="color")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="orden")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="game_tier_levels", to=settings.AUTH_USER_MODEL, verbose_name="usuario")),
            ],
            options={
                "verbose_name": "tier list de Juegos: nivel",
                "verbose_name_plural": "tier list de Juegos: niveles",
                "ordering": ["user_id", "order", "pk"],
            },
        ),
        migrations.AddField(
            model_name="gametierentry",
            name="new_tier",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="entries", to="games.gametierlevel", verbose_name="nivel",
            ),
        ),
        migrations.RunPython(seed_levels_and_migrate_entries, noop),
        migrations.RemoveField(model_name="gametierentry", name="tier"),
        migrations.RenameField(model_name="gametierentry", old_name="new_tier", new_name="tier"),
        migrations.AlterModelOptions(
            name="gametierentry",
            options={
                "ordering": ["tier__order", "order", "movie__title"],
                "verbose_name": "tier list de Juegos: entrada",
                "verbose_name_plural": "tier list de Juegos: entradas",
            },
        ),
    ]
