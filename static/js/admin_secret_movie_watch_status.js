(function () {
    // "series_watch_status" está siempre en el formulario (SecretMovieForm) pero
    // solo tiene sentido cuando la portada elegida es una serie — esto la
    // muestra/oculta al vuelo en cuanto cambia el campo "movie" (select2), sin
    // esperar a guardar y volver a abrir la entrada.
    function fieldRow() {
        return document.querySelector(".field-series_watch_status");
    }

    function toggle(isTV) {
        var row = fieldRow();
        if (row) row.style.display = isTV ? "" : "none";
    }

    function checkMovie() {
        var select = document.getElementById("id_movie");
        if (!select || !select.value) {
            toggle(false);
            return;
        }
        fetch("/admin/secret/secretmovie/movie-is-tv/" + select.value + "/")
            .then(function (r) { return r.json(); })
            .then(function (data) { toggle(!!data.is_tv); })
            .catch(function () {});
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (!fieldRow()) return;
        checkMovie();
        if (window.django && window.django.jQuery) {
            window.django.jQuery(document).on("change", "#id_movie", checkMovie);
        } else {
            var select = document.getElementById("id_movie");
            if (select) select.addEventListener("change", checkMovie);
        }
    });
})();
