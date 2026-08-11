// Arrastrar y soltar filas en el listado del admin para reordenar (ver
// SortableAdminMixin en apps/core/admin.py) — usa las casillas de
// selección de acciones en bloque (siempre tienen el pk como value) para
// saber qué fila es cuál, así no depende de qué columna sea el enlace.
document.addEventListener("DOMContentLoaded", function () {
    var tbody = document.querySelector("#result_list tbody");
    if (!tbody || typeof Sortable === "undefined") return;

    var reorderUrl = window.location.pathname.replace(/\/(\?.*)?$/, "") + "/reordenar/";

    function getCsrfToken() {
        var match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
        return match ? match[1] : "";
    }

    Sortable.create(tbody, {
        handle: ".drag-handle",
        animation: 150,
        onEnd: function () {
            var ids = Array.from(tbody.querySelectorAll("tr")).map(function (row) {
                var checkbox = row.querySelector('input[name="_selected_action"]');
                return checkbox ? parseInt(checkbox.value, 10) : null;
            }).filter(function (id) { return id !== null; });

            fetch(reorderUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCsrfToken(),
                },
                body: JSON.stringify({ order: ids }),
            }).then(function (response) {
                if (!response.ok) window.location.reload();
            });
        },
    });
});
