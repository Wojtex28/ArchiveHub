// Formularz zdarzenia z życia (ETAP 54): „Gdzie pokazać” przestawia się samo przy zmianie rodzaju
// (miejsce zamieszkania pod osią czasu, reszta na osi), dopóki ktoś nie wybierze ręcznie.
(function () {
  "use strict";

  function setup(select) {
    var form = select.form;
    if (!form) return;
    var below = (select.getAttribute("data-event-kind") || "").split(" ");
    var radios = form.querySelectorAll('input[name="on_timeline"]');
    var touched = false;
    radios.forEach(function (radio) { radio.addEventListener("change", function () { touched = true; }); });
    select.addEventListener("change", function () {
      if (touched) return;
      var value = below.indexOf(select.value) >= 0 ? "0" : "1";
      radios.forEach(function (radio) { radio.checked = radio.value === value; });
    });
  }

  function start() { document.querySelectorAll("select[data-event-kind]").forEach(setup); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
