function csrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
    return match ? match[1] : "";
}

function ensureEmptyPlaceholder(zone) {
    if (zone.querySelector(".tier-item") || zone.querySelector(".tier-row__empty")) return;
    const span = document.createElement("span");
    span.className = "muted tier-row__empty";
    span.textContent = "Sin películas todavía en este nivel.";
    zone.appendChild(span);
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".tier-item").forEach((item) => {
        item.setAttribute("draggable", "true");
        item.addEventListener("dragstart", (event) => {
            event.dataTransfer.setData("text/plain", item.dataset.entryId);
            event.dataTransfer.effectAllowed = "move";
        });
    });

    document.querySelectorAll(".tier-row__items").forEach((zone) => {
        zone.addEventListener("dragover", (event) => {
            event.preventDefault();
            zone.classList.add("tier-row__items--dragover");
        });
        zone.addEventListener("dragleave", () => {
            zone.classList.remove("tier-row__items--dragover");
        });
        zone.addEventListener("drop", (event) => {
            event.preventDefault();
            zone.classList.remove("tier-row__items--dragover");

            const id = event.dataTransfer.getData("text/plain");
            const item = document.querySelector(`.tier-item[data-entry-id="${id}"]`);
            if (!item) return;
            const sourceZone = item.parentElement;
            if (sourceZone === zone) return;

            fetch(`/top-secret/dentro/tierlist/${id}/mover/`, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken(),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body: `tier=${encodeURIComponent(zone.dataset.tier)}`,
            }).then((response) => {
                if (!response.ok) return;
                const empty = zone.querySelector(".tier-row__empty");
                if (empty) empty.remove();
                zone.appendChild(item);
                ensureEmptyPlaceholder(sourceZone);
            });
        });
    });
});
