// Galeria: podgląd zdjęcia na cały ekran nad siatką miniatur.
// Bez JavaScriptu każda miniatura prowadzi do zwykłej strony zdjęcia, więc skrypt jest tylko wygodą.
(function () {
  "use strict";

  var SWIPE_MIN = 50; // px w poziomie, żeby przesunięcie palcem zmieniło zdjęcie
  var ZOOM_MAX = 5;
  // Poniżej 1 zdjęcie robi się mniejsze niż ekran: przy nietypowych proporcjach łatwiej je wtedy objąć wzrokiem.
  var ZOOM_MIN = 0.3;
  var ZOOM_DOUBLE = 2.5; // dwuklik albo dwukrotne stuknięcie
  var TAP_MS = 300;

  // Podgląd zajmuje cały ekran, więc gest dwóch palców nie może powiększać całej strony:
  // po takim powiększeniu nie było czego chwycić, żeby ją pomniejszyć (zostawało odświeżenie).
  // Zablokowane jest to w CSS (touch-action), a tu jeszcze dla Safari na iPhonie i jako ratunek,
  // gdy strona już jest powiększona (np. przed otwarciem podglądu): wraca do skali 1.
  var viewportMeta = document.querySelector("meta[name=viewport]");
  var viewportContent = viewportMeta ? viewportMeta.getAttribute("content") : "";
  var zoomGuard = false;

  function resetPageZoom() {
    var vv = window.visualViewport;
    if (!viewportMeta || !vv || vv.scale <= 1.01) return;
    viewportMeta.setAttribute("content", viewportContent + ", maximum-scale=1");
    window.setTimeout(function () { viewportMeta.setAttribute("content", viewportContent); }, 400);
  }

  function guardPageZoom(on) {
    zoomGuard = on;
    if (on) resetPageZoom();
  }

  // Safari na iPhonie: własne zdarzenia gestu powiększania strony.
  ["gesturestart", "gesturechange"].forEach(function (name) {
    document.addEventListener(name, function (event) { if (zoomGuard) event.preventDefault(); }, { passive: false });
  });
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", function () { if (zoomGuard) resetPageZoom(); });
  }

  // Przesunięcie palcem w lewo/prawo. Gdy zdjęcie jest powiększone, palec je przesuwa, a nie zmienia.
  function onSwipe(element, callback, blocked) {
    var start = null;
    element.addEventListener("pointerdown", function (event) {
      start = event.isPrimary ? { x: event.clientX, y: event.clientY } : null;
    });
    element.addEventListener("pointercancel", function () { start = null; });
    element.addEventListener("pointerup", function (event) {
      if (!start) return;
      var dx = event.clientX - start.x;
      var dy = event.clientY - start.y;
      start = null;
      if (blocked && blocked()) return;
      if (Math.abs(dx) >= SWIPE_MIN && Math.abs(dx) > Math.abs(dy) * 1.5) callback(dx < 0 ? 1 : -1);
    });
  }

  // Stan obrazu: obrót z galerii i powiększenie (skala + przesunięcie względem środka).
  function view(img) {
    if (!img.zoom) img.zoom = { turn: 0, scale: 1, x: 0, y: 0 };
    return img.zoom;
  }

  function applyView(img) {
    var state = view(img);
    var parts = [];
    if (state.scale !== 1) parts.push("translate(" + state.x + "px, " + state.y + "px)", "scale(" + state.scale + ")");
    if (state.turn) parts.push("rotate(" + state.turn + "deg)");
    img.style.transform = parts.join(" ");
    img.parentNode.classList.toggle("is-zoomed", state.scale > 1);
    if (img.marks) img.marks.place();
  }

  // Powiększonego zdjęcia nie da się odsunąć tak, żeby za nim było puste tło.
  function clampPan(img) {
    var state = view(img);
    var stage = img.parentNode;
    var width = img.offsetWidth;
    var height = img.offsetHeight;
    if (state.turn % 180) {
      var swap = width;
      width = height;
      height = swap;
    }
    var maxX = Math.max(0, (width * state.scale - stage.clientWidth) / 2);
    var maxY = Math.max(0, (height * state.scale - stage.clientHeight) / 2);
    state.x = Math.min(maxX, Math.max(-maxX, state.x));
    state.y = Math.min(maxY, Math.max(-maxY, state.y));
  }

  // Zmienia powiększenie tak, żeby punkt pod kursorem albo palcami został w tym samym miejscu.
  function zoomAt(img, scale, clientX, clientY) {
    var state = view(img);
    var box = img.parentNode.getBoundingClientRect();
    scale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, scale));
    // Przy powrocie do zwykłego rozmiaru zdjęcie lekko „przyciąga” do 1.
    if (Math.abs(scale - 1) < 0.04) scale = 1;
    var px = clientX - (box.left + box.width / 2);
    var py = clientY - (box.top + box.height / 2);
    state.x = px - (px - state.x) * (scale / state.scale);
    state.y = py - (py - state.y) * (scale / state.scale);
    state.scale = scale;
    // Pomniejszone zdjęcie zawsze stoi na środku.
    if (scale <= 1) state.x = state.y = 0;
    clampPan(img);
    applyView(img);
  }

  function zoomBy(img, factor) {
    var box = img.parentNode.getBoundingClientRect();
    zoomAt(img, view(img).scale * factor, box.left + box.width / 2, box.top + box.height / 2);
  }

  function toggleZoom(img, clientX, clientY) {
    zoomAt(img, view(img).scale !== 1 ? 1 : ZOOM_DOUBLE, clientX, clientY);
  }

  // Powiększanie: kółko myszy, dwuklik, dwa palce, dwukrotne stuknięcie; przeciąganie przesuwa.
  function enableZoom(stage, img) {
    var pointers = {};
    var count = 0;
    var pinch = null;
    var pan = null;
    var lastTap = null;

    function points() {
      return Object.keys(pointers).slice(0, 2).map(function (id) { return pointers[id]; });
    }

    stage.addEventListener("pointerdown", function (event) {
      if (event.target.closest("a, button")) return;
      if (count === 0) stage.gesture = false;
      pointers[event.pointerId] = { x: event.clientX, y: event.clientY, x0: event.clientX, y0: event.clientY, time: Date.now() };
      count += 1;
      stage.classList.add("is-gesturing");
      if (count === 2) {
        var pair = points();
        pinch = { distance: Math.hypot(pair[0].x - pair[1].x, pair[0].y - pair[1].y) || 1, scale: view(img).scale };
        pan = null;
        stage.gesture = true;
      } else if (count === 1 && view(img).scale > 1) {
        pan = { x: event.clientX, y: event.clientY };
        stage.gesture = true;
        // Przeciąganie trwa, nawet gdy kursor wyjedzie poza zdjęcie albo nad przycisk.
        try { stage.setPointerCapture(event.pointerId); } catch (error) { /* starsza przeglądarka */ }
      }
      if (event.pointerType === "mouse") event.preventDefault();
    });

    stage.addEventListener("pointermove", function (event) {
      var pointer = pointers[event.pointerId];
      if (!pointer) return;
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      if (pinch && count >= 2) {
        var pair = points();
        var distance = Math.hypot(pair[0].x - pair[1].x, pair[0].y - pair[1].y);
        zoomAt(img, pinch.scale * distance / pinch.distance, (pair[0].x + pair[1].x) / 2, (pair[0].y + pair[1].y) / 2);
      } else if (pan) {
        var state = view(img);
        state.x += event.clientX - pan.x;
        state.y += event.clientY - pan.y;
        pan = { x: event.clientX, y: event.clientY };
        clampPan(img);
        applyView(img);
      }
    });

    function release(event) {
      var pointer = pointers[event.pointerId];
      if (!pointer) return;
      delete pointers[event.pointerId];
      count -= 1;
      if (count < 2) pinch = null;
      if (count === 0) {
        pan = null;
        stage.classList.remove("is-gesturing");
      }
      var quick = Date.now() - pointer.time < TAP_MS;
      var still = Math.abs(event.clientX - pointer.x0) < 10 && Math.abs(event.clientY - pointer.y0) < 10;
      if (event.type !== "pointerup" || event.pointerType === "mouse" || !quick || !still) return;
      if (lastTap && Date.now() - lastTap.time < TAP_MS && Math.abs(event.clientX - lastTap.x) < 30) {
        lastTap = null;
        stage.gesture = true;
        toggleZoom(img, event.clientX, event.clientY);
      } else {
        lastTap = { time: Date.now(), x: event.clientX };
      }
    }
    stage.addEventListener("pointerup", release);
    stage.addEventListener("pointercancel", release);
    // Firefox nie zna -webkit-user-drag: bez tego chwyta zdjęcie jak plik i przerywa przesuwanie.
    img.draggable = false;
    stage.addEventListener("dragstart", function (event) { event.preventDefault(); });
    stage.addEventListener("dblclick", function (event) { toggleZoom(img, event.clientX, event.clientY); });
    // Kółko myszy powiększa. Touchpad: rozsuwanie palców powiększa (przeglądarka wysyła je z Ctrl),
    // a przesuwanie dwoma palcami przesuwa powiększone zdjęcie, tak jak przewijanie strony.
    var touchpadUntil = 0;
    stage.addEventListener("wheel", function (event) {
      event.preventDefault();
      var now = Date.now();
      var smooth = event.deltaMode === 0 &&
        (event.deltaX !== 0 || event.deltaY % 1 !== 0 || Math.abs(event.deltaY) < 40);
      if (smooth) touchpadUntil = now + 400;
      var state = view(img);
      if (!event.ctrlKey && now < touchpadUntil && state.scale > 1) {
        state.x -= event.deltaX;
        state.y -= event.deltaY;
        clampPan(img);
        applyView(img);
        return;
      }
      zoomAt(img, state.scale * Math.exp(-event.deltaY * (event.ctrlKey && smooth ? 0.01 : 0.002)), event.clientX, event.clientY);
    }, { passive: false });
  }

  // „Moje albumy” (ETAP 51): okienko pod gwiazdką z listą Ulubione + albumy konta. Każde zaznaczenie
  // zapisuje się od razu; ``onState`` dostaje odpowiedź serwera (m.in. ``collected``: pełna gwiazdka).
  var collectMenu = null;

  function closeCollections() {
    if (!collectMenu) return;
    collectMenu.remove();
    collectMenu = null;
    document.removeEventListener("pointerdown", outsideCollections, true);
  }

  function outsideCollections(event) {
    if (collectMenu && !collectMenu.contains(event.target) && !collectMenu.anchor.contains(event.target)) closeCollections();
  }

  function openCollections(anchor, url, csrf, onState) {
    if (collectMenu && collectMenu.anchor === anchor) return closeCollections();
    closeCollections();
    var menu = document.createElement("div");
    menu.className = "collect-menu";
    menu.setAttribute("role", "dialog");
    menu.setAttribute("aria-label", "Dodaj zdjęcie do albumu");
    menu.anchor = anchor;
    menu.innerHTML = "<p class=\"collect-menu__title\">Dodaj do albumu</p><p class=\"collect-menu__wait\">Wczytuję…</p>";
    (anchor.closest(".viewer") || document.body).appendChild(menu);
    var box = anchor.getBoundingClientRect();
    var host = menu.parentNode.getBoundingClientRect();
    menu.style.top = (box.bottom - host.top + 8) + "px";
    menu.style.right = Math.max(8, host.right - box.right) + "px";
    collectMenu = menu;
    document.addEventListener("pointerdown", outsideCollections, true);

    function send(data) {
      var body = new FormData();
      Object.keys(data).forEach(function (key) { body.append(key, data[key]); });
      return fetch(url, {
        method: "POST",
        body: body,
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch", "X-CSRFToken": csrf }
      }).then(function (response) {
        if (!response.ok) throw new Error(response.status);
        return response.json();
      });
    }

    function row(label, key, on, extraClass) {
      var item = document.createElement("label");
      item.className = "collect-menu__item" + (extraClass ? " " + extraClass : "");
      var box = document.createElement("input");
      box.type = "checkbox";
      box.checked = on;
      box.addEventListener("change", function () {
        box.disabled = true;
        send({ album: key, on: box.checked ? "1" : "0" })
          .then(function (state) { onState(state); })
          .catch(function () { box.checked = !box.checked; })
          .then(function () { box.disabled = false; });
      });
      var text = document.createElement("span");
      text.textContent = label;
      item.append(box, text);
      return item;
    }

    function render(state) {
      if (collectMenu !== menu) return;
      menu.replaceChildren();
      var heading = document.createElement("p");
      heading.className = "collect-menu__title";
      heading.textContent = "Dodaj do albumu";
      menu.appendChild(heading);
      menu.appendChild(row("★ Ulubione", "ulubione", state.favorite, "collect-menu__item--favorites"));
      state.albums.forEach(function (album) { menu.appendChild(row(album.name, String(album.id), album.on)); });
      var form = document.createElement("form");
      form.className = "collect-menu__new";
      var input = document.createElement("input");
      input.name = "nowy";
      input.maxLength = 100;
      input.placeholder = "Nowy album…";
      input.setAttribute("aria-label", "Nazwa nowego albumu");
      var add = document.createElement("button");
      add.type = "submit";
      add.className = "button";
      add.textContent = "Dodaj";
      form.append(input, add);
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        if (!input.value.trim()) return input.focus();
        add.disabled = true;
        send({ nowy: input.value }).then(function (fresh) { onState(fresh); render(fresh); })
          .catch(function () { add.disabled = false; });
      });
      menu.appendChild(form);
    }

    fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (response) {
        if (!response.ok) throw new Error(response.status);
        return response.json();
      })
      .then(render)
      .catch(function () {
        if (collectMenu === menu) menu.querySelector(".collect-menu__wait").textContent = "Nie udało się wczytać. Spróbuj ponownie.";
      });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && collectMenu) {
      event.stopImmediatePropagation();
      var anchor = collectMenu.anchor;
      closeCollections();
      anchor.focus();
    }
  }, true);

  // Przyciski „−” i „+” na pasku (na komputerze): pomniejszają też poniżej rozmiaru ekranu.
  function zoomButtons(currentImg) {
    var box = document.createElement("span");
    box.className = "viewer__zoom";
    [["−", "Pomniejsz (klawisz −)", 1 / 1.5], ["+", "Powiększ (klawisz +)", 1.5]].forEach(function (item) {
      var node = document.createElement("button");
      node.type = "button";
      node.className = "viewer__rotate-button viewer__zoom-button";
      node.textContent = item[0];
      node.title = item[1];
      node.setAttribute("aria-label", item[1]);
      node.addEventListener("click", function () { zoomBy(currentImg(), item[2]); });
      box.appendChild(node);
    });
    return box;
  }

  function zoomKey(img, key) {
    if (key === "+" || key === "=") zoomBy(img, 1.5);
    else if (key === "-") zoomBy(img, 1 / 1.5);
    else if (key === "0") zoomAt(img, 1, 0, 0);
    else return false;
    return true;
  }

  // Obraz obrócony o 90° lub 270° ma zamienione boki: ograniczenia wymiarów też trzeba zamienić.
  // Nowe zdjęcie albo obrót zaczyna bez powiększenia; zmiana rozmiaru okna je zachowuje.
  function fitRotation(img, degrees, keepZoom) {
    var stage = img.parentNode;
    var state = view(img);
    state.turn = degrees;
    if (!keepZoom) {
      state.scale = 1;
      state.x = state.y = 0;
    }
    if (degrees % 180) {
      // Te same granice co bez obrotu: wnętrze sceny (bez marginesu) i na komputerze najwyżej 90%.
      var styles = window.getComputedStyle(stage);
      var room = window.matchMedia("(min-width: 40.0625rem)").matches ? 0.9 : 1;
      var inner = {
        width: stage.clientWidth - parseFloat(styles.paddingLeft) - parseFloat(styles.paddingRight),
        height: stage.clientHeight - parseFloat(styles.paddingTop) - parseFloat(styles.paddingBottom)
      };
      img.style.maxWidth = Math.floor(inner.height * room) + "px";
      img.style.maxHeight = Math.floor(inner.width * room) + "px";
    } else {
      img.style.maxWidth = "";
      img.style.maxHeight = "";
    }
    clampPan(img);
    applyView(img);
  }

  // Obrót zapisuje się od razu. Kilka szybkich kliknięć to kilka zapisów; serwer je sumuje.
  function saveRotation(url, csrf, side, direction, onError) {
    var body = new FormData();
    body.append("side", side);
    body.append("direction", direction);
    fetch(url, { method: "POST", body: body, credentials: "same-origin", headers: { "X-CSRFToken": csrf } })
      .then(function (response) { if (!response.ok) throw new Error(response.status); })
      .catch(onError);
  }

  function turned(degrees, direction) {
    return (degrees + (direction === "prawo" ? 90 : 270)) % 360;
  }

  // Podczas pisania komentarza strzałki przesuwają kursor w tekście, a nie zmieniają zdjęcia.
  function isTyping(event) {
    return Boolean(event.target.closest && event.target.closest("textarea, input, select"));
  }

  // Osoby i tagi wpisuje się po przecinku, a podpowiedzi (datalist) dotyczą ostatniej wpisywanej nazwy.
  function suggestNames(event) {
    var input = event.target;
    if (!input.matches || !input.matches("[data-list-input]") || !input.list) return;
    var list = input.list;
    if (!list.names) list.names = Array.prototype.map.call(list.options, function (option) { return option.value; });
    var cut = input.value.lastIndexOf(",");
    var prefix = cut < 0 ? "" : input.value.slice(0, cut + 1) + " ";
    var chosen = prefix.split(",").map(function (name) { return name.trim().toLowerCase(); });
    list.replaceChildren.apply(list, list.names.filter(function (name) {
      return chosen.indexOf(name.toLowerCase()) < 0;
    }).map(function (name) {
      var option = document.createElement("option");
      option.value = prefix + name;
      return option;
    }));
  }
  document.addEventListener("input", suggestNames);
  document.addEventListener("focusin", suggestNames);

  // Punkty osób na zdjęciu (ETAP 44). Lista „Kto jest na zdjęciu” w panelu niesie współrzędne
  // (ułamek szerokości i wysokości zdjęcia), a tu rysują się kropki nad zdjęciem. 📍 przy osobie
  // włącza wskazywanie: następne kliknięcie na zdjęciu zapisuje punkt.
  function createMarks(stage, img, options) {
    var layer = document.createElement("div");
    layer.className = "viewer__marks";
    layer.hidden = true;
    var hint = document.createElement("div");
    hint.className = "viewer__mark-hint";
    hint.hidden = true;
    stage.append(layer, hint);
    var people = [];
    var placing = null;
    var down = null;
    var url = "";

    // Środek i rozmiar zdjęcia tak, jak je widać (po powiększeniu, przesunięciu i obrocie).
    function box() {
      var state = view(img);
      var width = img.offsetWidth;
      var height = img.offsetHeight;
      var cx = img.offsetLeft + width / 2 + state.x;
      var cy = img.offsetTop + height / 2 + state.y;
      if (state.turn % 180) {
        var swap = width;
        width = height;
        height = swap;
      }
      return { cx: cx, cy: cy, width: width * state.scale, height: height * state.scale };
    }

    function place() {
      var area = box();
      people.forEach(function (person) {
        if (!person.dot) return;
        person.dot.style.left = area.cx + (person.x - 0.5) * area.width + "px";
        person.dot.style.top = area.cy + (person.y - 0.5) * area.height + "px";
      });
    }

    function stop() {
      placing = null;
      hint.hidden = true;
      stage.classList.remove("is-marking");
    }

    function clear() {
      stop();
      people = [];
      layer.replaceChildren();
      layer.hidden = true;
    }

    function lit(person, on) {
      if (person.dot) person.dot.classList.toggle("is-active", on);
    }

    function sync() {
      var root = options.panel();
      var list = root && root.querySelector("[data-marks]");
      var wanted = placing && placing.id;
      clear();
      if (!list) return;
      url = list.getAttribute("data-mark-url");
      Array.prototype.forEach.call(list.querySelectorAll("li[data-person]"), function (item) {
        var person = { id: item.getAttribute("data-person"), name: item.getAttribute("data-name"), item: item };
        if (item.hasAttribute("data-x")) {
          person.x = Number(item.getAttribute("data-x"));
          person.y = Number(item.getAttribute("data-y"));
          person.dot = document.createElement("button");
          person.dot.type = "button";
          person.dot.className = "viewer__mark";
          person.dot.setAttribute("aria-label", person.name);
          var label = document.createElement("span");
          label.className = "viewer__mark-name";
          label.textContent = person.name;
          person.dot.append(label);
          person.dot.addEventListener("click", function () { person.dot.classList.toggle("is-active"); });
          layer.append(person.dot);
        }
        item.addEventListener("mouseenter", function () { lit(person, true); });
        item.addEventListener("mouseleave", function () { lit(person, false); });
        item.querySelector("[data-mark-person]").addEventListener("click", function () { start(person); });
        people.push(person);
        if (person.id === wanted) start(person);
      });
      layer.hidden = false;
      place();
    }

    function hintButton(text, action) {
      var node = document.createElement("button");
      node.type = "button";
      node.className = "viewer__mark-action";
      node.textContent = text;
      node.addEventListener("click", action);
      return node;
    }

    function start(person) {
      if (placing === person) return stop();
      placing = person;
      stage.classList.add("is-marking");
      var text = document.createElement("span");
      text.textContent = "Kliknij na zdjęciu: " + person.name;
      hint.replaceChildren(text);
      if (person.dot) hint.append(hintButton("Usuń punkt", function () { send(person, null); }));
      hint.append(hintButton("Anuluj", stop));
      hint.hidden = false;
    }

    function send(person, point) {
      var body = new FormData();
      body.append("osoba", person.id);
      if (point) {
        body.append("x", point.x.toFixed(4));
        body.append("y", point.y.toFixed(4));
      } else body.append("usun", "1");
      stop();
      fetch(url, {
        method: "POST",
        body: body,
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch", "X-CSRFToken": options.csrf() }
      })
        .then(function (response) {
          if (!response.ok) throw new Error(response.status);
          return response.text().then(function (html) { options.onPanel(response, html); });
        })
        .catch(function () {
          hint.replaceChildren("Nie udało się zapisać punktu. Spróbuj ponownie.");
          hint.hidden = false;
          window.setTimeout(function () { if (!placing) hint.hidden = true; }, 4000);
        });
    }

    stage.addEventListener("pointerdown", function (event) { down = { x: event.clientX, y: event.clientY }; }, true);
    stage.addEventListener("click", function (event) {
      if (!placing || event.target.closest(".viewer__mark-hint")) return;
      // Przesuwanie powiększonego zdjęcia to nie kliknięcie.
      if (!down || Math.hypot(event.clientX - down.x, event.clientY - down.y) > 8) return;
      var area = box();
      var rect = stage.getBoundingClientRect();
      var x = (event.clientX - rect.left - area.cx) / area.width + 0.5;
      var y = (event.clientY - rect.top - area.cy) / area.height + 0.5;
      if (x < 0 || x > 1 || y < 0 || y > 1) return;
      send(placing, { x: x, y: y });
    });
    // Escape najpierw kończy wskazywanie, dopiero potem zamyka podgląd.
    document.addEventListener("keydown", function (event) {
      if (!placing || event.key !== "Escape") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      stop();
    }, true);
    img.addEventListener("load", place);

    // Serwer obraca punkty razem ze zdjęciem; tu to samo od razu na ekranie.
    function turn(clockwise) {
      people.forEach(function (person) {
        if (!person.dot) return;
        var x = clockwise ? 1 - person.y : person.y;
        person.y = clockwise ? person.x : 1 - person.x;
        person.x = x;
        person.item.setAttribute("data-x", person.x);
        person.item.setAttribute("data-y", person.y);
      });
      place();
    }

    img.marks = { place: place, sync: sync, clear: clear, turn: turn };
    return img.marks;
  }

  // Osobna strona zdjęcia (otwarta z linku): strzałki i gesty prowadzą po linkach.
  var page = document.querySelector("[data-viewer-page]");
  if (page) {
    guardPageZoom(true);
    var follow = function (selector) {
      var link = page.querySelector(selector);
      if (link) window.location.href = link.href;
    };
    document.addEventListener("keydown", function (event) {
      if (event.altKey || event.ctrlKey || event.metaKey || isTyping(event)) return;
      if (zoomKey(pageImg, event.key)) return;
      if (event.key === "ArrowLeft") follow("[rel=prev]");
      else if (event.key === "ArrowRight") follow("[rel=next]");
      else if (event.key === "Escape") follow("[data-close]");
    });
    var pageStage = page.querySelector("[data-stage]");
    var pageImg = page.querySelector(".viewer__img");
    onSwipe(pageStage, function (step) {
      follow(step > 0 ? "[rel=next]" : "[rel=prev]");
    }, function () { return pageStage.gesture || view(pageImg).scale > 1; });
    enableZoom(pageStage, pageImg);
    var rotateBox = page.querySelector("[data-rotate-url]");
    var starForm = page.querySelector("form[data-collections-url]");
    if (starForm) {
      starForm.addEventListener("submit", function (event) {
        event.preventDefault();
        var star = starForm.querySelector(".viewer__favorite");
        openCollections(star, starForm.getAttribute("data-collections-url"), rotateBox.getAttribute("data-csrf"), function (state) {
          star.classList.toggle("is-on", state.collected);
          star.setAttribute("aria-pressed", String(state.collected));
          star.firstChild.textContent = state.collected ? "★" : "☆";
        });
      });
    }
    rotateBox.parentNode.insertBefore(zoomButtons(function () { return pageImg; }), rotateBox);
    var refit = function (keepZoom) { fitRotation(pageImg, Number(pageImg.getAttribute("data-rotation")), keepZoom); };
    refit();
    window.addEventListener("resize", function () { refit(true); });
    var pagePanel = page.querySelector(".viewer__panel");
    var pageMarks = null;
    if (pagePanel && rotateBox.getAttribute("data-side") === "awers") {
      pageMarks = createMarks(pageStage, pageImg, {
        panel: function () { return pagePanel; },
        csrf: function () { return rotateBox.getAttribute("data-csrf"); },
        onPanel: function (response, html) {
          pagePanel.innerHTML = html;
          pageMarks.sync();
        }
      });
      pageMarks.sync();
    }
    rotateBox.addEventListener("click", function (event) {
      var button = event.target.closest("[data-direction]");
      if (!button) return;
      var before = Number(pageImg.getAttribute("data-rotation"));
      var direction = button.getAttribute("data-direction");
      pageImg.setAttribute("data-rotation", turned(before, direction));
      if (pageMarks) pageMarks.turn(direction === "prawo");
      refit();
      saveRotation(rotateBox.getAttribute("data-rotate-url"), rotateBox.getAttribute("data-csrf"),
        rotateBox.getAttribute("data-side"), direction, function () {
          pageImg.setAttribute("data-rotation", before);
          if (pageMarks) pageMarks.turn(direction !== "prawo");
          refit();
        });
    });
    return;
  }

  var grid = document.querySelector("[data-gallery]");
  if (!grid) return;
  var tiles = Array.prototype.slice.call(grid.querySelectorAll("a[data-preview]"));
  var albumTitle = grid.getAttribute("data-album-title");
  var csrf = grid.getAttribute("data-csrf");

  var viewer, img, count, flip, download, prevButton, nextButton, closeButton, rotateLeft, rotateRight;
  var commentsButton, commentsCount, panel, caption, title, favoriteButton, marks;
  var panelOpen = false;
  var panelTile = null;
  var panelFilled = null; // zdjęcie, którego opis faktycznie jest w panelu (wczytywanie trwa chwilę)
  var commentsRequest = 0;
  var current = -1;
  var reverse = false;
  var opener = null;
  var pushed = false;

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function button(className, symbol, label) {
    var node = element("button", className, symbol);
    node.type = "button";
    node.setAttribute("aria-label", label);
    return node;
  }

  function build() {
    viewer = element("div", "viewer");
    viewer.setAttribute("role", "dialog");
    viewer.setAttribute("aria-modal", "true");
    viewer.setAttribute("aria-label", "Podgląd zdjęcia");
    viewer.hidden = true;

    var bar = element("div", "viewer__bar");
    closeButton = button("viewer__close", "✕", "Zamknij podgląd");
    count = element("span", "viewer__count");
    flip = element("button", "viewer__flip");
    flip.type = "button";
    var rotate = element("span", "viewer__rotate");
    rotateLeft = button("viewer__rotate-button", "↺", "Obróć w lewo");
    rotateRight = button("viewer__rotate-button", "↻", "Obróć w prawo");
    rotateLeft.title = "Obróć w lewo";
    rotateRight.title = "Obróć w prawo";
    rotate.append(rotateLeft, rotateRight);
    download = element("a", "viewer__download", "⤓");
    download.setAttribute("download", "");
    download.title = "Pobierz w pełnej rozdzielczości";
    download.setAttribute("aria-label", "Pobierz w pełnej rozdzielczości");
    commentsButton = element("button", "viewer__comments", "💬");
    commentsButton.type = "button";
    commentsButton.title = "Osoby, opis i komentarze";
    commentsCount = element("span", "viewer__comments-count");
    commentsButton.append(commentsCount);
    favoriteButton = button("viewer__favorite", "☆", "Dodaj do ulubionych");
    title = element("span", "viewer__title", albumTitle);
    var zoom = zoomButtons(function () { return img; });
    bar.append(closeButton, title, count, zoom, rotate, flip, favoriteButton, commentsButton, download);

    var stage = element("div", "viewer__stage");
    img = element("img", "viewer__img");
    stage.append(img);
    caption = element("p", "viewer__caption");
    caption.hidden = true;

    prevButton = button("viewer__nav viewer__nav--prev", "‹", "Poprzednie zdjęcie");
    nextButton = button("viewer__nav viewer__nav--next", "›", "Następne zdjęcie");
    panel = element("aside", "viewer__panel");
    panel.setAttribute("aria-label", "Osoby, opis i komentarze");
    panel.hidden = true;
    panel.tabIndex = -1;
    viewer.append(bar, stage, caption, panel, prevButton, nextButton);
    document.body.append(viewer);

    closeButton.addEventListener("click", close);
    prevButton.addEventListener("click", function () { step(-1); });
    nextButton.addEventListener("click", function () { step(1); });
    flip.addEventListener("click", function () { show(current, !reverse); });
    rotateLeft.addEventListener("click", function () { turn("lewo"); });
    rotateRight.addEventListener("click", function () { turn("prawo"); });
    commentsButton.addEventListener("click", function () { setPanel(!panelOpen); });
    favoriteButton.addEventListener("click", toggleFavorite);
    panel.addEventListener("submit", sendPanelForm);
    panel.addEventListener("click", function (event) {
      if (!event.target.closest("[data-comments-close]")) return;
      event.preventDefault();
      setPanel(false);
      commentsButton.focus();
    });
    panel.addEventListener("keydown", function (event) {
      // Ctrl+Enter (Cmd+Enter na Macu) wysyła komentarz.
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && event.target.form) {
        event.preventDefault();
        event.target.form.requestSubmit();
      }
    });
    window.addEventListener("resize", function () { if (!viewer.hidden) fitRotation(img, rotationOf(tiles[current], reverse), true); });
    onSwipe(stage, step, function () { return stage.gesture || view(img).scale > 1; });
    enableZoom(stage, img);
    marks = createMarks(stage, img, {
      panel: function () { return panelOpen && panelFilled === tiles[current] && !reverse ? panel : null; },
      csrf: function () { return csrf; },
      onPanel: function (response, html) {
        commentsRequest += 1;
        fillPanel(panelTile, response, html);
      }
    });
    // Na całym dokumencie: gdy fokus zniknie z ukrytego przycisku, klawisze nadal działają.
    document.addEventListener("keydown", onKey);
  }

  function rotationOf(tile, onReverse) {
    return Number(tile.getAttribute(onReverse ? "data-reverse-rotation" : "data-rotation")) || 0;
  }

  function setRotation(tile, onReverse, degrees) {
    tile.setAttribute(onReverse ? "data-reverse-rotation" : "data-rotation", degrees);
    if (!onReverse) tile.querySelector("img").className = "rot-" + degrees;
    if (tiles[current] === tile && reverse === onReverse) fitRotation(img, degrees);
  }

  function turn(direction) {
    var tile = tiles[current];
    var side = reverse;
    var before = rotationOf(tile, side);
    setRotation(tile, side, turned(before, direction));
    if (!side) marks.turn(direction === "prawo");
    saveRotation(tile.getAttribute("data-rotate-url"), csrf, side ? "rewers" : "awers", direction, function () {
      setRotation(tile, side, before);
      if (!side && tiles[current] === tile) marks.turn(direction !== "prawo");
    });
  }

  // Ulubione (ETAP 29): ☆/★ zapisuje się od razu; po błędzie gwiazdka wraca do poprzedniego stanu.
  function isFavorite(tile) {
    return tile.getAttribute("data-favorite") === "1";
  }

  function setFavorite(tile, on) {
    tile.setAttribute("data-favorite", on ? "1" : "0");
    var badge = tile.querySelector(".gallery-tile__favorite");
    if (badge) badge.hidden = !on;
    if (tile === tiles[current]) showFavorite(tile);
  }

  function showFavorite(tile) {
    var on = isFavorite(tile);
    favoriteButton.textContent = on ? "★" : "☆";
    favoriteButton.classList.toggle("is-on", on);
    favoriteButton.setAttribute("aria-pressed", String(on));
    if (grid.hasAttribute("data-own-albums")) {
      favoriteButton.setAttribute("aria-label", "Dodaj do albumu");
      favoriteButton.title = on ? "W Twoich albumach (kliknij, żeby zmienić)" : "Dodaj do Ulubionych albo swojego albumu";
      return;
    }
    favoriteButton.setAttribute("aria-label", on ? "Usuń z ulubionych" : "Dodaj do ulubionych");
    favoriteButton.title = on ? "W ulubionych (kliknij, żeby usunąć)" : "Dodaj do ulubionych";
  }

  function toggleFavorite() {
    var tile = tiles[current];
    if (grid.hasAttribute("data-own-albums")) {
      openCollections(favoriteButton, tile.getAttribute("data-collections-url"), csrf, function (state) {
        setFavorite(tile, state.collected);
      });
      return;
    }
    var on = !isFavorite(tile);
    setFavorite(tile, on);
    var body = new FormData();
    body.append("ulubione", on ? "1" : "0");
    fetch(tile.getAttribute("data-favorite-url"), {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: { "X-Requested-With": "fetch", "X-CSRFToken": csrf }
    })
      .then(function (response) { if (!response.ok) throw new Error(response.status); })
      .catch(function () { setFavorite(tile, !on); });
  }

  // Komentarze: panel obok zdjęcia (na telefonie od dołu), wczytywany z serwera jako gotowy HTML.
  function commentCount(tile) {
    return Number(tile.getAttribute("data-comments")) || 0;
  }

  function showCommentCount(tile) {
    var number = commentCount(tile);
    commentsCount.textContent = number;
    commentsButton.setAttribute("aria-label", "Osoby, opis i komentarze (" + number + ")");
    commentsButton.setAttribute("aria-expanded", String(panelOpen));
  }

  function setCommentCount(tile, number) {
    tile.setAttribute("data-comments", number);
    var badge = tile.querySelector(".gallery-tile__comments");
    if (badge) {
      badge.hidden = !number;
      badge.querySelector("[data-comment-count]").textContent = number;
    }
    if (tile === tiles[current]) showCommentCount(tile);
  }

  function setPanel(open) {
    panelOpen = open;
    panel.hidden = !open;
    viewer.classList.toggle("has-panel", open);
    showCommentCount(tiles[current]);
    fitRotation(img, rotationOf(tiles[current], reverse), true);
    marks.sync();
    if (open) {
      loadComments(tiles[current]);
      panel.focus();
    }
  }

  function showCaption(tile) {
    var text = tile.getAttribute("data-caption") || "";
    caption.textContent = text;
    caption.hidden = !text;
  }

  // Treść z naszego serwera: komentarze i opis są już escapowane w szablonie.
  function fillPanel(tile, response, html) {
    panel.innerHTML = html;
    panelFilled = tile;
    panel.removeAttribute("aria-busy");
    var number = response.headers.get("X-Comment-Count");
    if (number !== null) setCommentCount(tile, Number(number));
    var body = panel.querySelector("[data-photo-panel]");
    if (body) {
      tile.setAttribute("data-caption", body.getAttribute("data-caption"));
      if (tile === tiles[current]) showCaption(tile);
    }
    marks.sync();
  }

  function panelError(text) {
    var note = element("p", "comments__error", text);
    note.setAttribute("role", "alert");
    return note;
  }

  function loadComments(tile) {
    var ticket = ++commentsRequest;
    panelTile = tile;
    panel.setAttribute("aria-busy", "true");
    fetch(tile.getAttribute("data-comments-url"), { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (response) {
        if (!response.ok) throw new Error(response.status);
        return response.text().then(function (html) {
          if (ticket === commentsRequest) fillPanel(tile, response, html);
        });
      })
      .catch(function () {
        if (ticket !== commentsRequest) return;
        panel.removeAttribute("aria-busy");
        panel.replaceChildren(panelError("Nie udało się wczytać opisu i komentarzy. Zamknij panel i otwórz go jeszcze raz."));
      });
  }

  // Komentarz, usunięcie komentarza albo opis: serwer odsyła cały panel na nowo.
  function sendPanelForm(event) {
    var form = event.target;
    event.preventDefault();
    if (form.hasAttribute("data-comment-delete") && !window.confirm("Usunąć ten komentarz?")) return;
    var tile = panelTile;
    var submit = form.querySelector("button[type=submit]");
    if (submit) submit.disabled = true;
    var ticket = ++commentsRequest;
    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: { "X-Requested-With": "fetch", "X-CSRFToken": csrf }
    })
      .then(function (response) {
        // 400 to błąd w formularzu (np. pusty komentarz): serwer odsyła formularz z opisem błędu.
        if (!response.ok && response.status !== 400) throw new Error(response.status);
        return response.text().then(function (html) {
          if (ticket !== commentsRequest) return;
          fillPanel(tile, response, html);
          // Po zapisaniu opisu widać go od góry panelu.
          if (response.status !== 400) {
            if (form.hasAttribute("data-metadata-form") || form.hasAttribute("data-people-form")) panel.scrollTop = 0;
            return;
          }
          var field = panel.querySelector("[aria-invalid=true]") || panel.querySelector("[data-comment-form] textarea");
          if (field) field.focus();
        });
      })
      .catch(function () {
        // Wpisany tekst zostaje w polu, można spróbować jeszcze raz.
        if (submit) submit.disabled = false;
        form.append(panelError("Nie udało się zapisać. Sprawdź połączenie i spróbuj ponownie."));
      });
  }

  function pageUrl(tile, onReverse) {
    return onReverse ? tile.getAttribute("data-reverse-page") : tile.href;
  }

  function preload(index) {
    var tile = tiles[index];
    if (tile) new Image().src = tile.getAttribute("data-preview");
  }

  function show(index, onReverse) {
    closeCollections();
    var tile = tiles[index];
    if (!tile) return;
    onReverse = onReverse && tile.hasAttribute("data-reverse-preview");
    current = index;
    reverse = onReverse;

    var full = tile.getAttribute(onReverse ? "data-reverse-preview" : "data-preview");
    // Najpierw miniatura z pamięci przeglądarki, potem ostrzejszy podgląd, gdy się wczyta.
    img.src = tile.getAttribute(onReverse ? "data-reverse-thumb" : "data-thumb");
    // W wynikach wyszukiwania każde zdjęcie może być z innego albumu.
    var album = tile.getAttribute("data-album-title") || albumTitle;
    title.textContent = album;
    img.alt = (onReverse ? "Rewers zdjęcia " : "Zdjęcie ") + (index + 1) + " z albumu " + album;
    img.classList.add("is-loading");
    fitRotation(img, rotationOf(tile, onReverse));
    var loader = new Image();
    loader.onload = function () {
      if (current === index && reverse === onReverse) {
        img.src = full;
        img.classList.remove("is-loading");
      }
    };
    loader.src = full;

    count.textContent = index + 1 + " / " + tiles.length + (onReverse ? " · rewers" : "");
    flip.hidden = !tile.hasAttribute("data-reverse-preview");
    flip.replaceChildren(element("span", "viewer__flip-verb", "Pokaż "), onReverse ? "awers" : "rewers");
    download.href = tile.getAttribute(onReverse ? "data-reverse-download" : "data-download");
    showCommentCount(tile);
    showFavorite(tile);
    showCaption(tile);
    viewer.classList.toggle("is-reverse", onReverse);
    if (panelOpen && panelTile !== tile) loadComments(tile);
    marks.sync();
    prevButton.disabled = index === 0;
    nextButton.disabled = index === tiles.length - 1;
    if (!viewer.contains(document.activeElement) || document.activeElement.disabled || document.activeElement.hidden) closeButton.focus();
    preload(index + 1);
    preload(index - 1);

    var state = { photo: index, reverse: onReverse };
    if (pushed) history.replaceState(state, "", pageUrl(tile, onReverse));
    else {
      history.pushState(state, "", pageUrl(tile, onReverse));
      pushed = true;
    }
  }

  function open(index, trigger) {
    if (!viewer) build();
    opener = trigger;
    viewer.hidden = false;
    document.body.classList.add("viewer-open");
    guardPageZoom(true);
    show(index, false);
    closeButton.focus();
  }

  // Zamknięcie cofa historię, więc przycisk „wstecz” na telefonie też zamyka podgląd.
  function close() {
    closeCollections();
    if (pushed) history.back();
    else hide();
  }

  function hide() {
    if (!viewer || viewer.hidden) return;
    viewer.hidden = true;
    pushed = false;
    document.body.classList.remove("viewer-open");
    guardPageZoom(false);
    var tile = tiles[current];
    if (tile) {
      tile.scrollIntoView({ block: "nearest" });
      tile.focus();
    } else if (opener) opener.focus();
  }

  function step(direction) {
    var next = current + direction;
    if (next >= 0 && next < tiles.length) show(next, false);
  }

  function onKey(event) {
    if (viewer.hidden || event.altKey || event.ctrlKey || event.metaKey) return;
    if (isTyping(event) && event.key !== "Tab") {
      // Escape w polu komentarza tylko z niego wychodzi, żeby nie zgubić wpisanego tekstu.
      if (event.key === "Escape") {
        event.preventDefault();
        commentsButton.focus();
      }
      return;
    }
    if (event.key === "ArrowLeft") step(-1);
    else if (event.key === "ArrowRight") step(1);
    else if (event.key === "Escape") close();
    else if (event.key === "Tab") trapFocus(event);
    else if (zoomKey(img, event.key)) return;
    else return;
    event.preventDefault();
  }

  function trapFocus(event) {
    var focusable = Array.prototype.filter.call(viewer.querySelectorAll("button, a[href], textarea"), function (node) {
      return !node.disabled && node.getClientRects().length > 0;
    });
    var position = focusable.indexOf(document.activeElement);
    var next = (position + (event.shiftKey ? -1 : 1) + focusable.length) % focusable.length;
    focusable[next].focus();
  }

  window.addEventListener("popstate", function (event) {
    var state = event.state;
    if (state && typeof state.photo === "number") {
      // „Dalej” w przeglądarce po zamknięciu podglądu otwiera go z powrotem.
      if (!viewer) build();
      pushed = true;
      viewer.hidden = false;
      document.body.classList.add("viewer-open");
      show(state.photo, state.reverse);
    } else hide();
  });

  // Tryb zaznaczania: kliknięcie miniatury zaznacza ją zamiast otwierać, pasek na dole pobiera ZIP.
  var selectStart = document.querySelector("[data-select-start]");
  var actions = document.querySelector("[data-gallery-actions]");
  var selectBar = document.querySelector("[data-select-bar]");
  var selectCount = document.querySelector("[data-select-count]");
  var selectDownload = document.querySelector("[data-select-download]");
  var boxes = Array.prototype.slice.call(grid.querySelectorAll(".gallery-select"));
  var selecting = false;

  function refreshSelection() {
    var chosen = boxes.filter(function (box) { return box.checked; }).length;
    selectCount.textContent = "Zaznaczono: " + chosen;
    selectDownload.disabled = chosen === 0;
    boxes.forEach(function (box) { box.parentNode.classList.toggle("is-selected", box.checked); });
  }

  function setSelecting(on) {
    selecting = on;
    grid.classList.toggle("is-selecting", on);
    selectBar.hidden = !on;
    selectStart.hidden = on;
    if (actions) actions.hidden = on;
    document.body.classList.toggle("has-select-bar", on);
    if (!on) boxes.forEach(function (box) { box.checked = false; });
    refreshSelection();
  }

  if (selectStart) {
    selectStart.hidden = false;
    selectStart.addEventListener("click", function () { setSelecting(true); });
    document.querySelector("[data-select-cancel]").addEventListener("click", function () { setSelecting(false); });
    document.querySelector("[data-select-all]").addEventListener("click", function () {
      var all = boxes.every(function (box) { return box.checked; });
      boxes.forEach(function (box) { box.checked = !all; });
      refreshSelection();
    });
    grid.addEventListener("change", refreshSelection);
  }

  grid.addEventListener("click", function (event) {
    var tile = event.target.closest("a[data-preview]");
    if (!tile || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (selecting) {
      var box = tile.parentNode.querySelector(".gallery-select");
      box.checked = !box.checked;
      refreshSelection();
      return;
    }
    open(tiles.indexOf(tile), tile);
  });
})();
