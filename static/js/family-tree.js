// Drzewo rodzinne: kanwa z kafelkami osób, liniami relacji, przesuwaniem, powiększaniem i przeciąganiem.
// Dane i każda zmiana idą przez /drzewo/dane.json i /drzewo/api/…; serwer odpowiada pełnym stanem drzewa.
// Bez JavaScriptu pod kanwą zostaje zwykła lista osób z kartami.
(function () {
  "use strict";

  var root = document.querySelector("[data-family-tree]");
  if (!root) return;

  var NODE_W = 200;
  var NODE_H = 72;
  var GAP_X = 48;
  var ROW_H = 180;
  var ZOOM_MIN = 0.2;
  var ZOOM_MAX = 2.5;
  var MOVE_MIN = 5; // px: mniejszy ruch to kliknięcie, nie przeciąganie
  var SVG_NS = "http://www.w3.org/2000/svg";
  var KINDS = { rodzic: "rodzica", partner: "partnera lub partnerkę", dziecko: "dziecko" };

  var urls = {
    data: root.getAttribute("data-url-data"),
    positions: root.getAttribute("data-url-positions"),
    add: root.getAttribute("data-url-add"),
    relation: root.getAttribute("data-url-relation"),
    remove: root.getAttribute("data-url-remove"),
  };
  var csrf = root.getAttribute("data-csrf");
  var canvas = root.querySelector(".tree-canvas");
  var world = root.querySelector(".tree-world");
  var lines = root.querySelector(".tree-lines");
  var nodesLayer = root.querySelector(".tree-nodes");
  var sheet = root.querySelector(".tree-sheet");
  var outsideList = root.querySelector("[data-outside]");
  var messageBox = root.querySelector(".tree-message");
  var namesList = root.querySelector("#drzewo-osoby");

  var state = { data: null, byId: {}, view: { x: 0, y: 0, scale: 1 }, selected: null, form: null, busy: false };
  var nodeEls = {};

  // --- Serwer ----------------------------------------------------------------

  function request(url, body) {
    var options = body === undefined ? {} : {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(body),
    };
    options.credentials = "same-origin";
    state.busy = true;
    root.classList.add("is-busy");
    return fetch(url, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          var error = new Error(data.error || "Nie udało się zapisać. Odśwież stronę i spróbuj jeszcze raz.");
          error.data = data;
          throw error;
        }
        return data;
      });
    }).finally(function () {
      state.busy = false;
      root.classList.remove("is-busy");
    });
  }

  function send(url, body) {
    return request(url, body).then(apply).catch(function (error) {
      // Imiennicy: formularz sam pyta, o kogo chodzi, więc bez czerwonego komunikatu.
      if (!(error.data && error.data.matches)) showMessage(error.message, true);
      throw error;
    });
  }

  var messageTimer = null;
  function showMessage(text, isError) {
    messageBox.textContent = text;
    messageBox.hidden = false;
    messageBox.classList.toggle("is-error", !!isError);
    clearTimeout(messageTimer);
    messageTimer = setTimeout(function () { messageBox.hidden = true; }, isError ? 6000 : 2500);
  }

  // --- Układ -----------------------------------------------------------------

  function relativesIndex(data) {
    var index = {};
    data.people.forEach(function (p) { index[p.id] = { parents: [], children: [], partners: [] }; });
    data.parents.forEach(function (link) {
      if (index[link[0]] && index[link[1]]) {
        index[link[0]].children.push(link[1]);
        index[link[1]].parents.push(link[0]);
      }
    });
    data.partners.forEach(function (pair) {
      if (index[pair[0]] && index[pair[1]]) {
        index[pair[0]].partners.push(pair[1]);
        index[pair[1]].partners.push(pair[0]);
      }
    });
    return index;
  }

  // Pokolenia w rzędach: dziecko pod rodzicami, para w jednym rzędzie, rodzeństwo obok siebie.
  function autoLayout(data) {
    var rel = relativesIndex(data);
    var gen = {};
    data.people.forEach(function (p) { gen[p.id] = 0; });
    for (var round = 0; round < 60; round++) {
      var changed = false;
      data.parents.forEach(function (link) {
        if (gen[link[1]] !== undefined && gen[link[0]] !== undefined && gen[link[1]] < gen[link[0]] + 1) {
          gen[link[1]] = gen[link[0]] + 1;
          changed = true;
        }
      });
      data.partners.forEach(function (pair) {
        var g = Math.max(gen[pair[0]], gen[pair[1]]);
        if (gen[pair[0]] !== g || gen[pair[1]] !== g) {
          gen[pair[0]] = gen[pair[1]] = g;
          changed = true;
        }
      });
      if (!changed) break;
    }
    var rows = [];
    data.people.forEach(function (p) {
      (rows[gen[p.id]] = rows[gen[p.id]] || []).push(p);
    });
    var pos = {};
    var step = NODE_W + GAP_X;
    rows.forEach(function (row, depth) {
      if (!row) return;
      row.forEach(function (p) {
        var xs = rel[p.id].parents.filter(function (id) { return pos[id]; }).map(function (id) { return pos[id][0]; });
        p._want = xs.length ? xs.reduce(function (a, b) { return a + b; }, 0) / xs.length : null;
      });
      // Osoba bez rodziców w drzewie (np. żona/mąż) staje przy partnerze.
      row.forEach(function (p) {
        if (p._want === null) {
          var partner = rel[p.id].partners.map(function (id) { return state.byId[id] || null; }).filter(function (q) {
            return q && q._want !== null && q._want !== undefined && gen[q.id] === depth;
          })[0];
          p._want = partner ? partner._want + 0.1 : null;
        }
      });
      row.sort(function (a, b) {
        var wa = a._want === null ? Infinity : a._want;
        var wb = b._want === null ? Infinity : b._want;
        if (wa !== wb) return wa - wb;
        return (a.born || 9999) - (b.born || 9999) || a.name.localeCompare(b.name, "pl");
      });
      // Pary obok siebie.
      var ordered = [];
      var placed = {};
      row.forEach(function (p) {
        if (placed[p.id]) return;
        ordered.push(p);
        placed[p.id] = true;
        rel[p.id].partners.forEach(function (id) {
          var q = state.byId[id];
          if (q && !placed[id] && gen[id] === depth) {
            ordered.push(q);
            placed[id] = true;
          }
        });
      });
      // Rodzeństwo (ten sam cel pod rodzicami) i ich partnerzy stają w bloku wyśrodkowanym pod rodzicami.
      var blocks = [];
      ordered.forEach(function (p) {
        var last = blocks[blocks.length - 1];
        var want = p._want === null ? null : Math.round(p._want);
        if (last && want !== null && (last.want === want || Math.abs(p._want - last.want - 0.1) < 0.01 * step)) {
          last.people.push(p);
        } else if (last && want !== null && last.people.some(function (q) { return rel[q.id].partners.indexOf(p.id) >= 0; })) {
          last.people.push(p);
        } else {
          blocks.push({ want: want, people: [p] });
        }
      });
      var x = -Infinity;
      var unanchored = 0;
      blocks.forEach(function (block) {
        var start = block.want === null ? null : block.want - ((block.people.length - 1) * step) / 2;
        block.people.forEach(function (p, i) {
          var want = start === null ? (depth === 0 ? unanchored++ * step : x + step) : start + i * step;
          x = Math.max(want, x + step);
          pos[p.id] = [x, depth * ROW_H];
        });
      });
      // Rząd bez rodziców wyśrodkowany na zero; rzędy niżej zostają pod rodzicami.
      if (depth === 0 && ordered.length) {
        var shift = (pos[ordered[0].id][0] + pos[ordered[ordered.length - 1].id][0]) / 2;
        ordered.forEach(function (p) { pos[p.id][0] -= shift; });
      }
    });
    data.people.forEach(function (p) { delete p._want; });
    return pos;
  }

  function overlaps(x, y, skip) {
    return state.data.people.some(function (p) {
      return p.id !== skip && p.x !== null && Math.abs(p.x - x) < NODE_W + 8 && Math.abs(p.y - y) < NODE_H + 8;
    });
  }

  function freeSpot(x, y, skip) {
    for (var i = 0; i < 200; i++) {
      var dx = (i % 2 ? 1 : -1) * Math.ceil(i / 2) * (NODE_W + GAP_X / 2);
      if (!overlaps(x + dx, y, skip)) return [x + dx, y];
    }
    return [x, y + NODE_H * 2];
  }

  // Nowe osoby (bez miejsca na kanwie) stają przy krewnych: rodzic nad, dziecko pod, partner obok.
  function placeMissing() {
    var missing = state.data.people.filter(function (p) { return p.x === null || p.y === null; });
    if (!missing.length) return {};
    var placedAny = state.data.people.some(function (p) { return p.x !== null; });
    var result = {};
    if (!placedAny) {
      var pos = autoLayout(state.data);
      missing.forEach(function (p) { p.x = pos[p.id][0]; p.y = pos[p.id][1]; result[p.id] = pos[p.id]; });
      return result;
    }
    var rel = relativesIndex(state.data);
    var center = viewCenter();
    for (var pass = 0; pass < 3; pass++) {
      missing.forEach(function (p) {
        if (p.x !== null) return;
        var r = rel[p.id];
        var anchor = null;
        var placedOf = function (ids) {
          return ids.map(function (id) { return state.byId[id]; }).filter(function (q) { return q && q.x !== null; });
        };
        var ps = placedOf(r.parents);
        var cs = placedOf(r.children);
        var partners = placedOf(r.partners);
        if (ps.length) {
          anchor = [ps.reduce(function (s, q) { return s + q.x; }, 0) / ps.length, ps[0].y + ROW_H];
        } else if (partners.length) {
          anchor = [partners[0].x + NODE_W + GAP_X, partners[0].y];
        } else if (cs.length) {
          anchor = [cs[0].x, cs[0].y - ROW_H];
        } else if (pass === 2) {
          anchor = [center[0] - NODE_W / 2, center[1] - NODE_H / 2];
        }
        if (!anchor) return;
        var spot = freeSpot(anchor[0], anchor[1], p.id);
        p.x = spot[0];
        p.y = spot[1];
        result[p.id] = spot;
      });
    }
    return result;
  }

  // --- Rysowanie -------------------------------------------------------------

  function applyView() {
    var v = state.view;
    world.style.transform = "translate(" + v.x + "px," + v.y + "px) scale(" + v.scale + ")";
    canvas.style.backgroundPosition = v.x + "px " + v.y + "px";
    canvas.style.backgroundSize = 24 * v.scale + "px " + 24 * v.scale + "px";
  }

  // Część kanwy, której nie zasłania wysunięta karta osoby (z prawej albo, na telefonie, od dołu).
  function area() {
    var w = canvas.clientWidth, h = canvas.clientHeight;
    if (!sheet.hidden) {
      if (sheet.offsetLeft > w / 3) w = sheet.offsetLeft;
      else h = Math.max(h / 3, sheet.offsetTop);
    }
    return { w: w, h: h };
  }

  function viewCenter() {
    var rect = canvas.getBoundingClientRect(), a = area();
    return toWorld(rect.left + a.w / 2, rect.top + a.h / 2);
  }

  // Płynne przesunięcie widoku (wybór osoby), bez animacji przy przeciąganiu.
  function glide() {
    canvas.classList.add("is-gliding");
    clearTimeout(glide.timer);
    glide.timer = setTimeout(function () { canvas.classList.remove("is-gliding"); }, 320);
  }

  // Wybrana osoba nie może się chować pod kartą ani za krawędzią: przesuwamy widok tylko tyle, ile trzeba.
  function reveal(id) {
    var p = state.byId[id];
    if (!p) return;
    var a = area(), v = state.view, pad = 24;
    var left = v.x + p.x * v.scale, top = v.y + p.y * v.scale;
    var right = left + NODE_W * v.scale, bottom = top + NODE_H * v.scale;
    var dx = 0, dy = 0;
    if (right > a.w - pad) dx = a.w - pad - right;
    if (left + dx < pad) dx = pad - left;
    if (bottom > a.h - pad) dy = a.h - pad - bottom;
    if (top + dy < pad) dy = pad - top;
    if (!dx && !dy) return;
    glide();
    state.view = { scale: v.scale, x: v.x + dx, y: v.y + dy };
    applyView();
  }

  // Kanwa sięga do dołu okna: odejmujemy to, co jest nad nią (nagłówek, wstążka, komunikaty).
  function sizeCanvas() {
    var top = canvas.getBoundingClientRect().top + window.scrollY;
    canvas.style.setProperty("--tree-top", Math.round(top) + "px");
  }

  function toWorld(clientX, clientY) {
    var rect = canvas.getBoundingClientRect();
    var v = state.view;
    return [(clientX - rect.left - v.x) / v.scale, (clientY - rect.top - v.y) / v.scale];
  }

  function fit() {
    var people = state.data.people;
    var rect = area();
    if (!people.length) {
      state.view = { x: rect.w / 2, y: rect.h / 3, scale: 1 };
      applyView();
      return;
    }
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    people.forEach(function (p) {
      minX = Math.min(minX, p.x); minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x + NODE_W); maxY = Math.max(maxY, p.y + NODE_H);
    });
    var pad = 40;
    var scale = Math.min((rect.w - pad * 2) / (maxX - minX), (rect.h - pad * 2) / (maxY - minY), 1);
    scale = Math.max(ZOOM_MIN, scale);
    state.view = {
      scale: scale,
      x: rect.w / 2 - ((minX + maxX) / 2) * scale,
      y: rect.h / 2 - ((minY + maxY) / 2) * scale,
    };
    applyView();
  }

  function focusOn(id) {
    var p = state.byId[id];
    if (!p) return;
    var a = area();
    var scale = Math.max(state.view.scale, 0.8);
    state.view = { scale: scale, x: a.w / 2 - (p.x + NODE_W / 2) * scale, y: a.h / 2 - (p.y + NODE_H / 2) * scale };
    applyView();
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function avatar(person, className) {
    if (person.portrait) {
      var img = el("img", className + " rot-" + person.portrait.turn);
      img.src = person.portrait.url;
      img.alt = "";
      img.draggable = false;
      return img;
    }
    return el("span", className + " " + className + "--empty", person.name.charAt(0));
  }

  function renderNode(person) {
    var node = nodeEls[person.id];
    if (!node) {
      node = el("div", "tree-node");
      node.setAttribute("data-id", person.id);
      node.setAttribute("role", "button");
      node.tabIndex = 0;
      nodeEls[person.id] = node;
      nodesLayer.appendChild(node);
    }
    node.textContent = "";
    node.appendChild(avatar(person, "tree-node__avatar"));
    var text = el("span", "tree-node__text");
    var name = el("strong", "tree-node__name", person.name);
    // Nazwisko rodowe w nawiasie, jaśniejsze, zaraz po nazwisku: „Helena Bereza (Kowalska)”.
    if (person.maiden) {
      name.appendChild(document.createTextNode(" "));
      var maiden = el("span", "tree-node__maiden", "(" + person.maiden + ")");
      maiden.title = "z domu " + person.maiden;
      name.appendChild(maiden);
    }
    text.appendChild(name);
    if (person.years) text.appendChild(el("span", "tree-node__years", person.years));
    node.appendChild(text);
    node.setAttribute("aria-label", person.name + (person.years ? ", " + person.years : ""));
    node.classList.toggle("is-selected", state.selected === person.id);
    if (state.data.canEdit && state.selected === person.id) {
      kindsFor(person.id).forEach(function (kind) {
        var handle = el("button", "tree-handle tree-handle--" + kind, "+");
        handle.type = "button";
        handle.setAttribute("data-kind", kind);
        handle.setAttribute("aria-label", "Dodaj " + KINDS[kind] + ": " + person.name);
        handle.title = "Dodaj " + KINDS[kind] + " (albo przeciągnij na kogoś z drzewa)";
        node.appendChild(handle);
      });
    }
    positionNode(person);
  }

  // Kogo można dodać: rodzica tylko do dwojga.
  function kindsFor(id) {
    var rel = relativesIndex(state.data)[id];
    return ["rodzic", "partner", "dziecko"].filter(function (kind) {
      return kind !== "rodzic" || !rel || rel.parents.length < 2;
    });
  }

  function positionNode(person) {
    nodeEls[person.id].style.transform = "translate(" + person.x + "px," + person.y + "px)";
  }

  function path(d, className) {
    var line = document.createElementNS(SVG_NS, "path");
    line.setAttribute("d", d);
    line.setAttribute("class", className);
    lines.appendChild(line);
  }

  function drawLines() {
    lines.textContent = "";
    var byId = state.byId;
    var partnerOf = {};
    state.data.partners.forEach(function (pair) {
      var a = byId[pair[0]], b = byId[pair[1]];
      if (!a || !b) return;
      partnerOf[pair[0] + "-" + pair[1]] = partnerOf[pair[1] + "-" + pair[0]] = true;
      path("M" + (a.x + NODE_W / 2) + "," + (a.y + NODE_H / 2) + " L" + (b.x + NODE_W / 2) + "," + (b.y + NODE_H / 2), "tree-line tree-line--partner");
    });
    // Dziecko dwojga rodziców: jedna linia od środka pary (rodzice są połączeni linią pary);
    // dziecko jednego rodzica: linia od tego rodzica.
    var parentsOf = {};
    state.data.parents.forEach(function (link) {
      (parentsOf[link[1]] = parentsOf[link[1]] || []).push(link[0]);
    });
    Object.keys(parentsOf).forEach(function (childId) {
      var child = byId[childId];
      if (!child) return;
      var ps = parentsOf[childId].map(function (id) { return byId[id]; }).filter(Boolean);
      var sources = [];
      if (ps.length === 2) {
        if (!partnerOf[ps[0].id + "-" + ps[1].id]) {
          path("M" + (ps[0].x + NODE_W / 2) + "," + (ps[0].y + NODE_H / 2) + " L" + (ps[1].x + NODE_W / 2) + "," + (ps[1].y + NODE_H / 2), "tree-line tree-line--partner");
        }
        sources.push([(ps[0].x + ps[1].x) / 2 + NODE_W / 2, (ps[0].y + ps[1].y) / 2 + NODE_H / 2]);
      } else {
        ps.forEach(function (p) { sources.push([p.x + NODE_W / 2, p.y + NODE_H]); });
      }
      sources.forEach(function (s) {
        var cx = child.x + NODE_W / 2;
        var cy = child.y;
        var mid = s[1] < cy ? Math.max(s[1] + 12, cy - 36) : (s[1] + cy) / 2;
        path("M" + s[0] + "," + s[1] + " V" + mid + " H" + cx + " V" + cy, "tree-line");
      });
    });
  }

  function render() {
    var seen = {};
    state.data.people.forEach(function (p) {
      seen[p.id] = true;
      renderNode(p);
    });
    Object.keys(nodeEls).forEach(function (id) {
      if (!seen[id]) {
        nodeEls[id].remove();
        delete nodeEls[id];
      }
    });
    drawLines();
    root.classList.toggle("is-empty", !state.data.people.length);
  }

  function apply(data) {
    var first = !state.data;
    state.data = data;
    state.byId = {};
    data.people.forEach(function (p) { state.byId[p.id] = p; });
    if (state.selected && !state.byId[state.selected]) state.selected = null;
    var placed = placeMissing();
    render();
    renderSheet();
    if (first) {
      var wanted = parseInt(new URLSearchParams(location.search).get("osoba"), 10);
      if (state.byId[wanted]) {
        state.selected = wanted;
        render();
        focusOn(wanted);
      } else {
        fit();
      }
    }
    renderOutside();
    renderNames();
    if (data.canEdit && Object.keys(placed).length) savePositions(placed);
    return data;
  }

  function savePositions(positions) {
    return request(urls.positions, { positions: positions }).catch(function (error) {
      showMessage(error.message, true);
    });
  }

  function renderNames() {
    if (!namesList) return;
    namesList.textContent = "";
    state.data.names.forEach(function (name) {
      var option = el("option");
      option.value = name;
      namesList.appendChild(option);
    });
  }

  // --- Panel osoby (z boku albo od dołu na telefonie) ------------------------

  function relationRows(person) {
    var rel = relativesIndex(state.data)[person.id];
    var rows = [];
    rel.parents.forEach(function (id) { rows.push(["rodzic", id]); });
    rel.partners.forEach(function (id) { rows.push(["partner", id]); });
    rel.children.forEach(function (id) { rows.push(["dziecko", id]); });
    return rows;
  }

  var LABELS = { rodzic: "rodzic", partner: "partner/ka", dziecko: "dziecko" };

  function renderSheet() {
    sheet.textContent = "";
    var person = state.selected && state.byId[state.selected];
    var editing = state.form && state.data.canEdit;
    sheet.hidden = !person && !editing;
    root.classList.toggle("has-sheet", !sheet.hidden);
    if (sheet.hidden) return;

    var close = el("button", "tree-sheet__close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "Zamknij");
    close.addEventListener("click", function () {
      state.selected = null;
      state.form = null;
      render();
      renderSheet();
    });
    sheet.appendChild(close);

    if (person) {
      var head = el("div", "tree-sheet__head");
      head.appendChild(avatar(person, "tree-avatar"));
      var title = el("div");
      title.appendChild(el("h2", "", person.name));
      var sub = [person.maiden ? "z domu " + person.maiden : "", person.years].filter(Boolean).join(" · ");
      if (sub) title.appendChild(el("p", "hint", sub));
      head.appendChild(title);
      sheet.appendChild(head);
      var card = el("a", "button button--quiet tree-sheet__card", "Karta osoby i zdjęcia");
      card.href = person.url;
      sheet.appendChild(card);

      var rows = relationRows(person);
      if (rows.length) {
        var list = el("ul", "tree-sheet__relatives");
        rows.forEach(function (row) {
          var other = state.byId[row[1]];
          if (!other) return;
          var item = el("li");
          var link = el("button", "link-button", other.name);
          link.type = "button";
          link.addEventListener("click", function () { select(other.id, true); });
          item.appendChild(link);
          item.appendChild(el("span", "hint", " " + LABELS[row[0]]));
          if (state.data.canEdit) {
            var remove = el("button", "icon-button icon-button--small", "×");
            remove.type = "button";
            remove.setAttribute("aria-label", "Usuń połączenie z: " + other.name);
            remove.addEventListener("click", function () {
              if (!window.confirm("Usunąć połączenie: " + person.name + " – " + other.name + "?")) return;
              send(urls.relation, { person: person.id, other: other.id, kind: row[0], remove: true }).then(function () {
                showMessage("Usunięto połączenie.");
              });
            });
            item.appendChild(remove);
          }
          list.appendChild(item);
        });
        sheet.appendChild(list);
      }
    }

    if (!state.data.canEdit) return;

    if (person) {
      var actions = el("div", "tree-sheet__actions");
      kindsFor(person.id).forEach(function (kind) {
        var button = el("button", "button button--quiet", "+ " + { rodzic: "Rodzic", partner: "Partner/ka", dziecko: "Dziecko" }[kind]);
        button.type = "button";
        button.addEventListener("click", function () { openForm(person.id, kind); });
        actions.appendChild(button);
      });
      sheet.appendChild(actions);
    }

    if (editing) sheet.appendChild(buildForm());

    if (person) {
      var removeTree = el("button", "link-button tree-sheet__remove", "Usuń z drzewa");
      removeTree.type = "button";
      removeTree.addEventListener("click", function () {
        if (!window.confirm("Usunąć " + person.name + " z drzewa razem z połączeniami? Oznaczenia na zdjęciach zostaną, a zmianę da się cofnąć.")) return;
        send(urls.remove, { id: person.id }).then(function () {
          state.selected = null;
          renderSheet();
          showMessage("Usunięto z drzewa: " + person.name + ".");
        });
      });
      sheet.appendChild(removeTree);
    }
  }

  function buildForm() {
    var form = el("form", "tree-form");
    var to = state.form.to && state.byId[state.form.to];
    var label = el("label", "", to ? "Dodaj " + KINDS[state.form.kind] + ": " + to.name : "Nowa osoba w drzewie");
    label.setAttribute("for", "drzewo-nowa-osoba");
    form.appendChild(label);
    if (to) {
      var kind = el("select", "tree-form__kind");
      kind.setAttribute("aria-label", "Kim jest ta osoba");
      Object.keys(KINDS).forEach(function (key) {
        var option = el("option", "", { rodzic: "rodzic", partner: "partner / partnerka", dziecko: "dziecko" }[key]);
        option.value = key;
        option.selected = key === state.form.kind;
        kind.appendChild(option);
      });
      kind.addEventListener("change", function () {
        state.form.kind = kind.value;
        renderSheet();
      });
      form.appendChild(kind);
      var rel = relativesIndex(state.data)[to.id] || { parents: [], partners: [] };
      if (state.form.kind === "dziecko" && rel.partners.length) {
        // Dziecko pochodzi od pary: drugim rodzicem jest partner (do wyboru, gdy jest ich kilku).
        var secondLabel = el("label", "tree-form__second", "Drugi rodzic");
        var second = el("select");
        second.setAttribute("data-second", "");
        rel.partners.forEach(function (id) {
          var mate = state.byId[id];
          if (!mate) return;
          var option = el("option", "", mate.name);
          option.value = id;
          second.appendChild(option);
        });
        var none = el("option", "", "nikt z drzewa / nie wiadomo");
        none.value = "";
        second.appendChild(none);
        secondLabel.appendChild(second);
        form.appendChild(secondLabel);
      } else if (state.form.kind === "rodzic" && rel.parents.length === 1 && state.byId[rel.parents[0]]) {
        form.appendChild(el("p", "hint", "Drugi rodzic: razem z " + state.byId[rel.parents[0]].name + " będą parą, a linia do " + to.name + " pójdzie od pary."));
      }
    }
    var input = el("input");
    input.id = "drzewo-nowa-osoba";
    input.type = "text";
    input.maxLength = 100;
    input.required = true;
    input.autocomplete = "off";
    input.setAttribute("list", "drzewo-osoby");
    input.placeholder = "Imię i nazwisko";
    // Zmiana „kim jest” przebudowuje formularz: wpisane imię zostaje.
    input.value = state.form.name || "";
    var choice = null;
    input.addEventListener("input", function () {
      state.form.name = input.value;
      // Inna nazwa: pytanie o imienników przestaje dotyczyć wpisanej osoby.
      if (state.form.matches) {
        state.form.matches = null;
        if (choice) choice.remove();
        submit.hidden = false;
      }
    });
    form.appendChild(input);
    form.appendChild(el("p", "hint", "Nowa osoba albo ktoś, kto już jest w archiwum (podpowiedzi)."));
    var row = el("div", "tree-form__buttons");
    var submit = el("button", "button", "Dodaj");
    submit.type = "submit";
    if (state.form.matches) {
      choice = namesakeChoice(state.form.matches, function (extra) { save(extra); });
      form.appendChild(choice);
      submit.hidden = true;
    }
    var cancel = el("button", "button button--quiet", "Anuluj");
    cancel.type = "button";
    cancel.addEventListener("click", function () {
      state.form = null;
      renderSheet();
    });
    row.appendChild(submit);
    row.appendChild(cancel);
    form.appendChild(row);
    // ``extra``: ``{id}`` (to ta osoba z archiwum) albo ``{new: true}`` (imiennik) po pytaniu o imienników.
    function save(extra) {
      var name = input.value.trim();
      if (!name || state.busy) return;
      var body = extra && extra.id ? { id: extra.id } : { name: name };
      if (extra && extra.new) body.new = true;
      var spot = state.form.at;
      if (spot) { body.x = spot[0]; body.y = spot[1]; }
      if (to) body.relation = { to: to.id, kind: state.form.kind };
      var secondChoice = form.querySelector("[data-second]");
      if (to && secondChoice) body.relation.second = secondChoice.value ? Number(secondChoice.value) : null;
      send(urls.add, body).then(function (data) {
        state.form = null;
        if (!to && data.added) state.selected = data.added;
        render();
        renderSheet();
        if (state.selected) reveal(state.selected);
        showMessage("Dodano: " + name + ".");
      }).catch(function (error) {
        if (!(error.data && error.data.matches)) return;
        state.form.name = name;
        state.form.matches = error.data.matches;
        renderSheet();
      });
    }
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      save(null);
    });
    if (!choice) setTimeout(function () { input.focus(); }, 0);
    return form;
  }

  // „W archiwum jest już Jan Bereza”: wybór istniejącej osoby albo nowego imiennika.
  function namesakeChoice(matches, pick) {
    var box = el("div", "tree-namesakes");
    box.setAttribute("role", "group");
    var lead = el("p", "tree-namesakes__lead", "W archiwum jest już „" + matches[0].name + "”. Kogo dodajesz?");
    lead.id = "drzewo-imiennicy";
    box.setAttribute("aria-labelledby", lead.id);
    box.appendChild(lead);
    matches.forEach(function (match) {
      var button = el("button", "tree-namesake");
      button.type = "button";
      button.appendChild(el("strong", "", "Tę osobę: " + match.name));
      button.appendChild(el("span", "tree-namesake__facts", match.facts));
      button.addEventListener("click", function () { pick({ id: match.id }); });
      box.appendChild(button);
    });
    var fresh = el("button", "tree-namesake tree-namesake--new");
    fresh.type = "button";
    fresh.appendChild(el("strong", "", "Inną osobę o tym samym imieniu i nazwisku"));
    fresh.appendChild(el("span", "tree-namesake__facts", "Powstanie nowa osoba. Dopisz jej lata życia, żeby łatwo było je odróżnić."));
    fresh.addEventListener("click", function () { pick({ new: true }); });
    box.appendChild(fresh);
    setTimeout(function () {
      box.querySelector("button").focus({ preventScroll: true });
      box.scrollIntoView({ block: "nearest" });
    }, 0);
    return box;
  }

  function openForm(personId, kind, at) {
    state.form = { to: personId, kind: kind, at: at || null };
    if (personId) state.selected = personId;
    render();
    renderSheet();
    if (personId) reveal(personId);
  }

  function select(id, center) {
    state.selected = id;
    state.form = null;
    render();
    renderSheet();
    if (center) { glide(); focusOn(id); } else reveal(id);
  }

  // --- Osoby ze zdjęć spoza drzewa -------------------------------------------

  function renderOutside() {
    if (!outsideList) return;
    outsideList.textContent = "";
    var box = outsideList.closest(".tree-outside");
    box.hidden = !state.data.canEdit || !state.data.outside.length;
    state.data.outside.forEach(function (person) {
      var item = el("li");
      var button = el("button", "chip tree-outside__item", person.name + " ");
      button.type = "button";
      button.appendChild(el("span", "chip__count", String(person.count)));
      button.setAttribute("data-id", person.id);
      button.title = "Przeciągnij na drzewo albo kliknij, żeby dodać";
      item.appendChild(button);
      outsideList.appendChild(item);
    });
  }

  function addOutside(id, at) {
    var spot = at ? freeSpot(at[0] - NODE_W / 2, at[1] - NODE_H / 2) : null;
    var center = viewCenter();
    spot = spot || freeSpot(center[0] - NODE_W / 2, center[1] - NODE_H / 2);
    send(urls.add, { id: id, x: spot[0], y: spot[1] }).then(function () {
      select(id, !at);
      showMessage("Dodano do drzewa: " + state.byId[id].name + ".");
    });
  }

  if (outsideList) {
    outsideList.addEventListener("pointerdown", function (event) {
      var button = event.target.closest(".tree-outside__item");
      if (!button || event.button > 0) return;
      event.preventDefault();
      var id = parseInt(button.getAttribute("data-id"), 10);
      var start = [event.clientX, event.clientY];
      var ghost = null;
      function move(e) {
        if (!ghost && Math.hypot(e.clientX - start[0], e.clientY - start[1]) > MOVE_MIN) {
          ghost = el("div", "tree-ghost", button.firstChild.textContent);
          document.body.appendChild(ghost);
        }
        if (ghost) ghost.style.transform = "translate(" + (e.clientX - 20) + "px," + (e.clientY - 20) + "px)";
      }
      function up(e) {
        document.removeEventListener("pointermove", move);
        document.removeEventListener("pointerup", up);
        document.removeEventListener("pointercancel", up);
        if (ghost) {
          ghost.remove();
          var rect = canvas.getBoundingClientRect();
          var inside = e.type === "pointerup" && e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom;
          if (inside) addOutside(id, toWorld(e.clientX, e.clientY));
        } else if (e.type === "pointerup") {
          addOutside(id, null);
        }
      }
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", up);
      document.addEventListener("pointercancel", up);
    });
  }

  // --- Przesuwanie, powiększanie, przeciąganie -------------------------------

  var pointers = {};
  var gesture = null;

  function zoomAt(clientX, clientY, factor) {
    var v = state.view;
    var scale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, v.scale * factor));
    var rect = canvas.getBoundingClientRect();
    var px = clientX - rect.left;
    var py = clientY - rect.top;
    v.x = px - ((px - v.x) * scale) / v.scale;
    v.y = py - ((py - v.y) * scale) / v.scale;
    v.scale = scale;
    applyView();
  }

  function nodeAt(clientX, clientY) {
    var hit = document.elementFromPoint(clientX, clientY);
    var node = hit && hit.closest && hit.closest(".tree-node");
    return node && canvas.contains(node) ? parseInt(node.getAttribute("data-id"), 10) : null;
  }

  canvas.addEventListener("pointerdown", function (event) {
    if (event.button > 0) return;
    pointers[event.pointerId] = [event.clientX, event.clientY];
    var ids = Object.keys(pointers);
    if (ids.length === 2) {
      // Dwa palce: powiększanie; przerywa przeciąganie.
      if (gesture && gesture.type === "node") positionNode(gesture.person);
      var a = pointers[ids[0]], b = pointers[ids[1]];
      gesture = { type: "pinch", dist: Math.hypot(a[0] - b[0], a[1] - b[1]) };
      lines.textContent = "";
      drawLines();
      return;
    }
    if (ids.length > 2) return;
    var handle = event.target.closest(".tree-handle");
    var node = event.target.closest(".tree-node");
    if (handle && node) {
      gesture = { type: "link", from: parseInt(node.getAttribute("data-id"), 10), kind: handle.getAttribute("data-kind"), start: [event.clientX, event.clientY], moved: false };
    } else if (node) {
      var person = state.byId[parseInt(node.getAttribute("data-id"), 10)];
      gesture = { type: "node", person: person, start: [event.clientX, event.clientY], origin: [person.x, person.y], moved: false };
    } else {
      gesture = { type: "pan", start: [event.clientX, event.clientY], origin: [state.view.x, state.view.y], moved: false };
    }
    canvas.setPointerCapture(event.pointerId);
  });

  canvas.addEventListener("pointermove", function (event) {
    if (!pointers[event.pointerId]) return;
    pointers[event.pointerId] = [event.clientX, event.clientY];
    if (!gesture) return;
    if (gesture.type === "pinch") {
      var ids = Object.keys(pointers);
      if (ids.length < 2) return;
      var a = pointers[ids[0]], b = pointers[ids[1]];
      var dist = Math.hypot(a[0] - b[0], a[1] - b[1]);
      if (gesture.dist > 0) zoomAt((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, dist / gesture.dist);
      gesture.dist = dist;
      return;
    }
    var dx = event.clientX - gesture.start[0];
    var dy = event.clientY - gesture.start[1];
    if (!gesture.moved && Math.hypot(dx, dy) < MOVE_MIN) return;
    gesture.moved = true;
    if (gesture.type === "pan") {
      state.view.x = gesture.origin[0] + dx;
      state.view.y = gesture.origin[1] + dy;
      applyView();
    } else if (gesture.type === "node" && state.data.canEdit) {
      gesture.person.x = gesture.origin[0] + dx / state.view.scale;
      gesture.person.y = gesture.origin[1] + dy / state.view.scale;
      positionNode(gesture.person);
      nodeEls[gesture.person.id].classList.add("is-dragging");
      drawLines();
    } else if (gesture.type === "link") {
      drawLines();
      var from = state.byId[gesture.from];
      var to = toWorld(event.clientX, event.clientY);
      path("M" + (from.x + NODE_W / 2) + "," + (from.y + NODE_H / 2) + " L" + to[0] + "," + to[1], "tree-line tree-line--draft");
      var target = nodeAt(event.clientX, event.clientY);
      Object.keys(nodeEls).forEach(function (id) {
        nodeEls[id].classList.toggle("is-target", parseInt(id, 10) === target && target !== gesture.from);
      });
    }
  });

  function endGesture(event) {
    if (!pointers[event.pointerId]) return;
    delete pointers[event.pointerId];
    var g = gesture;
    if (!g) return;
    if (g.type === "pinch") {
      if (!Object.keys(pointers).length) gesture = null;
      return;
    }
    gesture = null;
    if (event.type === "pointercancel") {
      if (g.type === "node") {
        g.person.x = g.origin[0];
        g.person.y = g.origin[1];
        render();
      }
      return;
    }
    if (g.type === "pan") {
      if (!g.moved) {
        state.selected = null;
        if (state.form && state.form.to) state.form = null;
        render();
        renderSheet();
      }
    } else if (g.type === "node") {
      nodeEls[g.person.id].classList.remove("is-dragging");
      if (!g.moved || !state.data.canEdit) {
        select(g.person.id, false);
      } else {
        var positions = {};
        positions[g.person.id] = [g.person.x, g.person.y];
        savePositions(positions);
      }
    } else if (g.type === "link") {
      Object.keys(nodeEls).forEach(function (id) { nodeEls[id].classList.remove("is-target"); });
      drawLines();
      var target = g.moved ? nodeAt(event.clientX, event.clientY) : null;
      if (target && target !== g.from) {
        var source = state.byId[g.from];
        var other = state.byId[target];
        send(urls.relation, { person: g.from, other: target, kind: g.kind }).then(function () {
          showMessage({ rodzic: other.name + " jest rodzicem: " + source.name, partner: "Para: " + source.name + " i " + other.name, dziecko: other.name + " jest dzieckiem: " + source.name }[g.kind] + ".");
        });
      } else {
        var at = g.moved ? toWorld(event.clientX, event.clientY) : null;
        openForm(g.from, g.kind, at ? [at[0] - NODE_W / 2, at[1] - NODE_H / 2] : null);
      }
    }
  }

  canvas.addEventListener("pointerup", endGesture);
  canvas.addEventListener("pointercancel", endGesture);

  // Kółko myszy powiększa; touchpad (płynne przesunięcia) przesuwa, a rozsunięcie palców (ctrl) powiększa.
  canvas.addEventListener("wheel", function (event) {
    event.preventDefault();
    var smooth = event.deltaMode === 0 && (event.deltaX !== 0 || event.deltaY % 1 !== 0 || Math.abs(event.deltaY) < 40);
    if (smooth && !event.ctrlKey) {
      state.view.x -= event.deltaX;
      state.view.y -= event.deltaY;
      applyView();
      return;
    }
    var amount = event.deltaMode === 1 ? event.deltaY * 33 : event.deltaY;
    zoomAt(event.clientX, event.clientY, Math.exp(-amount * (event.ctrlKey ? 0.01 : 0.002)));
  }, { passive: false });

  // Klawiatura: Enter na kafelku otwiera panel osoby.
  canvas.addEventListener("keydown", function (event) {
    var node = event.target.closest && event.target.closest(".tree-node");
    if (node && (event.key === "Enter" || event.key === " ") && !event.target.closest(".tree-handle")) {
      event.preventDefault();
      select(parseInt(node.getAttribute("data-id"), 10), false);
    }
  });
  canvas.addEventListener("click", function (event) {
    // Klawiatura na uchwycie „+” (bez przeciągania): formularz nowej osoby.
    var handle = event.target.closest(".tree-handle");
    if (handle && event.detail === 0) {
      var node = handle.closest(".tree-node");
      openForm(parseInt(node.getAttribute("data-id"), 10), handle.getAttribute("data-kind"));
    }
  });

  // --- Przyciski nad kanwą ---------------------------------------------------

  root.addEventListener("click", function (event) {
    var action = event.target.closest("[data-tree-action]");
    if (!action) return;
    var name = action.getAttribute("data-tree-action");
    var rect = canvas.getBoundingClientRect(), a = area();
    if (name === "zoom-in") zoomAt(rect.left + a.w / 2, rect.top + a.h / 2, 1.25);
    if (name === "zoom-out") zoomAt(rect.left + a.w / 2, rect.top + a.h / 2, 0.8);
    if (name === "fit") fit();
    if (name === "add") {
      state.selected = null;
      openForm(null, null, null);
      // Środek tej części kanwy, której nie zasłoni karta z formularzem.
      var center = viewCenter();
      state.form.at = freeSpot(center[0] - NODE_W / 2, center[1] - NODE_H / 2);
    }
    if (name === "layout") {
      if (!window.confirm("Ułożyć całe drzewo od nowa? Kafelki staną w rzędach według pokoleń, a Twoje ręczne ustawienie zniknie.")) return;
      var pos = autoLayout(state.data);
      state.data.people.forEach(function (p) { p.x = pos[p.id][0]; p.y = pos[p.id][1]; });
      render();
      fit();
      savePositions(pos).then(function () { showMessage("Ułożono drzewo."); });
    }
  });

  // Esc chowa wysuniętą kartę osoby.
  root.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" || sheet.hidden || event.defaultPrevented) return;
    state.selected = null;
    state.form = null;
    render();
    renderSheet();
    canvas.focus();
  });

  window.addEventListener("resize", function () { sizeCanvas(); if (state.data) applyView(); });
  sizeCanvas();

  request(urls.data).then(function (data) {
    root.classList.add("is-ready");
    apply(data);
  }).catch(function (error) {
    showMessage(error.message, true);
  });
})();
