(function () {
    "use strict";

    var VISITS_KEY = "bygui_pwa_visits";
    var SESSION_FLAG = "bygui_pwa_session_counted";
    var EVERY_N_VISITS = 3;

    function isStandalone() {
        return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
    }

    if ("serviceWorker" in navigator) {
        window.addEventListener("load", function () {
            navigator.serviceWorker.register("/sw.js").catch(function () {});
        });
    }

    if (isStandalone()) return;

    if (!sessionStorage.getItem(SESSION_FLAG)) {
        sessionStorage.setItem(SESSION_FLAG, "1");
        var visits = parseInt(localStorage.getItem(VISITS_KEY) || "0", 10) + 1;
        localStorage.setItem(VISITS_KEY, String(visits));
    }

    var deferredPrompt = null;

    function showInstallBanner() {
        var banner = document.createElement("div");
        banner.className = "pwa-install-banner";
        banner.innerHTML =
            '<span>📱 Instala La Sala de Bygui como app</span>' +
            '<button type="button" class="btn btn--accent btn--sm" data-pwa-install>Instalar</button>' +
            '<button type="button" class="btn btn--ghost btn--sm" data-pwa-dismiss>Ahora no</button>';
        document.body.appendChild(banner);

        banner.querySelector("[data-pwa-install]").addEventListener("click", function () {
            banner.remove();
            if (!deferredPrompt) return;
            deferredPrompt.prompt();
            deferredPrompt.userChoice.finally(function () {
                deferredPrompt = null;
            });
        });
        banner.querySelector("[data-pwa-dismiss]").addEventListener("click", function () {
            banner.remove();
        });
    }

    window.addEventListener("beforeinstallprompt", function (event) {
        event.preventDefault();
        deferredPrompt = event;

        var visits = parseInt(localStorage.getItem(VISITS_KEY) || "0", 10);
        if (visits % EVERY_N_VISITS !== 0) return;

        showInstallBanner();
    });

    window.addEventListener("appinstalled", function () {
        deferredPrompt = null;
    });
})();
