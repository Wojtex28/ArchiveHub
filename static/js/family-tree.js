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
  var BIRTH_WEIGHT = 3; // kara za rodzeństwo nie po kolei urodzenia (zob. autoLayout)
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
    alive: root.getAttribute("data-url-alive"),
    couple: root.getAttribute("data-url-couple"),
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
  var bandsLayer = root.querySelector(".tree-bands");
  // Podpisy pasów leżą nad kafelkami i liniami (pas jest pod nimi), więc linia ich nie przekreśla.
  var bandLabels = null;
  if (bandsLayer) {
    bandLabels = document.createElement("div");
    bandLabels.className = "tree-band-labels";
    bandLabels.setAttribute("aria-hidden", "true");
    canvas.insertBefore(bandLabels, world.nextSibling);
  }
  var timeline = root.querySelector(".tree-timeline");

  var state = {
    data: null, byId: {}, view: { x: 0, y: 0, scale: 1 }, selected: null, form: null, busy: false,
    gen: {}, bands: [], mode: "drzewo", tl: { px: null },
  };
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

  // Związki (ETAP 31): kolejność wg roku ślubu, bez roku w kolejności dodania; rozwód.
  function coupleKey(a, b) { return a < b ? a + "-" + b : b + "-" + a; }
  function couplesIndex(data) {
    var info = {};
    (data.partners || []).forEach(function (pair, i) { info[coupleKey(pair[0], pair[1])] = { order: i, year: null, since: "", ended: false }; });
    (data.couples || []).forEach(function (c) {
      var item = info[coupleKey(c.a, c.b)];
      if (item) { item.year = c.year; item.since = c.since; item.ended = c.ended; }
    });
    return info;
  }
  // Partnerzy osoby od pierwszego związku.
  function partnersInOrder(id, rel, couples) {
    return rel[id].partners.slice().sort(function (a, b) {
      var x = couples[coupleKey(id, a)] || {}, y = couples[coupleKey(id, b)] || {};
      var xy = x.year === null || x.year === undefined ? Infinity : x.year;
      var yy = y.year === null || y.year === undefined ? Infinity : y.year;
      return xy - yy || (x.order || 0) - (y.order || 0);
    });
  }

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

  // Pokolenia w rzędach: dziecko pod rodzicami, para obok siebie, rodzeństwo obok siebie.
  // Kolejność w rzędach dobieramy tak, żeby linie rodzin przecinały się jak najrzadziej:
  // najpierw metoda średnich (osoba pod środkiem rodziców, rodzice nad środkiem dzieci) w kilku
  // przejściach w dół i w górę, potem zamiany sąsiadów i odwracanie par, dopóki ubywa przecięć.
  // Dwie rodziny w tym samym odstępie między rzędami: ile razy ich linie się przetną, gdy szyna
  // rodziny ``high`` leży wyżej niż szyna ``low``. Linie dzieci wyższej szyny schodzą przez niższą,
  // a linia od rodziców niższej szyny przechodzi przez wyższą. Rodzina: {sx, kids, l, r}.
  function costAbove(high, low) {
    var n = 0;
    high.kids.forEach(function (x) { if (x > low.l && x < low.r) n++; });
    if (low.sx > high.l && low.sx < high.r) n++;
    return n;
  }

  function overlapping(a, b) {
    return a.l < b.r && b.l < a.r;
  }

  // Kolejność torów dla grupy zachodzących na siebie rodzin: od najniższej szyny (tuż nad dziećmi) w górę.
  // Do 6 rodzin sprawdzamy wszystkie kolejności, przy większej grupie wystarcza kolejność od lewej.
  function laneOrder(group) {
    if (group.length > 6) return group.slice().sort(function (a, b) { return a.l - b.l || a.r - b.r; });
    var best = null, bestCost = Infinity;
    (function permute(done, rest) {
      if (!rest.length) {
        var cost = 0;
        for (var i = 0; i < done.length; i++) {
          for (var j = i + 1; j < done.length; j++) {
            if (overlapping(done[i], done[j])) cost += costAbove(done[j], done[i]);
          }
        }
        if (cost < bestCost) { bestCost = cost; best = done; }
        return;
      }
      rest.forEach(function (f, i) { permute(done.concat([f]), rest.slice(0, i).concat(rest.slice(i + 1))); });
    })([], group);
    return best;
  }

  function generations(data) {
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
        if (gen[pair[0]] === undefined || gen[pair[1]] === undefined) return;
        var g = Math.max(gen[pair[0]], gen[pair[1]]);
        if (gen[pair[0]] !== g || gen[pair[1]] !== g) {
          gen[pair[0]] = gen[pair[1]] = g;
          changed = true;
        }
      });
      if (!changed) break;
    }
    alignByBirth(data, gen);
    return gen;
  }

  // Osobne gałęzie (jeszcze niepołączone z resztą drzewa) i pojedyncze osoby trafiają do rzędu
  // swoich rówieśników według dat urodzenia, zamiast zawsze do górnego rzędu (ETAP 30).
  var YEARS_PER_GENERATION = 25;
  function alignByBirth(data, gen) {
    var rel = relativesIndex(data);
    var component = {}, groups = [];
    data.people.forEach(function (p) {
      if (component[p.id] !== undefined) return;
      var members = [], queue = [p.id];
      component[p.id] = groups.length;
      while (queue.length) {
        var id = queue.shift();
        members.push(id);
        var r = rel[id];
        r.parents.concat(r.children, r.partners).forEach(function (q) {
          if (component[q] === undefined) { component[q] = groups.length; queue.push(q); }
        });
      }
      groups.push(members);
    });
    if (groups.length < 2) return;
    var born = {};
    data.people.forEach(function (p) { if (p.born !== null && p.born !== undefined) born[p.id] = p.born; });
    // „Rok zerowego pokolenia” gałęzi: średnia z (rok urodzenia − pokolenie × 25 lat).
    function base(members) {
      var known = members.filter(function (id) { return born[id] !== undefined; });
      if (!known.length) return null;
      return known.reduce(function (sum, id) { return sum + born[id] - gen[id] * YEARS_PER_GENERATION; }, 0) / known.length;
    }
    // Wzorem jest największa gałąź z datami.
    var main = null;
    groups.forEach(function (members) {
      if (base(members) !== null && (!main || members.length > main.length)) main = members;
    });
    if (!main) return;
    var mainBase = base(main);
    groups.forEach(function (members) {
      if (members === main) return;
      var b = base(members);
      if (b === null) return;
      var shift = Math.round((b - mainBase) / YEARS_PER_GENERATION);
      members.forEach(function (id) { gen[id] += shift; });
    });
    var low = Infinity;
    data.people.forEach(function (p) { low = Math.min(low, gen[p.id]); });
    if (low !== 0 && isFinite(low)) data.people.forEach(function (p) { gen[p.id] -= low; });
  }

  function autoLayout(data) {
    var rel = relativesIndex(data);
    var gen = generations(data);
    var byId = {};
    data.people.forEach(function (p) { byId[p.id] = p; });
    var depthCount = 0;
    data.people.forEach(function (p) { depthCount = Math.max(depthCount, gen[p.id] + 1); });

    // Jednostka = osoba z partnerami z tego samego pokolenia (zawsze obok siebie).
    var rows = [];
    for (var d = 0; d < depthCount; d++) rows.push([]);
    var seen = {};
    var people = data.people.slice().sort(function (a, b) {
      return (a.born || 9999) - (b.born || 9999) || a.name.localeCompare(b.name, "pl") || a.id - b.id;
    });
    var couples = couplesIndex(data);
    people.forEach(function (p) {
      if (seen[p.id]) return;
      var members = [], queue = [p.id];
      seen[p.id] = true;
      while (queue.length) {
        var id = queue.shift();
        members.push(id);
        rel[id].partners.forEach(function (q) {
          if (!seen[q] && gen[q] === gen[id]) { seen[q] = true; queue.push(q); }
        });
      }
      rows[gen[p.id]].push(arrangeUnit(members));
    });

    // Osoba z kilkoma partnerami stoi w środku: 1. związek po lewej, 2. po prawej (kolejne na zmianę
    // dalej od środka). Łańcuch par (A+B, B+C, C+D) stoi po kolei. Takiej jednostki nie odwracamy.
    function arrangeUnit(members) {
      if (members.length < 3) return members;
      var inUnit = {};
      members.forEach(function (id) { inUnit[id] = true; });
      var mates = {};
      members.forEach(function (id) {
        mates[id] = partnersInOrder(id, rel, couples).filter(function (q) { return inUnit[q] && gen[q] === gen[id]; });
      });
      var hub = members.slice().sort(function (a, b) { return mates[b].length - mates[a].length; })[0];
      var edges = members.reduce(function (n, id) { return n + mates[id].length; }, 0) / 2;
      var isPath = edges === members.length - 1 && members.every(function (id) { return mates[id].length <= 2; });
      var order;
      if (isPath) {
        var start = members.filter(function (id) { return mates[id].length === 1; })[0];
        order = [start];
        var prev = null, cur = start;
        while (order.length < members.length) {
          var next = mates[cur].filter(function (q) { return q !== prev; })[0];
          if (next === undefined) break;
          order.push(next);
          prev = cur;
          cur = next;
        }
        // Pierwszy związek osoby w środku ma być po lewej.
        var at = order.indexOf(hub);
        if (at > 0 && at < order.length - 1 && mates[hub][0] !== order[at - 1]) order.reverse();
      } else {
        var left = [], right = [];
        mates[hub].forEach(function (q, i) { if (i % 2) right.push(q); else left.unshift(q); });
        order = left.concat([hub], right);
      }
      members.forEach(function (id) { if (order.indexOf(id) < 0) order.push(id); });
      return order;
    }

    // Krawędzie rodzic → dziecko między sąsiednimi rzędami: źródło to środek pary albo jeden rodzic.
    var familiesOf = {};
    data.people.forEach(function (p) {
      var ps = rel[p.id].parents.filter(function (id) { return gen[id] === gen[p.id] - 1; });
      if (!ps.length) return;
      familiesOf[p.id] = ps.length === 2 && rel[ps[0]].partners.indexOf(ps[1]) >= 0 ? [ps] : ps.map(function (id) { return [id]; });
    });

    // Numer miejsca osoby w rzędzie (po kolei przez jednostki); wystarczy do liczenia przecięć.
    function indexOf(order) {
      var idx = {}, pos = 0;
      order.forEach(function (unit) { unit.forEach(function (id) { idx[id] = pos++; }); });
      return idx;
    }

    function source(family, idx) {
      var sum = 0;
      family.forEach(function (id) { sum += idx[id]; });
      return sum / family.length;
    }

    function crossingsBetween(upper, lower) {
      var up = indexOf(upper), low = indexOf(lower), fams = {};
      lower.forEach(function (unit) {
        unit.forEach(function (id) {
          (familiesOf[id] || []).forEach(function (family) {
            if (up[family[0]] === undefined) return;
            var key = family.join("+");
            var f = fams[key] || (fams[key] = { sx: source(family, up), kids: [] });
            f.kids.push(low[id]);
          });
        });
      });
      var list = Object.keys(fams).map(function (k) {
        var f = fams[k];
        f.l = Math.min.apply(null, f.kids.concat([f.sx]));
        f.r = Math.max.apply(null, f.kids.concat([f.sx]));
        return f;
      });
      var n = 0;
      for (var i = 0; i < list.length; i++) {
        for (var j = i + 1; j < list.length; j++) {
          if (!overlapping(list[i], list[j])) continue;
          // Lepsza z dwóch kolejności szyn, plus drobna kara za samo zachodzenie (czytelniej obok siebie).
          n += Math.min(costAbove(list[i], list[j]), costAbove(list[j], list[i])) + 0.01;
        }
      }
      return n;
    }

    // Rodzeństwo od najstarszego z lewej (ETAP 30): każda para rodzeństwa w złej kolejności to kara
    // BIRTH_WEIGHT, więc data urodzenia wygrywa z pojedynczym przecięciem linii, ale nie z kilkoma.
    // Rodzeństwo bez daty urodzenia nie ma kary i może stać gdziekolwiek.
    function bornOf(id) { return byId[id].born === null || byId[id].born === undefined ? null : byId[id].born; }
    function familyKeyIn(id, up) {
      var f = (familiesOf[id] || []).filter(function (family) { return up[family[0]] !== undefined; });
      return f.map(function (family) { return family.join("+"); });
    }
    function inversions(upper, lower) {
      var up = indexOf(upper), groups = {}, n = 0;
      lower.forEach(function (unit) {
        unit.forEach(function (id) {
          if (bornOf(id) === null) return;
          familyKeyIn(id, up).forEach(function (key) { (groups[key] = groups[key] || []).push(bornOf(id)); });
        });
      });
      Object.keys(groups).forEach(function (key) {
        var born = groups[key];
        for (var i = 0; i < born.length; i++) {
          for (var j = i + 1; j < born.length; j++) if (born[i] > born[j]) n++;
        }
      });
      return n;
    }

    function total(orders) {
      var n = 0;
      for (var d = 1; d < orders.length; d++) {
        n += crossingsBetween(orders[d - 1], orders[d]) + BIRTH_WEIGHT * inversions(orders[d - 1], orders[d]);
      }
      return n;
    }

    function sortBy(order, keyOf) {
      var keyed = order.map(function (unit, i) { var k = keyOf(unit); return { unit: unit, k: k === null ? i : k, i: i }; });
      keyed.sort(function (a, b) { return a.k - b.k || a.i - b.i; });
      return keyed.map(function (e) { return e.unit; });
    }

    function average(values) {
      return values.length ? values.reduce(function (a, b) { return a + b; }, 0) / values.length : null;
    }

    // W parze pierwszy stoi ten, którego rodzina jest bardziej po lewej (wtedy linie się nie krzyżują).
    function orderMembers(unit, keyOfPerson) {
      if (unit.length !== 2) return unit;
      var keyed = unit.map(function (id, i) { var k = keyOfPerson(id); return { id: id, k: k, i: i }; });
      var known = keyed.filter(function (e) { return e.k !== null; });
      if (!known.length) return unit;
      var mean = average(known.map(function (e) { return e.k; }));
      keyed.forEach(function (e) { if (e.k === null) e.k = mean; });
      keyed.sort(function (a, b) { return a.k - b.k || a.i - b.i; });
      return keyed.map(function (e) { return e.id; });
    }

    var orders = rows.map(function (row) { return row.slice(); });
    function down(d) {
      var up = indexOf(orders[d - 1]);
      function personKey(id) {
        var keys = (familiesOf[id] || []).filter(function (f) { return up[f[0]] !== undefined; }).map(function (f) { return source(f, up); });
        return average(keys);
      }
      orders[d] = sortBy(orders[d].map(function (unit) { return orderMembers(unit, personKey); }), function (unit) {
        return average(unit.map(personKey).filter(function (k) { return k !== null; }));
      });
    }
    function upward(d) {
      var low = indexOf(orders[d + 1]);
      var kids = {};
      orders[d + 1].forEach(function (unit) {
        unit.forEach(function (id) {
          (familiesOf[id] || []).forEach(function (family) {
            family.forEach(function (parent) { (kids[parent] = kids[parent] || []).push(low[id]); });
          });
        });
      });
      function personKey(id) { return average(kids[id] || []); }
      orders[d] = sortBy(orders[d].map(function (unit) { return orderMembers(unit, personKey); }), function (unit) {
        return average(unit.map(personKey).filter(function (k) { return k !== null; }));
      });
    }

    var best = orders.map(function (o) { return o.slice(); });
    var bestScore = total(orders);
    for (var iter = 0; iter < 8 && bestScore > 0; iter++) {
      for (d = 1; d < orders.length; d++) down(d);
      var score = total(orders);
      if (score < bestScore) { bestScore = score; best = orders.map(function (o) { return o.slice(); }); }
      for (d = orders.length - 2; d >= 0; d--) upward(d);
      for (d = 1; d < orders.length; d++) down(d);
      score = total(orders);
      if (score < bestScore) { bestScore = score; best = orders.map(function (o) { return o.slice(); }); }
    }
    orders = best;

    // Rodzeństwo jednej rodziny może stać przemieszane z innymi osobami, więc zamiana sąsiadów nie
    // wystarczy: tu rodzeństwo zamienia się miejscami między sobą, od najstarszego z lewej.
    function birthOrderPass() {
      var improved = false;
      for (var d = 1; d < orders.length; d++) {
        var row = orders[d];
        var up = indexOf(orders[d - 1]);
        var keys = {};
        row.forEach(function (unit, i) {
          unit.forEach(function (id) {
            if (bornOf(id) === null) return;
            familyKeyIn(id, up).forEach(function (key) { (keys[key] = keys[key] || []).push({ i: i, born: bornOf(id) }); });
          });
        });
        Object.keys(keys).forEach(function (key) {
          var entries = keys[key];
          var slots = entries.map(function (e) { return e.i; });
          if (entries.length < 2 || slots.some(function (i, k) { return slots.indexOf(i) !== k; })) return;
          slots.sort(function (a, b) { return a - b; });
          var sorted = entries.slice().sort(function (a, b) { return a.born - b.born || a.i - b.i; });
          var before = row.slice();
          var units = sorted.map(function (e) { return before[e.i]; });
          slots.forEach(function (slot, k) { row[slot] = units[k]; });
          var now = total(orders);
          if (now < bestScore) { bestScore = now; improved = true; }
          else { for (var k = 0; k < row.length; k++) row[k] = before[k]; }
        });
      }
      return improved;
    }

    // Poprawki lokalne: zamiana sąsiednich jednostek i odwrócenie par, dopóki ubywa przecięć.
    for (var round = 0; round < 20 && bestScore > 0; round++) {
      var improved = birthOrderPass();
      for (d = 0; d < orders.length; d++) {
        var row = orders[d];
        for (var i = 0; i < row.length; i++) {
          var tries = [];
          if (i + 1 < row.length) tries.push(function () { var t = row[i]; row[i] = row[i + 1]; row[i + 1] = t; });
          if (row[i].length === 2) tries.push(function () { row[i] = row[i].slice().reverse(); });
          for (var t = 0; t < tries.length; t++) {
            var before = row.slice();
            tries[t]();
            var now = total(orders);
            if (now < bestScore) { bestScore = now; improved = true; }
            else { for (var k = 0; k < row.length; k++) row[k] = before[k]; }
          }
        }
      }
      if (!improved) break;
    }

    // Partner bez rodziców w drzewie staje po tej stronie, gdzie nie ma rodzeństwa jego partnera,
    // żeby linia rodzeństwa nie biegła pod jego kafelkiem.
    orders.forEach(function (order, d) {
      if (!d) return;
      var up = indexOf(orders[d - 1]);
      var keyOf = function (id) {
        var f = (familiesOf[id] || []).filter(function (family) { return up[family[0]] !== undefined; })[0];
        return f ? f.join("+") : null;
      };
      order.forEach(function (unit, i) {
        if (unit.length !== 2) return;
        var rooted = unit.filter(function (id) { return keyOf(id) !== null; });
        if (rooted.length !== 1) return;
        var key = keyOf(rooted[0]), left = 0, right = 0;
        order.forEach(function (other, j) {
          if (j === i) return;
          if (other.some(function (id) { return keyOf(id) === key; })) { if (j < i) left++; else right++; }
        });
        var others = unit.filter(function (id) { return id !== rooted[0]; });
        order[i] = left >= right ? [rooted[0]].concat(others) : others.concat([rooted[0]]);
      });
    });

    // Współrzędne: rodzeństwo z partnerami w bloku wyśrodkowanym pod rodzicami, bez nachodzenia.
    var pos = {};
    var step = NODE_W + GAP_X;
    orders.forEach(function (order, depth) {
      var flat = [];
      order.forEach(function (unit) { unit.forEach(function (id) { flat.push(id); }); });
      var wants = flat.map(function (id) {
        var xs = (familiesOf[id] || []).map(function (family) {
          var known = family.filter(function (pid) { return pos[pid]; });
          return known.length ? average(known.map(function (pid) { return pos[pid][0]; })) : null;
        }).filter(function (x) { return x !== null; });
        return average(xs);
      });
      // Bloki: kolejne osoby z tym samym celem (rodzeństwo) albo partnerzy kogoś z bloku.
      var blocks = [];
      flat.forEach(function (id, i) {
        var last = blocks[blocks.length - 1];
        var want = wants[i];
        var partnerOfLast = last && last.ids.some(function (q) { return rel[q].partners.indexOf(id) >= 0; });
        if (last && (partnerOfLast || (want !== null && last.want !== null && Math.abs(want - last.want) < 1))) {
          last.ids.push(id);
          if (last.want === null) last.want = want;
        } else {
          blocks.push({ want: want, ids: [id] });
        }
      });
      var x = -Infinity;
      blocks.forEach(function (block) {
        var start = block.want === null ? x + step : block.want - ((block.ids.length - 1) * step) / 2;
        block.ids.forEach(function (id, i) {
          x = Math.max(start + i * step, x + step);
          if (!isFinite(x)) x = 0;
          pos[id] = [x, depth * ROW_H];
        });
      });
      if (depth === 0 && flat.length) {
        var shift = (pos[flat[0]][0] + pos[flat[flat.length - 1]][0]) / 2;
        flat.forEach(function (id) { pos[id][0] -= shift; });
      }
    });
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
    positionBands();
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
    var stage = canvas.parentNode;
    var top = stage.getBoundingClientRect().top + window.scrollY;
    stage.style.setProperty("--tree-top", Math.round(top) + "px");
  }

  function toWorld(clientX, clientY) {
    var rect = canvas.getBoundingClientRect();
    var v = state.view;
    return [(clientX - rect.left - v.x) / v.scale, (clientY - rect.top - v.y) / v.scale];
  }

  function fit() {
    // Kanwa schowana (oś czasu): dopasujemy widok, gdy wróci.
    if (canvas.hidden) { state.needFit = true; return; }
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
    if (canvas.hidden) { state.needFit = true; return; }
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
    // Osoba zmarła: lata z † (serwer, Person.life) i przygaszony kafelek (ETAP 30).
    if (person.years) text.appendChild(el("span", "tree-node__years", person.years));
    node.appendChild(text);
    node.classList.toggle("tree-node--deceased", !!person.deceased);
    node.setAttribute("aria-label", person.name + (person.deceased ? ", nie żyje" : "") + (person.years ? ", " + person.years : ""));
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

  function label(x, y, text, className) {
    var node = document.createElementNS(SVG_NS, "text");
    node.setAttribute("x", x);
    node.setAttribute("y", y);
    node.setAttribute("class", className);
    node.textContent = text;
    lines.appendChild(node);
  }

  // Linia pary (ETAP 31): ciągła, a po rozwodzie przerywana. Gdy między partnerami stoi ktoś inny,
  // linia przechodzi łukiem nad jego kafelkiem. Przy osobie z kilkoma partnerami opis „1. ślub 1950”.
  function drawCouple(a, b, info, rel, couples) {
    var left = a.x <= b.x ? a : b, right = left === a ? b : a;
    var ax = left.x + NODE_W / 2, bx = right.x + NODE_W / 2;
    var ay = left.y + NODE_H / 2, by = right.y + NODE_H / 2;
    var blocked = Math.abs(a.y - b.y) < 1 && state.data.people.some(function (p) {
      return p !== a && p !== b && Math.abs(p.y - a.y) < NODE_H && p.x > left.x + 1 && p.x < right.x - 1;
    });
    var cls = "tree-line tree-line--partner" + (info.ended ? " tree-line--ended" : "");
    if (blocked) {
      var top = Math.min(left.y, right.y) - 26;
      path("M" + ax + "," + left.y + " C" + ax + "," + top + " " + bx + "," + top + " " + bx + "," + right.y, cls);
    } else if (Math.abs(a.y - b.y) < 1 && right.x - left.x >= NODE_W) {
      path("M" + (left.x + NODE_W) + "," + ay + " L" + right.x + "," + by, cls);
    } else {
      path("M" + ax + "," + ay + " L" + bx + "," + by, cls);
    }
    var hub = [a, b].filter(function (p) { return rel[p.id] && rel[p.id].partners.length > 1; })[0];
    var parts = [];
    if (hub) {
      var other = hub === a ? b : a;
      parts.push(partnersInOrder(hub.id, rel, couples).indexOf(other.id) + 1 + ".");
    }
    if (info.since) parts.push("ślub " + info.since);
    if (info.ended) parts.push((parts.length > 1 || info.since ? "· " : "") + "rozwód");
    if (parts.length) {
      var y = blocked ? Math.min(left.y, right.y) - 24 : Math.min(left.y, right.y) - 8;
      label((ax + bx) / 2, y, parts.join(" "), "tree-couple-label" + (info.ended ? " tree-couple-label--ended" : ""));
    }
  }

  function drawLines() {
    lines.textContent = "";
    var byId = state.byId;
    var partnerOf = {};
    var couples = couplesIndex(state.data);
    var rel = relativesIndex(state.data);
    state.data.partners.forEach(function (pair) {
      var a = byId[pair[0]], b = byId[pair[1]];
      if (!a || !b) return;
      partnerOf[pair[0] + "-" + pair[1]] = partnerOf[pair[1] + "-" + pair[0]] = true;
      drawCouple(a, b, couples[coupleKey(a.id, b.id)] || {}, rel, couples);
    });
    // Rodzina = rodzice (para albo jedna osoba) i ich dzieci w jednym rzędzie. Każda rodzina ma własną
    // poziomą „szynę” od rodziców nad dzieci; szyny różnych rodzin w tym samym odstępie między rzędami
    // leżą na różnych wysokościach, żeby się nie zlewały i było widać, czyje jest które dziecko.
    var parentsOf = {};
    state.data.parents.forEach(function (link) {
      (parentsOf[link[1]] = parentsOf[link[1]] || []).push(link[0]);
    });
    var families = {};
    Object.keys(parentsOf).forEach(function (childId) {
      var child = byId[childId];
      if (!child) return;
      var ps = parentsOf[childId].map(function (id) { return byId[id]; }).filter(Boolean);
      if (!ps.length) return;
      var sources = [];
      if (ps.length === 2) {
        if (!partnerOf[ps[0].id + "-" + ps[1].id]) {
          path("M" + (ps[0].x + NODE_W / 2) + "," + (ps[0].y + NODE_H / 2) + " L" + (ps[1].x + NODE_W / 2) + "," + (ps[1].y + NODE_H / 2), "tree-line tree-line--partner");
        }
        sources.push({ key: [ps[0].id, ps[1].id].sort().join("+"), x: (ps[0].x + ps[1].x) / 2 + NODE_W / 2, y: (ps[0].y + ps[1].y) / 2 + NODE_H / 2 });
      } else {
        ps.forEach(function (p) { sources.push({ key: String(p.id), x: p.x + NODE_W / 2, y: p.y + NODE_H }); });
      }
      sources.forEach(function (src) {
        var key = src.key + "|" + Math.round(child.y);
        var family = families[key] || (families[key] = { x: src.x, y: src.y, top: child.y, kids: [] });
        family.top = Math.min(family.top, child.y);
        family.kids.push(child);
      });
    });
    // Szyny zachodzące na siebie w tym samym odstępie dostają osobne „tory” (wysokości), w kolejności,
    // przy której ich linie przecinają się najrzadziej.
    var list = Object.keys(families).map(function (key) {
      var f = families[key];
      var xs = f.kids.map(function (k) { return k.x + NODE_W / 2; });
      f.kidXs = xs;
      f.l = Math.min.apply(null, xs.concat([f.x]));
      f.r = Math.max.apply(null, xs.concat([f.x]));
      f.left = f.l;
      f.right = f.r;
      f.gap = Math.round(f.top / 20);
      return f;
    }).sort(function (a, b) { return a.l - b.l || a.r - b.r; });
    var lanes = {};
    var byGap = {};
    list.forEach(function (f) { (byGap[f.gap] = byGap[f.gap] || []).push(f); });
    Object.keys(byGap).forEach(function (gap) {
      var fams = byGap[gap];
      var groups = [];
      fams.forEach(function (f) {
        var last = groups[groups.length - 1];
        if (last && last.some(function (g) { return overlapping(g, f); })) last.push(f);
        else groups.push([f]);
      });
      var count = 0;
      groups.forEach(function (group) {
        var geometry = group.map(function (f) { return { f: f, sx: f.x, kids: f.kidXs, l: f.l, r: f.r }; });
        laneOrder(geometry).forEach(function (g, lane) { g.f.lane = lane; g.f.group = group.length; });
        count = Math.max(count, group.length);
      });
      lanes[gap] = { length: count };
    });
    var colorIndex = {};
    list.forEach(function (f) {
      var count = lanes[f.gap].length;
      // Gdy szyny w odstępie zachodzą na siebie, każda rodzina ma swój kolor (stonowany, z tej samej palety).
      var cls = "tree-line";
      if (f.group > 1) {
        colorIndex[f.gap] = (colorIndex[f.gap] || 0) + 1;
        cls += " tree-line--f" + ((colorIndex[f.gap] - 1) % 5);
      }
      var room = f.top - f.y;
      var bus;
      if (room > 40) {
        // Tory od dołu odstępu w górę, co 14 px, ale zawsze poniżej rodziców.
        var spacing = Math.min(22, (room - 30) / Math.max(count, 1));
        bus = Math.max(f.y + 12, f.top - 24 - f.lane * spacing);
      } else {
        bus = (f.y + f.top) / 2;
      }
      path("M" + f.x + "," + f.y + " V" + bus, cls);
      if (f.right > f.left) path("M" + f.left + "," + bus + " H" + f.right, cls);
      f.kids.forEach(function (k) {
        var kx = k.x + NODE_W / 2;
        path("M" + kx + "," + bus + " V" + k.y, cls);
        // Kropka w miejscu odejścia dziecka od szyny: widać, że linia nie przechodzi „przez” rodzinę.
        dot(kx, bus, cls);
      });
      dot(f.x, bus, cls);
    });
    drawBands();
  }

  function dot(x, y, cls) {
    var c = document.createElementNS(SVG_NS, "circle");
    c.setAttribute("cx", x);
    c.setAttribute("cy", y);
    c.setAttribute("r", 3);
    c.setAttribute("class", cls.split("tree-line").join("tree-joint"));
    lines.appendChild(c);
  }


  // --- Pasy pokoleń (ETAP 32) --------------------------------------------------
  // Za kafelkami leżą poziome pasy, po jednym na pokolenie, z podpisem przy lewej krawędzi.
  // Pokolenie liczy generations() (to samo co „Ułóż automatycznie”), a pas obejmuje kafelki
  // tego pokolenia tam, gdzie akurat stoją, więc działa też przy ręcznym ułożeniu.
  var BAND_PAD = 44;
  var GEN_COLORS = 6;
  var RELATIVE = {
    "-4": "Pokolenie prapradziadków", "-3": "Pokolenie pradziadków", "-2": "Pokolenie dziadków",
    "-1": "Pokolenie rodziców", "1": "Pokolenie dzieci", "2": "Pokolenie wnuków",
    "3": "Pokolenie prawnuków", "4": "Pokolenie praprawnuków",
  };

  function yearsRange(ids) {
    var years = ids.map(function (id) { return state.byId[id].born; })
      .filter(function (y) { return y !== null && y !== undefined; });
    if (!years.length) return "";
    var lo = Math.min.apply(null, years), hi = Math.max.apply(null, years);
    return lo === hi ? "ur. " + lo : "ur. " + lo + "–" + hi;
  }

  var RELATIVE_SHORT = {
    "-4": "Prapradziadkowie", "-3": "Pradziadkowie", "-2": "Dziadkowie", "-1": "Rodzice",
    "1": "Dzieci", "2": "Wnuki", "3": "Prawnuki", "4": "Praprawnuki",
  };

  // Pełny podpis i krótki (gdy drzewo jest mocno pomniejszone, np. na telefonie).
  function bandLabel(g, low) {
    var sel = state.selected && state.byId[state.selected];
    if (sel && state.gen[sel.id] !== undefined) {
      var d = g - state.gen[sel.id];
      if (d === 0) return ["Pokolenie: " + sel.name, sel.name.split(" ")[0]];
      if (RELATIVE[d]) return [RELATIVE[d], RELATIVE_SHORT[d]];
      var far = d < 0 ? (-d) + " pokoleń wstecz" : d + " pokoleń dalej";
      return [far, (d < 0 ? "−" : "+") + Math.abs(d)];
    }
    return [(g - low + 1) + ". pokolenie", "Pok. " + (g - low + 1)];
  }

  function genClass(g) { return "gen-c" + (((g % GEN_COLORS) + GEN_COLORS) % GEN_COLORS); }

  function drawBands() {
    if (!bandsLayer) return;
    var rows = {};
    state.data.people.forEach(function (p) {
      var g = state.gen[p.id];
      if (g === undefined || p.x === null) return;
      var r = rows[g] = rows[g] || { gen: g, ids: [], top: Infinity, bottom: -Infinity, centers: [] };
      r.ids.push(p.id);
      r.top = Math.min(r.top, p.y);
      r.bottom = Math.max(r.bottom, p.y + NODE_H);
      r.centers.push(p.y + NODE_H / 2);
    });
    var list = Object.keys(rows).map(function (g) {
      var r = rows[g];
      r.centers.sort(function (a, b) { return a - b; });
      r.center = r.centers[Math.floor(r.centers.length / 2)];
      return r;
    });
    bandsLayer.textContent = "";
    bandLabels.textContent = "";
    state.bands = [];
    if (list.length < 2) return;
    list.sort(function (a, b) { return a.center - b.center; });
    var low = Math.min.apply(null, list.map(function (r) { return r.gen; }));
    list.forEach(function (r, i) {
      var prev = list[i - 1], next = list[i + 1];
      // Granica między pasami: w połowie przerwy między rzędami (albo między ich środkami, gdy
      // ktoś przestawił kafelki tak, że rzędy na siebie zachodzą).
      var top = !prev ? r.top - BAND_PAD : (prev.bottom <= r.top ? (prev.bottom + r.top) / 2 : (prev.center + r.center) / 2);
      var bottom = !next ? r.bottom + BAND_PAD : (r.bottom <= next.top ? (r.bottom + next.top) / 2 : (r.center + next.center) / 2);
      var band = el("div", "tree-band " + genClass(r.gen) + (i % 2 ? " tree-band--odd" : ""));
      var text = el("span", "tree-band__label " + genClass(r.gen));
      text.appendChild(el("span", "tree-band__dot"));
      var names = bandLabel(r.gen, low);
      text.appendChild(el("span", "tree-band__name", names[0]));
      text.appendChild(el("span", "tree-band__short", names[1]));
      var years = yearsRange(r.ids);
      if (years) text.appendChild(el("span", "tree-band__years", years));
      bandLabels.appendChild(text);
      bandsLayer.appendChild(band);
      state.bands.push({ el: band, label: text, top: top, bottom: bottom });
    });
    positionBands();
  }

  function positionBands() {
    var v = state.view;
    var h = canvas.clientHeight;
    bandLabels.classList.toggle("is-small", v.scale < 0.55);
    state.bands.forEach(function (b) {
      var top = v.y + b.top * v.scale, bottom = v.y + b.bottom * v.scale;
      b.el.style.top = top + "px";
      b.el.style.height = Math.max(0, bottom - top) + "px";
      // Podpis zostaje na ekranie, dopóki widać choć kawałek pasa.
      // Przy mocnym pomniejszeniu odstęp nad kafelkami jest mały: podpis przylega do górnej krawędzi pasa.
      var edge = v.scale < 0.55 ? 1 : 4;
      var inside = Math.min(Math.max(0, -top) + edge, Math.max(edge, bottom - top - 22));
      b.label.style.transform = "translateY(" + (top + inside) + "px)";
      b.el.hidden = b.label.hidden = bottom < 0 || top > h;
    });
  }

  // --- Oś czasu (ETAP 32) --------------------------------------------------------
  // Drugi tryb widoku: każda osoba to pasek od roku urodzenia do roku śmierci, ułożone według
  // dat urodzenia. Kropki na pasku: ślub (kółko), urodzenie dziecka (mała kropka).
  var TL_ROW = 36;
  var TL_MAX_AGE = 105; // starszych bez „nie żyje” nie rysujemy do dziś, tylko z rozmytym końcem
  var NOW = new Date().getFullYear();

  function tlNameWidth() { return timeline.clientWidth < 520 ? 136 : 220; }

  function tlRows() {
    var rel = relativesIndex(state.data);
    var couples = couplesIndex(state.data);
    var rows = [], undated = [];
    state.data.people.forEach(function (p) {
      var born = p.born, died = p.died;
      if (born == null && died == null) { undated.push(p); return; }
      var marks = [];
      rel[p.id].partners.forEach(function (q) {
        var c = couples[coupleKey(p.id, q)];
        if (c && c.year) marks.push({ year: c.year, kind: c.ended ? "ended" : "marriage", text: "Ślub: " + state.byId[q].name + " (" + c.since + ")" + (c.ended ? ", potem rozwód" : "") });
      });
      rel[p.id].children.forEach(function (q) {
        var child = state.byId[q];
        if (child && child.born != null) marks.push({ year: child.born, kind: "child", text: "Urodzenie dziecka: " + child.name + " (" + child.born + ")" });
      });
      var start = born != null ? born : null, end = died != null ? died : null, open = false;
      if (end === null && start !== null && !p.deceased && NOW - start <= TL_MAX_AGE) { end = NOW; open = true; }
      rows.push({ p: p, start: start, end: end, open: open, marks: marks, sort: born != null ? born : died - 60 });
    });
    rows.sort(function (a, b) { return a.sort - b.sort || a.p.name.localeCompare(b.p.name, "pl"); });
    undated.sort(function (a, b) { return a.name.localeCompare(b.name, "pl"); });
    return { rows: rows, undated: undated };
  }

  function renderTimeline() {
    if (!timeline || state.mode !== "os" || !state.data) return;
    var keep = { left: timeline.scrollLeft, top: timeline.scrollTop };
    var focusName = document.activeElement && document.activeElement.closest && document.activeElement.closest(".tl-row") && document.activeElement.closest(".tl-row").getAttribute("data-id");
    timeline.textContent = "";
    var data = tlRows();
    if (!data.rows.length) {
      timeline.appendChild(el("p", "tl-empty", state.data.people.length
        ? "Nikt w drzewie nie ma jeszcze wpisanego roku urodzenia ani śmierci. Uzupełnij daty w karcie osoby, a pojawi się tutaj."
        : "Drzewo jest puste."));
    } else {
      var lo = Infinity, hi = -Infinity;
      data.rows.forEach(function (r) {
        [r.start, r.end].concat(r.marks.map(function (m) { return m.year; })).forEach(function (y) {
          if (y !== null) { lo = Math.min(lo, y); hi = Math.max(hi, y); }
        });
      });
      lo = Math.floor((lo - 5) / 10) * 10;
      hi = Math.ceil((hi + 5) / 10) * 10;
      var nameW = tlNameWidth();
      var fitPx = (timeline.clientWidth - nameW - 24) / (hi - lo);
      var px = state.tl.px || Math.min(24, Math.max(2.5, fitPx));
      state.tl.lastPx = px;
      var step = px * 10 >= 44 ? 10 : px * 20 >= 44 ? 20 : 50;
      var trackW = Math.ceil((hi - lo) * px) + 16;
      var sheetEl = el("div", "tl");
      sheetEl.style.width = nameW + trackW + "px";
      sheetEl.style.setProperty("--tl-name", nameW + "px");
      sheetEl.style.setProperty("--tl-step", step * px + "px");

      var head = el("div", "tl-head");
      head.appendChild(el("div", "tl-name tl-name--head", data.rows.length + " os."));
      var axis = el("div", "tl-track tl-axis");
      for (var y = lo; y <= hi; y += step) {
        var tick = el("span", "tl-tick", String(y));
        tick.style.left = (y - lo) * px + "px";
        axis.appendChild(tick);
      }
      head.appendChild(axis);
      sheetEl.appendChild(head);

      data.rows.forEach(function (r) {
        var p = r.p;
        var row = el("div", "tl-row" + (state.selected === p.id ? " is-selected" : "") + (p.deceased ? " is-deceased" : ""));
        row.setAttribute("data-id", p.id);
        var name = el("button", "tl-name");
        name.type = "button";
        name.appendChild(el("span", "tl-name__text", p.name));
        if (p.years) name.appendChild(el("span", "tl-name__years", p.years));
        name.title = p.name + (p.years ? ", " + p.years : "");
        row.appendChild(name);
        var track = el("div", "tl-track");
        var g = state.gen[p.id];
        var s = r.start !== null ? r.start : r.end - 30, e = r.end !== null ? r.end : r.start + 30;
        var bar = el("span", "tl-bar " + genClass(g === undefined ? 0 : g)
          + (r.start === null ? " tl-bar--fade-start" : "") + (r.end === null ? " tl-bar--fade-end" : "") + (r.open ? " tl-bar--open" : ""));
        bar.style.left = (s - lo) * px + "px";
        bar.style.width = Math.max(4, (e - s) * px) + "px";
        bar.title = p.name + (r.start === null ? ": rok urodzenia nieznany" : "") + (r.end === null ? ": rok śmierci nieznany" : "") + (r.open ? ": żyje" : "");
        track.appendChild(bar);
        r.marks.forEach(function (m) {
          var mark = el("span", "tl-mark tl-mark--" + m.kind);
          mark.style.left = (m.year - lo) * px + "px";
          mark.title = m.text;
          track.appendChild(mark);
        });
        row.appendChild(track);
        sheetEl.appendChild(row);
      });
      timeline.appendChild(sheetEl);
    }
    if (data.undated.length) {
      var rest = el("div", "tl-undated");
      // Lista zostaje pod osią, nawet gdy oś jest przewinięta w bok.
      rest.style.width = timeline.clientWidth + "px";
      rest.appendChild(el("h2", "", "Bez dat (" + data.undated.length + ")"));
      rest.appendChild(el("p", "hint", "Te osoby nie mają wpisanego roku urodzenia ani śmierci, więc nie ma ich na osi."));
      var list = el("ul", "chips chips--light");
      data.undated.forEach(function (p) {
        var li = el("li", "tl-row");
        li.setAttribute("data-id", p.id);
        var b = el("button", "chip" + (state.selected === p.id ? " is-selected" : ""), p.name);
        b.type = "button";
        li.appendChild(b);
        list.appendChild(li);
      });
      rest.appendChild(list);
      timeline.appendChild(rest);
    }
    timeline.scrollLeft = keep.left;
    timeline.scrollTop = keep.top;
    if (focusName) {
      var again = timeline.querySelector('.tl-row[data-id="' + focusName + '"] button');
      if (again) again.focus({ preventScroll: true });
    }
  }

  // Wybrany wiersz osi nie może się chować pod kartą osoby (na telefonie karta wysuwa się od dołu).
  function revealRow(id) {
    var row = timeline.querySelector('.tl-row[data-id="' + id + '"]');
    if (!row || !row.offsetParent || !row.closest(".tl")) return;
    var limit = timeline.clientHeight;
    if (!sheet.hidden && sheet.offsetLeft < timeline.clientWidth / 3) limit = Math.min(limit, sheet.offsetTop - timeline.offsetTop);
    var y = row.offsetTop - timeline.scrollTop;
    if (y < 40 || y + TL_ROW > limit - 8) timeline.scrollTop = Math.max(0, row.offsetTop - Math.max(40, (limit - TL_ROW) / 2));
  }

  function zoomTimeline(factor) {
    var px = state.tl.lastPx || 4;
    var nameW = tlNameWidth();
    // Rok na środku widoku zostaje na środku.
    var middle = (timeline.scrollLeft + (timeline.clientWidth - nameW) / 2) / px;
    state.tl.px = Math.min(40, Math.max(1.5, px * factor));
    renderTimeline();
    timeline.scrollLeft = Math.max(0, middle * state.tl.px - (timeline.clientWidth - nameW) / 2);
  }

  function setMode(mode, remember) {
    state.mode = mode === "os" ? "os" : "drzewo";
    var isTimeline = state.mode === "os";
    root.classList.toggle("is-timeline", isTimeline);
    canvas.hidden = isTimeline;
    if (timeline) timeline.hidden = !isTimeline;
    root.querySelectorAll("[data-tree-mode]").forEach(function (b) {
      var on = b.getAttribute("data-tree-mode") === state.mode;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (remember) {
      var params = new URLSearchParams(location.search);
      if (isTimeline) params.set("widok", "os"); else params.delete("widok");
      var query = params.toString();
      history.replaceState(null, "", location.pathname + (query ? "?" + query : ""));
    }
    if (!state.data) return;
    if (isTimeline) {
      renderTimeline();
      var row = state.selected && timeline.querySelector('.tl-row[data-id="' + state.selected + '"]');
      // Tylko oś przewija się do wybranej osoby, strona zostaje na miejscu.
      if (row && row.offsetParent) timeline.scrollTop = Math.max(0, row.offsetTop - timeline.clientHeight / 2);
    } else {
      sizeCanvas();
      if (state.needFit) {
        state.needFit = false;
        if (state.selected) focusOn(state.selected); else fit();
      } else {
        applyView();
        if (state.selected) reveal(state.selected);
      }
    }
  }

  if (timeline) {
    timeline.addEventListener("click", function (event) {
      var row = event.target.closest(".tl-row");
      if (!row) return;
      var id = parseInt(row.getAttribute("data-id"), 10);
      if (state.selected === id && !sheet.hidden) return;
      select(id, false);
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
    renderTimeline();
    root.classList.toggle("is-empty", !state.data.people.length);
  }

  function apply(data) {
    var first = !state.data;
    state.data = data;
    state.byId = {};
    data.people.forEach(function (p) { state.byId[p.id] = p; });
    state.gen = generations(data);
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
    var index = relativesIndex(state.data);
    var rel = index[person.id];
    var rows = [];
    rel.parents.forEach(function (id) { rows.push(["rodzic", id]); });
    partnersInOrder(person.id, index, couplesIndex(state.data)).forEach(function (id) { rows.push(["partner", id]); });
    rel.children.forEach(function (id) { rows.push(["dziecko", id]); });
    return rows;
  }

  var LABELS = { rodzic: "rodzic", partner: "partner/ka", dziecko: "dziecko" };

  // Opis związku w panelu bocznym: „1. związek · ślub 1950 · rozwód”.
  function coupleInfo(id, otherId) {
    var index = relativesIndex(state.data);
    var couples = couplesIndex(state.data);
    var item = couples[coupleKey(id, otherId)] || {};
    var parts = [];
    if (index[id].partners.length > 1) parts.push(partnersInOrder(id, index, couples).indexOf(otherId) + 1 + ". związek");
    if (item.since) parts.push("ślub " + item.since);
    if (item.ended) parts.push("rozwód");
    return { text: parts.join(" · "), since: item.since || "", ended: !!item.ended };
  }

  function coupleForm(person, other, info) {
    var form = el("form", "tree-couple");
    var since = el("input");
    since.type = "text";
    since.value = info.since;
    since.placeholder = "np. 1950";
    since.maxLength = 60;
    since.id = "slub-" + other.id;
    var sinceLabel = el("label", "", "Rok ślubu");
    sinceLabel.htmlFor = since.id;
    var ended = el("label", "check");
    var box = el("input");
    box.type = "checkbox";
    box.checked = info.ended;
    ended.appendChild(box);
    ended.appendChild(document.createTextNode(" Rozwód lub rozstanie"));
    var save = el("button", "button button--quiet", "Zapisz");
    save.type = "submit";
    [sinceLabel, since, ended, save].forEach(function (node) { form.appendChild(node); });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      send(urls.couple, { person: person.id, other: other.id, since: since.value, ended: box.checked }).then(function () {
        state.coupleEdit = null;
        renderSheet();
        showMessage("Zapisano: " + person.name + " i " + other.name + ".");
      }).catch(function () {});
    });
    return form;
  }

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
      if (state.data.canEdit) {
        // Przełącznik „Żyje / Nie żyje”: widać go od razu na kafelku (†).
        var alive = el("label", "check tree-sheet__alive");
        var box = el("input");
        box.type = "checkbox";
        box.checked = !!person.deceased;
        box.addEventListener("change", function () {
          send(urls.alive, { id: person.id, deceased: box.checked }).then(function () {
            showMessage(person.name + (box.checked ? ": nie żyje." : ": żyje."));
          }).catch(function () { box.checked = !box.checked; });
        });
        alive.appendChild(box);
        alive.appendChild(document.createTextNode(" Nie żyje †"));
        sheet.appendChild(alive);
      }
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
          var info = row[0] === "partner" ? coupleInfo(person.id, other.id) : null;
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
          if (info) {
            if (info.text) item.appendChild(el("span", "hint tree-sheet__couple", info.text));
            if (state.data.canEdit) {
              var edit = el("button", "link-button tree-sheet__couple-edit", state.coupleEdit === other.id ? "Zwiń" : "Ślub, rozwód");
              edit.type = "button";
              edit.addEventListener("click", function () {
                state.coupleEdit = state.coupleEdit === other.id ? null : other.id;
                renderSheet();
              });
              item.appendChild(edit);
              if (state.coupleEdit === other.id) item.appendChild(coupleForm(person, other, info));
            }
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
    state.coupleEdit = null;
    render();
    renderSheet();
    if (state.mode === "os") { revealRow(id); return; }
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
    var modeButton = event.target.closest("[data-tree-mode]");
    if (modeButton) { setMode(modeButton.getAttribute("data-tree-mode"), true); return; }
    var action = event.target.closest("[data-tree-action]");
    if (!action) return;
    var name = action.getAttribute("data-tree-action");
    if (state.mode === "os" && /^(zoom-in|zoom-out|fit)$/.test(name)) {
      if (name === "fit") { state.tl.px = null; renderTimeline(); } else zoomTimeline(name === "zoom-in" ? 1.25 : 0.8);
      return;
    }
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

  window.addEventListener("resize", function () {
    sizeCanvas();
    if (!state.data) return;
    if (state.mode === "os") renderTimeline(); else applyView();
  });
  sizeCanvas();
  setMode(new URLSearchParams(location.search).get("widok"), false);

  request(urls.data).then(function (data) {
    root.classList.add("is-ready");
    apply(data);
    if (state.mode === "os") setMode("os", false);
  }).catch(function (error) {
    showMessage(error.message, true);
  });
})();
