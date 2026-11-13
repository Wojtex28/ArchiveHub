// Lista albumów (ETAP 49): przesunięcie myszą po okładce pokazuje kolejne zdjęcia z albumu.
// Tylko dla myszy; na dotyku okładka zostaje stała, a stuknięcie otwiera album.
(function () {
  "use strict";

  function setup(cover) {
    var main = cover.querySelector(".album-card__main");
    var photos = main ? Array.prototype.slice.call(main.querySelectorAll("img")) : [];
    var dots = Array.prototype.slice.call(cover.querySelectorAll(".album-card__dots > span"));
    if (photos.length < 2) return;
    var shown = 0;

    function show(index) {
      if (index === shown) return;
      photos[shown].hidden = true;
      photos[index].hidden = false;
      if (dots[shown]) dots[shown].classList.remove("is-on");
      if (dots[index]) dots[index].classList.add("is-on");
      shown = index;
    }

    cover.addEventListener("pointerenter", function (event) {
      if (event.pointerType !== "mouse") return;
      cover.classList.add("is-previewing");
      // Pozostałe miniatury ładują się dopiero, gdy ktoś zacznie oglądać tę okładkę.
      photos.forEach(function (img) { img.loading = "eager"; });
    });
    cover.addEventListener("pointermove", function (event) {
      if (event.pointerType !== "mouse") return;
      var box = cover.getBoundingClientRect();
      var part = (event.clientX - box.left) / Math.max(1, box.width);
      show(Math.min(photos.length - 1, Math.max(0, Math.floor(part * photos.length))));
    });
    cover.addEventListener("pointerleave", function () {
      cover.classList.remove("is-previewing");
      show(0);
    });
  }

  // Przełącznik kafelki / lista (ETAP 50): od razu, bez przeładowania; wybór zostaje w ciasteczku.
  function setupSwitch(box) {
    var list = document.querySelector("[data-album-list]");
    if (!list) return;
    box.addEventListener("click", function (event) {
      var link = event.target.closest("[data-view]");
      if (!link) return;
      event.preventDefault();
      var view = link.getAttribute("data-view");
      list.classList.remove("album-grid--lista", "album-grid--kafelki");
      list.classList.add("album-grid--" + view);
      Array.prototype.forEach.call(box.querySelectorAll("[data-view]"), function (other) {
        if (other === link) other.setAttribute("aria-current", "true");
        else other.removeAttribute("aria-current");
      });
      document.cookie = "albumy_widok=" + view + "; path=/; max-age=31536000; SameSite=Lax";
    });
  }

  function start() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-album-preview]"), setup);
    var box = document.querySelector("[data-view-switch]");
    if (box) setupSwitch(box);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
