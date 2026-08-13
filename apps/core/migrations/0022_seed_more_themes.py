from django.db import migrations

THEMES = [
    {
        "name": "Estudio",
        "slug": "estudio",
        "description": "Blanco casi puro con rojo de claqueta como acento y azul marino de secundario — limpio y editorial, como una sala de proyección moderna.",
        "is_dark": False,
        "color_bg": "#FAFAF8",
        "color_surface": "#FFFFFF",
        "color_border": "#E3E1DA",
        "color_text": "#1A1A1A",
        "color_text_muted": "#6B6B63",
        "color_accent": "#D62828",
        "color_accent_hover": "#E85A5A",
        "color_on_accent": "#FAFAF8",
        "color_accent_secondary": "#1D3557",
        "color_accent_secondary_hover": "#3A5A85",
        "color_on_accent_secondary": "#FAFAF8",
        "color_danger": "#C1121F",
        "color_success": "#2A9D5C",
        "font_heading": "'Playfair Display', Georgia, serif",
        "font_body": "'Inter', system-ui, -apple-system, sans-serif",
        "space_unit": "0.25rem",
        "radius_base": "0.5rem",
        "max_content_width": "1200px",
    },
    {
        "name": "Technicolor",
        "slug": "technicolor",
        "description": "Crema cálido con rojo y cian muy saturados — homenaje al color a lo bruto del cine clásico.",
        "is_dark": False,
        "color_bg": "#FFF8E7",
        "color_surface": "#FFFFFF",
        "color_border": "#F0DDA6",
        "color_text": "#2B1B12",
        "color_text_muted": "#8A7256",
        "color_accent": "#E63946",
        "color_accent_hover": "#FF6B75",
        "color_on_accent": "#FFF8E7",
        "color_accent_secondary": "#1D8A99",
        "color_accent_secondary_hover": "#4FB8C7",
        "color_on_accent_secondary": "#08262A",
        "color_danger": "#C1121F",
        "color_success": "#2A9D5C",
        "font_heading": "'Abril Fatface', Georgia, serif",
        "font_body": "'Inter', system-ui, -apple-system, sans-serif",
        "space_unit": "0.25rem",
        "radius_base": "0.6rem",
        "max_content_width": "1200px",
    },
    {
        "name": "Pastel Menta",
        "slug": "pastel-menta",
        "description": "Menta muy pálido con lavanda y rosa pastel — suave y actual, sin renunciar al contraste.",
        "is_dark": False,
        "color_bg": "#F1F5F0",
        "color_surface": "#FBFDFA",
        "color_border": "#DCE8DA",
        "color_text": "#33403A",
        "color_text_muted": "#7C8C83",
        "color_accent": "#8B6FE0",
        "color_accent_hover": "#A78BFA",
        "color_on_accent": "#241542",
        "color_accent_secondary": "#E0759C",
        "color_accent_secondary_hover": "#F6A6C1",
        "color_on_accent_secondary": "#4A1526",
        "color_danger": "#D2415F",
        "color_success": "#5AA57C",
        "font_heading": "'Cormorant Garamond', Georgia, serif",
        "font_body": "'Inter', system-ui, -apple-system, sans-serif",
        "space_unit": "0.25rem",
        "radius_base": "0.8rem",
        "max_content_width": "1200px",
    },
    {
        "name": "Desierto",
        "slug": "desierto",
        "description": "Arena y terracota con teal del desierto de contraste — western, cálido y polvoriento.",
        "is_dark": False,
        "color_bg": "#F3E5D3",
        "color_surface": "#FBF3E7",
        "color_border": "#E0C29B",
        "color_text": "#4A2E1E",
        "color_text_muted": "#8F6B4E",
        "color_accent": "#BF5B2E",
        "color_accent_hover": "#D97B4F",
        "color_on_accent": "#FBF3E7",
        "color_accent_secondary": "#2E6E62",
        "color_accent_secondary_hover": "#4F8F82",
        "color_on_accent_secondary": "#FBF3E7",
        "color_danger": "#A6321D",
        "color_success": "#3D7A52",
        "font_heading": "'Cinzel', Georgia, serif",
        "font_body": "'Inter', system-ui, -apple-system, sans-serif",
        "space_unit": "0.25rem",
        "radius_base": "0.4rem",
        "max_content_width": "1200px",
    },
    {
        "name": "Medianoche Azul",
        "slug": "medianoche-azul",
        "description": "Añil profundo con azul hielo y dorado de estreno — la noche de una première, no la del cine negro.",
        "is_dark": True,
        "color_bg": "#060B18",
        "color_surface": "#0E1830",
        "color_border": "#1E2E52",
        "color_text": "#E6ECFF",
        "color_text_muted": "#8A97C4",
        "color_accent": "#6EA8FE",
        "color_accent_hover": "#A9C9FF",
        "color_on_accent": "#060B18",
        "color_accent_secondary": "#D4AF37",
        "color_accent_secondary_hover": "#E9CD70",
        "color_on_accent_secondary": "#241B02",
        "color_danger": "#FF5C6C",
        "color_success": "#4ADE80",
        "font_heading": "'Cinzel', Georgia, serif",
        "font_body": "'Inter', system-ui, -apple-system, sans-serif",
        "space_unit": "0.25rem",
        "radius_base": "0.5rem",
        "max_content_width": "1200px",
    },
]


def seed_more_themes(apps, schema_editor):
    Theme = apps.get_model("core", "Theme")
    for order, data in enumerate(THEMES, start=10):
        Theme.objects.get_or_create(slug=data["slug"], defaults={**data, "order": order})


def unseed_more_themes(apps, schema_editor):
    Theme = apps.get_model("core", "Theme")
    Theme.objects.filter(slug__in=[t["slug"] for t in THEMES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_adminmenuorder"),
    ]

    operations = [
        migrations.RunPython(seed_more_themes, unseed_more_themes),
    ]
