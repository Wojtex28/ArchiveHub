// Tryb nocny (ETAP 40). Serwer wstawia data-theme na <html> z ciasteczka „motyw”, więc strona
// nie mruga przy wczytaniu. Tutaj: poprawny stan przełącznika, gdy wyboru jeszcze nie było
// (wtedy obowiązuje ustawienie systemu), i przełączanie bez przeładowania strony.
(function () {
  "use strict";
  const root = document.documentElement;
  const system = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function current() {
    const chosen = root.getAttribute("data-theme");
    if (chosen === "dark" || chosen === "light") return chosen;
    return system && system.matches ? "dark" : "light";
  }

  function paint() {
    const dark = current() === "dark";
    document.querySelectorAll("[data-theme-toggle] button").forEach(function (button) {
      button.value = dark ? "jasny" : "ciemny";
      button.setAttribute("aria-checked", dark ? "true" : "false");
    });
  }

  function choose(theme) {
    root.setAttribute("data-theme", theme);
    const value = theme === "dark" ? "ciemny" : "jasny";
    const secure = location.protocol === "https:" ? "; Secure" : "";
    document.cookie = "motyw=" + value + "; Max-Age=31536000; Path=/; SameSite=Lax" + secure;
    paint();
    // Tło logowania czyta kolory kropek przy starcie; inne strony nie potrzebują przeładowania.
    document.dispatchEvent(new CustomEvent("themechange", { detail: { theme: theme } }));
  }

  document.addEventListener("submit", function (event) {
    const form = event.target.closest("[data-theme-toggle]");
    if (!form) return;
    event.preventDefault();
    choose(current() === "dark" ? "light" : "dark");
  });

  if (system && system.addEventListener) system.addEventListener("change", paint);
  paint();
})();
