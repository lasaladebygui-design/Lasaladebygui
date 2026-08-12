// Jazzmin pone todos los "topmenu_links" juntos a la izquierda de la barra
// superior. El botón de exportar a Excel se pide junto al menú de usuario,
// a la derecha, pero como botón propio (no dentro del desplegable de
// perfil) — así que movemos su <li> al <ul> de la derecha, justo antes del
// menú de usuario.
document.addEventListener("DOMContentLoaded", function () {
    var exportLink = document.querySelector('a[href*="admin-exportar"]');
    var rightNav = document.querySelector(".app-header .navbar-nav.ms-auto");
    if (!exportLink || !rightNav || !rightNav.lastElementChild) return;
    var item = exportLink.closest("li");
    if (!item) return;
    // El menú de usuario es siempre el último <li> de este <ul> — insertar
    // justo antes deja el botón pegado a él sin entrar en su desplegable.
    rightNav.insertBefore(item, rightNav.lastElementChild);
});
