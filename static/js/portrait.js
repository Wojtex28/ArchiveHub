// Portret osoby (ETAP 45): kadr w kółku i okno wyboru portretu.
// Kadr to położenie zdjęcia w procentach (jak object-position) i powiększenie. Ustawia je skrypt,
// bo strona nie pozwala na style wpisane w HTML; bez skryptu portret jest po prostu wyśrodkowany.
(function () {
  "use strict";

  var ZOOM_MAX = 4;
  var FACE_ZOOM = 2.2; // powiększenie startowe, gdy osoba ma punkt na zdjęciu

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function apply(img, x, y, zoom) {
    // Zdjęcie czekające na obrót obraca przeglądarka wokół środka, więc kadr wraca do środka na ten czas.
    if (/\brot-(90|180|270)\b/.test(img.className)) x = y = 50, zoom = 1;
    img.style.objectPosition = x + "% " + y + "%";
    img.style.transformOrigin = x + "% " + y + "%";
    img.style.scale = zoom > 1 ? String(zoom) : "";
  }

  function applyAll(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll("img[data-portrait]"), function (img) {
      apply(img, Number(img.getAttribute("data-x")), Number(img.getAttribute("data-y")), Number(img.getAttribute("data-zoom")) || 1);
    });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // Ile zdjęcia wystaje poza kółko w każdej osi (1 = nic): z proporcji zdjęcia i powiększenia.
  function cover(img, zoom) {
    var ratio = img.naturalWidth && img.naturalHeight ? img.naturalWidth / img.naturalHeight : 1;
    return { x: 1 / (zoom * Math.max(1, ratio)), y: 1 / (zoom * Math.max(1, 1 / ratio)) };
  }

  // Położenie (0–100), przy którym punkt zdjęcia ``focus`` (0–1) trafia na środek kółka.
  function centerOn(focus, k) {
    return k > 0.999 ? 50 : clamp((focus - 0.5 * k) / (1 - k), 0, 1) * 100;
  }

  // Zamienia listę zdjęć do wyboru (pola radio ``portrait``) na podgląd z przyciskiem i oknem wyboru.
  // ``crop`` to obecny kadr {x, y, zoom}; pola ``portrait_x``, ``portrait_y``, ``portrait_zoom`` w tym
  // samym fieldsecie dostają wynik (tworzą się, jeśli ich nie ma).
  function attach(box, crop, initial) {
    var list = box.querySelector(".portrait-choice__list");
    if (!list || box.querySelector(".portrait-pick")) return;
    var radios = Array.prototype.slice.call(list.querySelectorAll("input[name=portrait]"));
    var photos = radios.map(function (radio) {
      var img = radio.parentNode.querySelector("img");
      var mark = radio.getAttribute("data-mark");
      return {
        radio: radio,
        id: radio.value,
        url: img ? img.src : null,
        turn: img ? img.className : "",
        mark: mark ? mark.split(",").map(Number) : null
      };
    });
    var fields = {};
    ["x", "y", "zoom"].forEach(function (key) {
      var name = "portrait_" + key;
      var input = box.querySelector("input[name=" + name + "]") || (box.form || document).querySelector("input[name=" + name + "]");
      if (!input) {
        input = el("input");
        input.type = "hidden";
        input.name = name;
        box.appendChild(input);
      }
      if (crop) input.value = crop[key];
      fields[key] = input;
    });
    var state = {
      photo: photos.filter(function (photo) { return photo.radio.checked; })[0] || photos[0],
      x: Number(fields.x.value) || 50,
      y: Number(fields.y.value) || 50,
      zoom: Number(fields.zoom.value) || 1
    };
    initial = initial || "?";
    list.hidden = true;

    function fill(frame, photo, view) {
      frame.replaceChildren();
      frame.classList.toggle("tree-avatar--empty", !photo.url);
      if (!photo.url) {
        frame.textContent = initial;
        return null;
      }
      var img = el("img", photo.turn);
      img.src = photo.url;
      img.alt = "";
      img.draggable = false;
      frame.appendChild(img);
      apply(img, view.x, view.y, view.zoom);
      return img;
    }

    // Podgląd w formularzu.
    var row = el("div", "portrait-pick");
    var preview = el("span", "tree-avatar tree-avatar--photo portrait-pick__preview");
    var open = el("button", "button button--quiet");
    open.type = "button";
    var count = el("span", "hint", (photos.length - 1) + " zdjęć z tą osobą");
    row.append(preview, open, count);
    box.insertBefore(row, list);

    function showChoice() {
      fill(preview, state.photo, state);
      open.textContent = state.photo.url ? "Zmień portret" : "Wybierz portret";
    }
    showChoice();

    // Okno wyboru.
    var dialog = el("dialog", "portrait-dialog");
    var head = el("div", "portrait-dialog__head");
    head.appendChild(el("h2", "portrait-dialog__title", "Portret"));
    var close = el("button", "portrait-dialog__close", "✕");
    close.type = "button";
    close.setAttribute("aria-label", "Zamknij bez zmian");
    head.appendChild(close);

    var body = el("div", "portrait-dialog__body");
    var cropBox = el("div", "portrait-dialog__crop");
    var frame = el("div", "tree-avatar tree-avatar--photo portrait-dialog__frame");
    var note = el("p", "hint portrait-dialog__note");
    var zoomRow = el("label", "portrait-dialog__zoom");
    zoomRow.appendChild(el("span", "", "Powiększenie"));
    var slider = el("input");
    slider.type = "range";
    slider.min = "1";
    slider.max = String(ZOOM_MAX);
    slider.step = "0.05";
    zoomRow.appendChild(slider);
    cropBox.append(frame, zoomRow, note);

    var side = el("div", "portrait-dialog__side");
    side.appendChild(el("p", "portrait-dialog__label", "Zdjęcia z tą osobą"));
    var grid = el("ul", "portrait-dialog__grid");
    side.appendChild(grid);
    body.append(cropBox, side);

    var foot = el("div", "portrait-dialog__foot");
    var done = el("button", "button", "Gotowe");
    done.type = "button";
    var cancel = el("button", "button button--quiet", "Anuluj");
    cancel.type = "button";
    foot.append(done, cancel);
    dialog.append(head, body, foot);
    box.appendChild(dialog);

    var draft = null; // {photo, x, y, zoom} w otwartym oknie
    var cropImg = null;

    function showDraft() {
      cropImg = fill(frame, draft.photo, draft);
      slider.value = draft.zoom;
      zoomRow.hidden = !cropImg;
      note.textContent = cropImg
        ? "Przeciągnij zdjęcie, żeby ustawić twarz w kółku."
        : "Bez portretu: na kafelku będzie pierwsza litera imienia.";
      Array.prototype.forEach.call(grid.children, function (item, index) {
        item.firstChild.setAttribute("aria-pressed", String(photos[index] === draft.photo));
      });
    }

    function redraw() {
      if (cropImg) apply(cropImg, draft.x, draft.y, draft.zoom);
    }

    function choose(photo) {
      draft = { photo: photo, x: 50, y: 50, zoom: 1 };
      showDraft();
      if (!cropImg || !photo.mark) return;
      // Osoba ma punkt na tym zdjęciu: kadr od razu na twarz.
      var center = function () {
        if (draft.photo !== photo || !cropImg.naturalWidth) return;
        draft.zoom = FACE_ZOOM;
        var k = cover(cropImg, draft.zoom);
        draft.x = centerOn(photo.mark[0], k.x);
        draft.y = centerOn(photo.mark[1], k.y);
        slider.value = draft.zoom;
        redraw();
      };
      if (cropImg.complete) center();
      else cropImg.addEventListener("load", center);
    }

    photos.forEach(function (photo) {
      var item = el("li");
      var button = el("button", "portrait-dialog__photo");
      button.type = "button";
      if (photo.url) {
        var img = el("img", photo.turn);
        img.src = photo.url;
        img.alt = "Zdjęcie " + photo.id;
        img.loading = "lazy";
        button.appendChild(img);
      } else {
        button.classList.add("portrait-dialog__photo--none");
        button.textContent = "bez portretu";
      }
      button.addEventListener("click", function () { choose(photo); });
      item.appendChild(button);
      grid.appendChild(item);
    });

    // Przeciąganie przesuwa zdjęcie pod kółkiem; kółko myszy i suwak powiększają.
    var drag = null;
    frame.addEventListener("pointerdown", function (event) {
      if (!cropImg) return;
      drag = { x: event.clientX, y: event.clientY };
      frame.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    frame.addEventListener("pointermove", function (event) {
      if (!drag || !cropImg) return;
      var size = frame.clientWidth;
      var k = cover(cropImg, draft.zoom);
      if (k.x < 0.999) draft.x = clamp(draft.x - (event.clientX - drag.x) / size * k.x / (1 - k.x) * 100, 0, 100);
      if (k.y < 0.999) draft.y = clamp(draft.y - (event.clientY - drag.y) / size * k.y / (1 - k.y) * 100, 0, 100);
      drag = { x: event.clientX, y: event.clientY };
      redraw();
    });
    ["pointerup", "pointercancel"].forEach(function (name) {
      frame.addEventListener(name, function () { drag = null; });
    });
    function setZoom(zoom) {
      draft.zoom = clamp(zoom, 1, ZOOM_MAX);
      slider.value = draft.zoom;
      redraw();
    }
    slider.addEventListener("input", function () { setZoom(Number(slider.value)); });
    frame.addEventListener("wheel", function (event) {
      if (!cropImg) return;
      event.preventDefault();
      setZoom(draft.zoom * Math.exp(-event.deltaY * 0.002));
    }, { passive: false });

    open.addEventListener("click", function () {
      draft = { photo: state.photo, x: state.x, y: state.y, zoom: state.zoom };
      showDraft();
      if (dialog.showModal) dialog.showModal();
      else dialog.setAttribute("open", "");
    });
    function shut() {
      if (dialog.close) dialog.close();
      else dialog.removeAttribute("open");
    }
    close.addEventListener("click", shut);
    cancel.addEventListener("click", shut);
    done.addEventListener("click", function () {
      state = { photo: draft.photo, x: draft.x, y: draft.y, zoom: draft.zoom };
      state.photo.radio.checked = true;
      fields.x.value = state.x.toFixed(2);
      fields.y.value = state.y.toFixed(2);
      fields.zoom.value = state.zoom.toFixed(2);
      showChoice();
      shut();
    });
    // Escape w oknie zamyka tylko okno, a nie formularz pod nim.
    dialog.addEventListener("keydown", function (event) {
      if (event.key === "Escape") event.stopPropagation();
    });
  }

  window.Portrait = { apply: apply, applyAll: applyAll, attach: attach };

  function start() {
    applyAll();
    var box = document.querySelector("[data-portrait-choice]");
    if (box) attach(box, null, box.getAttribute("data-initial"));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
