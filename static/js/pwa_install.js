(function () {
    "use strict";

    var SESSION_SHOWN_FLAG = "bygui_pwa_prompt_shown";

    function isStandalone() {
        return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
    }

    if ("serviceWorker" in navigator) {
        window.addEventListener("load", function () {
            navigator.serviceWorker.register("/sw.js").then(function (registration) {
                // Comprueba si hay una versión nueva del service worker en
                // cada carga, en vez de esperar a la revisión periódica que
                // hace el navegador por su cuenta (puede tardar hasta 24h) —
                // así un despliegue nuevo se nota lo antes posible.
                registration.update().catch(function () {});
            }).catch(function () {});
        });
    }

    if (isStandalone()) return;

    var deferredPrompt = null;

    function showInstallBanner() {
        sessionStorage.setItem(SESSION_SHOWN_FLAG, "1");

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

        // Como mucho una vez por sesión de navegador: si ya se mostró (se
        // instalase o se le diera a "Ahora no"), no se vuelve a insistir
        // hasta la próxima vez que se abra el sitio (sessionStorage se
        // reinicia solo al cerrar la pestaña/navegador).
        if (sessionStorage.getItem(SESSION_SHOWN_FLAG)) return;

        showInstallBanner();
    });

    window.addEventListener("appinstalled", function () {
        deferredPrompt = null;
    });
})();
