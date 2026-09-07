// Arrastrar y soltar filas en el listado del admin para reordenar (ver
// SortableAdminMixin en apps/core/admin.py) — el pk de cada fila sale
// del atributo data-pk del propio tirador (⠿), no de la casilla de
// selección en bloque: un modelo sin borrado permitido y sin ninguna
// otra acción disponible no pinta esas casillas en absoluto, y
// depender de ellas dejaba el arrastre sin guardar nada.
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
                var handle = row.querySelector(".drag-handle[data-pk]");
                return handle ? parseInt(handle.dataset.pk, 10) : null;
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
