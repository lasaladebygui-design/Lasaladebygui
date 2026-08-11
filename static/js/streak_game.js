// Feedback en verde/rojo al responder en los juegos de racha (Trivial,
// Frases célebres, Actor, Malas descripciones, Emoji, V/F): intercepta el
// envío del formulario, lo manda por fetch en vez de navegar, colorea el
// botón pulsado según la respuesta ya calculada por el servidor (se detecta
// mirando el HTML que devuelve, sin tocar la lógica de las vistas) y, tras
// un instante para que se vea el color, sustituye el contenido por el que
// ha devuelto el servidor — mismo resultado que una recarga, pero con el
// color visible primero.
//
// Delegado desde `document` (no desde cada `<form>`) porque el formulario se
// sustituye entero en cada ronda: un listener puesto directamente en él se
// perdería en cuanto se reemplaza.
document.addEventListener("submit", async (event) => {
    const form = event.target.closest(".js-streak-answer-form");
    if (!form) return;

    const submitter = event.submitter;
    if (!submitter || submitter.type !== "submit") return;

    event.preventDefault();

    const buttons = Array.from(form.querySelectorAll("button[type=submit]"));
    buttons.forEach((btn) => { btn.disabled = true; });

    const formData = new FormData(form);
    if (submitter.name) formData.append(submitter.name, submitter.value);

    let html;
    try {
        const response = await fetch(form.getAttribute("action") || window.location.href, {
            method: "POST",
            body: formData,
        });
        html = await response.text();
    } catch (err) {
        // Sin red: que se comporte como un envío normal.
        form.submit();
        return;
    }

    const wrong = html.includes("Fallaste —") || html.includes("No era —");
    submitter.classList.add(wrong ? "btn--flash-wrong" : "btn--flash-correct");

    await new Promise((resolve) => setTimeout(resolve, 650));

    const newRoot = new DOMParser().parseFromString(html, "text/html").getElementById("game-root");
    const oldRoot = document.getElementById("game-root");
    if (newRoot && oldRoot) {
        oldRoot.replaceWith(newRoot);
    } else {
        window.location.reload();
    }
});
