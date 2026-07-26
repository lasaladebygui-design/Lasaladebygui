from django.db import migrations

THEMES = [
    {
        "name": "Cinephile",
        "slug": "cinephile",
        "description": "Teal + ámbar sobre fondo oscuro. Tema por defecto.",
        "is_dark": True,
        "color_bg": "#0B1416",
        "color_surface": "#122120",
        "color_border": "#1F2E2D",
        "color_text": "#E5E7EB",
        "color_text_muted": "#9CA3AF",
        "color_accent": "#2DD4BF",
        "color_accent_hover": "#5EEAD4",
        "color_on_accent": "#0B1416",
        "color_accent_secondary": "#FFB347",
        "color_accent_secondary_hover": "#FFDFAF",
        "color_on_accent_secondary": "#241505",
        "color_danger": "#EF4444",
        "color_success": "#22C55E",
        "font_heading": "'Playfair Display', Georgia, serif",
        "font_body": "'Inter', system-ui, -apple-system, sans-serif",
        "space_unit": "0.25rem",
        "radius_base": "0.6rem",
        "max_content_width": "1200px",
    },
    {
        "name": "Noir",
        "slug": "noir",
        "description": "Negro/gris carbón con rojo sangre como acento. Alto contraste, cine negro.",
        "is_dark": True,
        "color_bg": "#0A0A0A",
        "color_surface": "#161616",
        "color_border": "#2E2E2E",
        "color_text": "#F2F2F2",
        "color_text_muted": "#A3A3A3",
        "color_accent": "#8B0000",
        "color_accent_hover": "#B22222",
        "color_on_accent": "#F2F2F2",
        "color_accent_secondary": "#E5E5E5",
        "color_accent_secondary_hover": "#FFFFFF",
        "color_on_accent_secondary": "#0A0A0A",
        "color_danger": "#FF3B3B",
        "color_success": "#4ADE80",
        "font_heading": "'Bebas Neue', Impact, sans-serif",
        "font_body": "'Inter', system-ui, -apple-system, sans-serif",
        "space_unit": "0.25rem",
        "radius_base": "0.3rem",
        "max_content_width": "1200px",
    },
    {
        "name": "Vintage",
        "slug": "vintage",
        "description": "Verde menta/salvia pastel con acentos crema y marrón. Suave y retro.",
        "is_dark": False,
        "color_bg": "#E8EFE1",
        "color_surface": "#F5F1E6",
        "color_border": "#D8CBB0",
        "color_text": "#4A3F2F",
        "color_text_muted": "#8A7A63",
        "color_accent": "#8C5A3B",
        "color_accent_hover": "#A9744F",
        "color_on_accent": "#FDF8F0",
        "color_accent_secondary": "#D9A441",
        "color_accent_secondary_hover": "#E8BE6C",
        "color_on_accent_secondary": "#3A2C1A",
        "color_danger": "#B23A2E",
        "color_success": "#5B7B4F",
        "font_heading": "'Special Elite', 'Playfair Display', Georgia, serif",
        "font_body": "'Inter', system-ui, -apple-system, sans-serif",
        "space_unit": "0.25rem",
        "radius_base": "0.5rem",
        "max_content_width": "1200px",
    },
]


def seed_themes(apps, schema_editor):
    Theme = apps.get_model("core", "Theme")
    SiteConfig = apps.get_model("core", "SiteConfig")

    for data in THEMES:
        Theme.objects.get_or_create(slug=data["slug"], defaults=data)

    cinephile = Theme.objects.filter(slug="cinephile").first()
    config, _ = SiteConfig.objects.get_or_create(pk=1)
    if config.active_theme_id is None:
        config.active_theme = cinephile
        config.save(update_fields=["active_theme"])


def unseed_themes(apps, schema_editor):
    Theme = apps.get_model("core", "Theme")
    Theme.objects.filter(slug__in=[t["slug"] for t in THEMES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_themes, unseed_themes),
    ]
