function notifBell() {
    return {
        open: false,
        loaded: false,
        html: "",

        toggle() {
            this.open = !this.open;
            if (this.open && !this.loaded) this.load();
        },

        load() {
            fetch("/avisos/")
                .then((r) => r.text())
                .then((text) => {
                    this.html = text;
                    this.loaded = true;
                    // Abrir el panel ya marca como leídos los avisos del
                    // equipo (lo único que esto gestiona de verdad) — el
                    // número deja de tener sentido, se quita del todo.
                    const badge = document.querySelector(".notif-bell__badge");
                    if (badge) badge.remove();
                })
                .catch(() => {});
        },
    };
}
