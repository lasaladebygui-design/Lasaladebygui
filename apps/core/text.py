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
    ilegible, y si no queda nada legible se usa un texto de repuesto.
    Los saltos de línea sí se conservan (solo se colapsan los espacios
    y tabulaciones dentro de cada línea), para no juntar párrafos que
    el usuario haya separado a propósito."""
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    stripped = stripped.replace("—", "-").replace("–", "-").replace("…", "...")
    renderable = "".join(ch for ch in stripped if ch == "\n" or 32 <= ord(ch) < 127)
    lines = [" ".join(line.split()) for line in renderable.split("\n")]
    result = "\n".join(lines).strip("\n")
    return result or fallback


def flow_into_columns(lines, max_columns=4, thresholds=(900, 1800, 2700)):
    """Reparte una lista larga en varias columnas de alto parecido en vez
    de una única tira vertical (que con muchas guardadas/favoritas podía
    salir desproporcionadamente alta) — usado al generar las imágenes de
    "compartir" con Pillow.

    `lines` es una lista de (alto_en_px, se_puede_cortar_justo_antes,
    dato) — a esta función no le importa qué hay en `dato`, cada llamador
    decide qué guardar ahí (texto + qué fuente/color usar al dibujarlo).
    `se_puede_cortar_justo_antes` evita partir un grupo de títulos por la
    mitad: solo se corta columna en un punto marcado como cortable (p.
    ej. el encabezado de cada lista), nunca en mitad de sus títulos.

    Devuelve (columnas, número_de_columnas), donde cada columna es una
    lista de (alto, dato)."""
    total_h = sum(h for h, _, _ in lines)
    num_columns = 1
    for threshold in thresholds:
        if total_h > threshold:
            num_columns += 1
    num_columns = min(num_columns, max_columns) or 1

    target_per_column = -(-total_h // num_columns)  # división hacia arriba
    columns = [[] for _ in range(num_columns)]
    col_idx, col_h = 0, 0
    for h, breakable, data in lines:
        if breakable and col_h >= target_per_column and col_idx < num_columns - 1:
            col_idx += 1
            col_h = 0
        columns[col_idx].append((h, data))
        col_h += h
    return columns, num_columns
