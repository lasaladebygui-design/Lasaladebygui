function themeSwitcher() {
    return {
        open: false,
        busy: false,

        csrfToken() {
            const match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
            return match ? match[1] : "";
        },

        choose(slug) {
            if (this.busy) return;
            this.busy = true;
            fetch(`/tema/${slug}/`, {
                method: "POST",
                headers: { "X-CSRFToken": this.csrfToken() },
            })
                .then(() => window.location.reload())
                .catch(() => { this.busy = false; });
        },

        reset() {
            if (this.busy) return;
            this.busy = true;
            fetch("/tema/reset/", {
                method: "POST",
                headers: { "X-CSRFToken": this.csrfToken() },
            })
                .then(() => window.location.reload())
                .catch(() => { this.busy = false; });
        },
    };
}
