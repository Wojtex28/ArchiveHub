// Lista z atrybutem data-autosubmit wysyła swój formularz od razu po wyborze (0.61.0).
// Bez JavaScriptu działa przycisk obok listy.
(function () {
  "use strict";
  document.querySelectorAll("[data-autosubmit]").forEach(function (field) {
    field.addEventListener("change", function () {
      if (field.form) field.form.submit();
    });
  });
})();
