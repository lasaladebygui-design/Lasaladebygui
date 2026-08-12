// Arrastrar y soltar en listas del front-end (guardadas, favoritas...),
// hermano del sortable_admin.js del panel: cualquier lista con
// [data-sortable-url] se vuelve arrastrable con SortableJS y manda el
// orden completo por fetch al soltar. Cada fila necesita
// [data-sortable-id] con su pk.
document.addEventListener("DOMContentLoaded", function () {
    if (typeof Sortable === "undefined") return;

    function getCsrfToken() {
        var match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
        return match ? match[1] : "";
    }

    document.querySelectorAll("[data-sortable-url]").forEach(function (list) {
        Sortable.create(list, {
            handle: list.dataset.sortableHandle || undefined,
            animation: 150,
            ghostClass: "sortable-ghost",
            onEnd: function () {
                var ids = Array.from(list.children)
                    .map(function (item) { return parseInt(item.dataset.sortableId, 10); })
                    .filter(function (id) { return !isNaN(id); });

                fetch(list.dataset.sortableUrl, {
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
});
