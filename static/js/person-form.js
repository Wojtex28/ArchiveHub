// Formularz danych osoby (ETAP 42): data i miejsce śmierci pojawiają się dopiero po włączeniu
// przełącznika „Nie żyje”. Ukryte pola są wyłączone, więc wyłączony przełącznik czyści je przy zapisie.
// Bez JavaScriptu wszystkie pola są widoczne, jak dawniej.
(function () {
  "use strict";
  document.querySelectorAll(".person-form").forEach(function (form) {
    const box = form.querySelector("input[name=deceased]");
    if (!box) return;
    function update() {
      form.querySelectorAll(".field--death").forEach(function (row) {
        row.hidden = !box.checked;
        row.querySelectorAll("input, textarea").forEach(function (input) { input.disabled = !box.checked; });
      });
    }
    box.addEventListener("change", update);
    update();
  });
})();
