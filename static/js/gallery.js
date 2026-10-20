// Galeria: podgląd zdjęcia na cały ekran nad siatką miniatur.
// Bez JavaScriptu każda miniatura prowadzi do zwykłej strony zdjęcia, więc skrypt jest tylko wygodą.
(function () {
  "use strict";

  var SWIPE_MIN = 50; // px w poziomie, żeby przesunięcie palcem zmieniło zdjęcie
  var ZOOM_MAX = 5;
  var ZOOM_DOUBLE = 2.5; // dwuklik albo dwukrotne stuknięcie
  var TAP_MS = 300;

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
    scale = Math.min(ZOOM_MAX, Math.max(1, scale));
    var px = clientX - (box.left + box.width / 2);
    var py = clientY - (box.top + box.height / 2);
    state.x = px - (px - state.x) * (scale / state.scale);
    state.y = py - (py - state.y) * (scale / state.scale);
    state.scale = scale;
    if (scale === 1) state.x = state.y = 0;
    clampPan(img);
    applyView(img);
  }

  function zoomBy(img, factor) {
    var box = img.parentNode.getBoundingClientRect();
    zoomAt(img, view(img).scale * factor, box.left + box.width / 2, box.top + box.height / 2);
  }

  function toggleZoom(img, clientX, clientY) {
    zoomAt(img, view(img).scale > 1 ? 1 : ZOOM_DOUBLE, clientX, clientY);
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
    stage.addEventListener("dblclick", function (event) { toggleZoom(img, event.clientX, event.clientY); });
    stage.addEventListener("wheel", function (event) {
      event.preventDefault();
      zoomAt(img, view(img).scale * Math.exp(-event.deltaY * 0.002), event.clientX, event.clientY);
    }, { passive: false });
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
      img.style.maxWidth = stage.clientHeight + "px";
      img.style.maxHeight = stage.clientWidth + "px";
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

  // Osobna strona zdjęcia (otwarta z linku): strzałki i gesty prowadzą po linkach.
  var page = document.querySelector("[data-viewer-page]");
  if (page) {
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
    var refit = function (keepZoom) { fitRotation(pageImg, Number(pageImg.getAttribute("data-rotation")), keepZoom); };
    refit();
    window.addEventListener("resize", function () { refit(true); });
    rotateBox.addEventListener("click", function (event) {
      var button = event.target.closest("[data-direction]");
      if (!button) return;
      var before = Number(pageImg.getAttribute("data-rotation"));
      var direction = button.getAttribute("data-direction");
      pageImg.setAttribute("data-rotation", turned(before, direction));
      refit();
      saveRotation(rotateBox.getAttribute("data-rotate-url"), rotateBox.getAttribute("data-csrf"),
        rotateBox.getAttribute("data-side"), direction, function () {
          pageImg.setAttribute("data-rotation", before);
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
  var commentsButton, commentsCount, panel, caption;
  var panelOpen = false;
  var panelTile = null;
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
    commentsButton.title = "Opis i komentarze";
    commentsCount = element("span", "viewer__comments-count");
    commentsButton.append(commentsCount);
    bar.append(closeButton, element("span", "viewer__title", albumTitle), count, rotate, flip, commentsButton, download);

    var stage = element("div", "viewer__stage");
    img = element("img", "viewer__img");
    stage.append(img);
    caption = element("p", "viewer__caption");
    caption.hidden = true;

    prevButton = button("viewer__nav viewer__nav--prev", "‹", "Poprzednie zdjęcie");
    nextButton = button("viewer__nav viewer__nav--next", "›", "Następne zdjęcie");
    panel = element("aside", "viewer__panel");
    panel.setAttribute("aria-label", "Opis i komentarze");
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
    saveRotation(tile.getAttribute("data-rotate-url"), csrf, side ? "rewers" : "awers", direction, function () {
      setRotation(tile, side, before);
    });
  }

  // Komentarze: panel obok zdjęcia (na telefonie od dołu), wczytywany z serwera jako gotowy HTML.
  function commentCount(tile) {
    return Number(tile.getAttribute("data-comments")) || 0;
  }

  function showCommentCount(tile) {
    var number = commentCount(tile);
    commentsCount.textContent = number;
    commentsButton.setAttribute("aria-label", "Opis i komentarze (" + number + ")");
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
    panel.removeAttribute("aria-busy");
    var number = response.headers.get("X-Comment-Count");
    if (number !== null) setCommentCount(tile, Number(number));
    var body = panel.querySelector("[data-photo-panel]");
    if (body) {
      tile.setAttribute("data-caption", body.getAttribute("data-caption"));
      if (tile === tiles[current]) showCaption(tile);
    }
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
            if (form.hasAttribute("data-metadata-form")) panel.scrollTop = 0;
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
    var tile = tiles[index];
    if (!tile) return;
    onReverse = onReverse && tile.hasAttribute("data-reverse-preview");
    current = index;
    reverse = onReverse;

    var full = tile.getAttribute(onReverse ? "data-reverse-preview" : "data-preview");
    // Najpierw miniatura z pamięci przeglądarki, potem ostrzejszy podgląd, gdy się wczyta.
    img.src = tile.getAttribute(onReverse ? "data-reverse-thumb" : "data-thumb");
    img.alt = (onReverse ? "Rewers zdjęcia " : "Zdjęcie ") + (index + 1) + " z albumu " + albumTitle;
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
    showCaption(tile);
    if (panelOpen && panelTile !== tile) loadComments(tile);
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
    show(index, false);
    closeButton.focus();
  }

  // Zamknięcie cofa historię, więc przycisk „wstecz” na telefonie też zamyka podgląd.
  function close() {
    if (pushed) history.back();
    else hide();
  }

  function hide() {
    if (!viewer || viewer.hidden) return;
    viewer.hidden = true;
    pushed = false;
    document.body.classList.remove("viewer-open");
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
