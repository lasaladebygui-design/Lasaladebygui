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
                    // Abrir el panel solo marca como leídos los avisos del
                    // equipo — mensajes/solicitudes/artículos/tienda siguen
                    // sin leer hasta que se visita su propia página, así que
                    // el globo no se quita sin más: se deja con lo que de
                    // verdad queda pendiente (o se quita si ya no queda
                    // nada), para que no reaparezca igual en la siguiente
                    // recarga como si abrir la campanita no hubiera servido.
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
