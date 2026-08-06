from django.db import migrations

THEME = {
    "name": "Jinx",
    "slug": "jinx",
    "description": "Azul neón, rosa y morado — inspirado en Jinx (Arcane). Zaun después de medianoche.",
    "is_dark": True,
    "color_bg": "#0B0714",
    "color_surface": "#1A0F2E",
    "color_border": "#3D2465",
    "color_text": "#F0E9FF",
    "color_text_muted": "#B39DDB",
    "color_accent": "#00E5FF",
    "color_accent_hover": "#7DF9FF",
    "color_on_accent": "#0B0714",
    "color_accent_secondary": "#FF2FD0",
    "color_accent_secondary_hover": "#FF8EE8",
    "color_on_accent_secondary": "#0B0714",
    "color_danger": "#FF3860",
    "color_success": "#39FF88",
    "font_heading": "'Bebas Neue', Impact, sans-serif",
    "font_body": "'Inter', system-ui, -apple-system, sans-serif",
    "space_unit": "0.25rem",
    "radius_base": "0.4rem",
    "max_content_width": "1200px",
}


def seed_jinx_theme(apps, schema_editor):
    Theme = apps.get_model("core", "Theme")
    Theme.objects.get_or_create(slug=THEME["slug"], defaults=THEME)


def unseed_jinx_theme(apps, schema_editor):
    Theme = apps.get_model("core", "Theme")
    Theme.objects.filter(slug=THEME["slug"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_theme_is_published"),
    ]

    operations = [
        migrations.RunPython(seed_jinx_theme, unseed_jinx_theme),
    ]
