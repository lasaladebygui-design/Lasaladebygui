// Vista previa en vivo de un tema (admin → Temas visuales): el iframe carga
// una página de muestra aparte (para que los estilos de main.css no choquen
// con los del propio admin) y este script va empujando cada cambio de campo
// como una variable CSS dentro de ese iframe — sin necesidad de guardar
// para ver el resultado.
document.addEventListener("DOMContentLoaded", function () {
    var iframe = document.getElementById("theme-preview-frame");
    if (!iframe) return;

    var FIELD_TO_VAR = {
        id_color_bg: "--color-bg",
        id_color_surface: "--color-surface",
        id_color_border: "--color-border",
        id_color_text: "--color-text",
        id_color_text_muted: "--color-text-muted",
        id_color_accent: "--color-accent",
        id_color_accent_hover: "--color-accent-hover",
        id_color_on_accent: "--color-on-accent",
        id_color_accent_secondary: "--color-accent-secondary",
        id_color_accent_secondary_hover: "--color-accent-secondary-hover",
        id_color_on_accent_secondary: "--color-on-accent-secondary",
        id_color_danger: "--color-danger",
        id_color_success: "--color-success",
        id_font_heading: "--font-heading",
        id_font_body: "--font-body",
        id_space_unit: "--space-unit",
        id_radius_base: "--radius-base",
        id_max_content_width: "--max-content-width",
    };

    function applyField(fieldId) {
        var el = document.getElementById(fieldId);
        var doc = iframe.contentDocument;
        if (!el || !doc || !el.value) return;
        doc.documentElement.style.setProperty(FIELD_TO_VAR[fieldId], el.value);
    }

    function applyAll() {
        Object.keys(FIELD_TO_VAR).forEach(applyField);
    }

    Object.keys(FIELD_TO_VAR).forEach(function (fieldId) {
        var el = document.getElementById(fieldId);
        if (!el) return;
        el.addEventListener("input", function () { applyField(fieldId); });
    });

    iframe.addEventListener("load", applyAll);
});
