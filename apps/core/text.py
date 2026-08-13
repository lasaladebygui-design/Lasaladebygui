"""Utilidades de texto compartidas entre apps — pensadas sobre todo para
dibujar imágenes con Pillow, que no tiene el mismo soporte de caracteres
que el resto del sitio."""

import unicodedata


def ascii_safe(text, fallback="(titulo no compatible)"):
    """La fuente por defecto de Pillow solo tiene glifos latinos/ASCII —
    se usa solo para dibujar imágenes (el resto del sitio sigue
    mostrando el texto tal cual, con tildes, japonés, etc.). Primero
    quita acentos/ñ; lo que siga sin ser ASCII (japonés, coreano,
    árabe...) directamente se descarta en vez de salir como un cuadro
    ilegible, y si no queda nada legible se usa un texto de repuesto."""
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    stripped = stripped.replace("—", "-").replace("–", "-").replace("…", "...")
    renderable = "".join(ch for ch in stripped if 32 <= ord(ch) < 127)
    renderable = " ".join(renderable.split())
    return renderable or fallback
