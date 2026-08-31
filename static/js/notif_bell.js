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
                .then((r) => {
                    const remaining = parseInt(r.headers.get("X-Notif-Remaining"), 10) || 0;
                    return r.text().then((text) => ({ text, remaining }));
                })
                .then(({ text, remaining }) => {
                    this.html = text;
                    this.loaded = true;
                    // Abrir el panel resetea el número entero de golpe (ver
                    // apps.core.notifications._after_last_seen) — lo que
                    // quede aquí ya es de verdad lo nuevo desde la última
                    // vez que se abrió, no lo de siempre reapareciendo.
                    const badge = document.querySelector(".notif-bell__badge");
                    if (badge) {
                        if (remaining > 0) badge.textContent = remaining;
                        else badge.remove();
                    }
                })
                .catch(() => {});
        },
    };
}
