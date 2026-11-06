// Tramos de color de la guía (templates/secret/_rating_guide_panel.html):
// al cambiar una nota, el tramo que se acaba de tocar se respeta y los que
// chocan con él se recortan hasta su borde (o se marcan para borrar si
// quedan tapados enteros); después las filas se reordenan de mayor a menor.
// Es la misma regla que ajustar_solapes en apps/secret/models.py, que la
// vuelve a aplicar al guardar. Todo en décimas para no arrastrar errores de
// coma flotante. Delegado en document porque el panel llega por HTMX.
(function () {
    "use strict";

    function decimas(input) {
        var v = parseFloat(String(input.value).replace(",", "."));
        return isNaN(v) ? null : Math.max(0, Math.min(100, Math.round(v * 10)));
    }
    function texto(d) { return (d / 10).toFixed(1); }
    function bonito(d) { return texto(d).replace(".", ","); }

    function leerTramos(panel) {
        var tramos = [];
        panel.querySelectorAll(".rating-bands__row").forEach(function (row) {
            var lo = row.querySelector(".rating-band__min"), hi = row.querySelector(".rating-band__max");
            var borrar = row.querySelector("input[name$='-DELETE']");
            if (!lo || !hi || (borrar && borrar.checked)) return;
            var min = decimas(lo), max = decimas(hi);
            if (min === null || max === null) return;
            tramos.push({ row: row, lo: lo, hi: hi, borrar: borrar, min: min, max: max });
        });
        return tramos;
    }

    function avisar(row, mensaje) {
        var nota = row.querySelector(".rating-bands__nota");
        if (nota) nota.textContent = mensaje;
        row.classList.remove("rating-bands__row--ajustada");
        void row.offsetWidth; // reinicia la animación si ya estaba
        row.classList.add("rating-bands__row--ajustada");
    }

    function ajustar(panel, editada) {
        var tramos = leerTramos(panel);
        var e = tramos.filter(function (t) { return t.row === editada; })[0];
        if (e) {
            if (e.min > e.max) { var t = e.min; e.min = e.max; e.max = t; }
            e.lo.value = texto(e.min);
            e.hi.value = texto(e.max);
            tramos.forEach(function (b) {
                if (b === e || b.max < e.min || b.min > e.max) return;
                var antes = bonito(b.min) + "–" + bonito(b.max);
                if (b.min >= e.min && b.max <= e.max) {
                    if (b.borrar) {
                        b.borrar.checked = true;
                    } else {
                        b.lo.value = ""; b.hi.value = "";
                    }
                    avisar(b.row, "Se borrará al guardar: quedaba tapado entero (" + antes + ").");
                    return;
                }
                if (b.min < e.min && b.max > e.max) {
                    if (e.min - b.min >= b.max - e.max) b.max = e.min - 1; else b.min = e.max + 1;
                } else if (b.min < e.min) {
                    b.max = e.min - 1;
                } else {
                    b.min = e.max + 1;
                }
                b.lo.value = texto(b.min);
                b.hi.value = texto(b.max);
                avisar(b.row, "Ajustado: era " + antes + ".");
            });
        }
        ordenar(panel);
    }

    // De mayor a menor; la fila en blanco para añadir siempre al final.
    function ordenar(panel) {
        var cont = panel.querySelector(".rating-bands__rows");
        if (!cont) return;
        var filas = Array.prototype.slice.call(cont.querySelectorAll(".rating-bands__row"));
        filas.sort(function (a, b) {
            var va = decimas(a.querySelector(".rating-band__min")), vb = decimas(b.querySelector(".rating-band__min"));
            if (va === null) return 1;
            if (vb === null) return -1;
            return vb - va;
        });
        filas.forEach(function (f) { cont.appendChild(f); });
    }

    document.addEventListener("change", function (ev) {
        var input = ev.target;
        if (!input.classList || !(input.classList.contains("rating-band__min") || input.classList.contains("rating-band__max"))) return;
        var panel = input.closest(".rating-bands");
        var row = input.closest(".rating-bands__row");
        if (!panel || !row) return;
        var nota = row.querySelector(".rating-bands__nota");
        if (nota) nota.textContent = "";
        // Hasta que la fila tiene las dos notas no se puede comparar con nada.
        if (decimas(row.querySelector(".rating-band__min")) === null || decimas(row.querySelector(".rating-band__max")) === null) return;
        ajustar(panel, row);
    });
})();
