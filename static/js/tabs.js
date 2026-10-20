// Zakładki panelu na telefonie przewijają się w poziomie: bieżąca ma być widoczna od razu.
(function () {
  "use strict";
  var current = document.querySelector('.tabs [aria-current="page"]');
  if (!current) return;
  var tabs = current.parentNode;
  if (tabs.scrollWidth <= tabs.clientWidth) return;
  var offset = current.getBoundingClientRect().left - tabs.getBoundingClientRect().left;
  tabs.scrollLeft += offset - (tabs.clientWidth - current.offsetWidth) / 2;
})();
