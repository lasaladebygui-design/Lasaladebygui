from django.db import migrations

THEME = {
    "name": "Blanco y Negro",
    "slug": "blanco-y-negro",
    "description": "Escala de grises pura, sin color — como el cine clásico en blanco y negro.",
    "is_dark": True,
    "color_bg": "#0E0E0E",
    "color_surface": "#1C1C1C",
    "color_border": "#3A3A3A",
    "color_text": "#F5F5F5",
    "color_text_muted": "#A0A0A0",
    "color_accent": "#E5E5E5",
    "color_accent_hover": "#FFFFFF",
    "color_on_accent": "#0E0E0E",
    "color_accent_secondary": "#808080",
    "color_accent_secondary_hover": "#A6A6A6",
    "color_on_accent_secondary": "#0E0E0E",
    "color_danger": "#B0413E",
    "color_success": "#4F7942",
    "font_heading": "'Playfair Display', Georgia, serif",
    "font_body": "'Inter', system-ui, -apple-system, sans-serif",
    "space_unit": "0.25rem",
    "radius_base": "0.3rem",
    "max_content_width": "1200px",
}


def seed_theme(apps, schema_editor):
    Theme = apps.get_model("core", "Theme")
    Theme.objects.get_or_create(slug=THEME["slug"], defaults=THEME)


def unseed_theme(apps, schema_editor):
    Theme = apps.get_model("core", "Theme")
    Theme.objects.filter(slug=THEME["slug"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_seed_jinx_theme"),
    ]

    operations = [
        migrations.RunPython(seed_theme, unseed_theme),
    ]
