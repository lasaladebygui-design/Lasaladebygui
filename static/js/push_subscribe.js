(function () {
    "use strict";

    function urlBase64ToUint8Array(base64String) {
        var padding = "=".repeat((4 - (base64String.length % 4)) % 4);
        var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
        var rawData = window.atob(base64);
        var outputArray = new Uint8Array(rawData.length);
        for (var i = 0; i < rawData.length; i++) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    function getCsrfToken() {
        var match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
        return match ? match[1] : "";
    }

    function postJson(url, body) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrfToken(),
            },
            body: JSON.stringify(body),
        });
    }

    async function subscribeToPush(button) {
        var meta = document.querySelector('meta[name="vapid-public-key"]');
        if (!meta || !("serviceWorker" in navigator) || !("PushManager" in window)) return;

        var permission = await Notification.requestPermission();
        if (permission !== "granted") return;

        var registration = await navigator.serviceWorker.ready;
        var subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(meta.content),
        });

        await postJson(button.dataset.subscribeUrl, subscription.toJSON());
        button.textContent = "🔔 Notificaciones activadas";
        button.disabled = true;
    }

    document.addEventListener("DOMContentLoaded", function () {
        var button = document.querySelector("[data-push-subscribe]");
        if (!button) return;

        if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
            button.hidden = true;
            return;
        }

        navigator.serviceWorker.ready.then(function (registration) {
            return registration.pushManager.getSubscription();
        }).then(function (existing) {
            if (existing) {
                button.textContent = "🔔 Notificaciones activadas";
                button.disabled = true;
            }
        }).catch(function () {});

        button.addEventListener("click", function () {
            subscribeToPush(button).catch(function () {});
        });
    });
})();
