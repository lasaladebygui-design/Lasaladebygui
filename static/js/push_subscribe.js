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

    function setButtonState(button, subscribed) {
        button.textContent = subscribed ? "🔕 Desactivar notificaciones" : "🔔 Activar notificaciones";
        button.dataset.subscribed = subscribed ? "1" : "";
    }

    async function subscribeToPush(button) {
        var meta = document.querySelector('meta[name="vapid-public-key"]');
        if (!meta) return;

        var permission = await Notification.requestPermission();
        if (permission !== "granted") return;

        var registration = await navigator.serviceWorker.ready;
        var subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(meta.content),
        });

        await postJson(button.dataset.subscribeUrl, subscription.toJSON());
        setButtonState(button, true);
    }

    async function unsubscribeFromPush(button) {
        var registration = await navigator.serviceWorker.ready;
        var subscription = await registration.pushManager.getSubscription();
        if (subscription) {
            await postJson(button.dataset.unsubscribeUrl, { endpoint: subscription.endpoint });
            await subscription.unsubscribe();
        }
        setButtonState(button, false);
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
            setButtonState(button, !!existing);
        }).catch(function () {});

        button.addEventListener("click", function () {
            var action = button.dataset.subscribed ? unsubscribeFromPush : subscribeToPush;
            action(button).catch(function () {});
        });
    });
})();
