// Przyciski z data-confirm pytają przed wysłaniem formularza (np. „Usuń” w panelu).
(function () {
  "use strict";
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-confirm]");
    if (button && !window.confirm(button.getAttribute("data-confirm"))) event.preventDefault();
  });
})();
