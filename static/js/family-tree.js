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
  var GAP_FAMILY = 112; // przerwa między różnymi rodzinami w rzędzie (ETAP 38)
  var ROW_H = 180;
  // Kary w układaniu kolejności (ETAP 38, zob. autoLayout): przecięcie linii > dwie rodziny z kreskami
  // jedna nad drugą (rodzeństwo nie stoi blokiem) > rodzeństwo nie po kolei urodzenia.
  var CROSS_WEIGHT = 4;
  var OVERLAP_WEIGHT = 1;
  var BIRTH_WEIGHT = 1;
  var ZOOM_MIN = 0.2;
  var ZOOM_MAX = 2.5;
  var MOVE_MIN = 5; // px: mniejszy ruch to kliknięcie, nie przeciąganie
  var SVG_NS = "http://www.w3.org/2000/svg";
  var KINDS = { rodzic: "rodzica", partner: "partnera lub partnerkę", dziecko: "dziecko", rodzenstwo: "brata lub siostrę" };
  var KIND_NAMES = { rodzic: "rodzic", partner: "partner / partnerka", dziecko: "dziecko", rodzenstwo: "brat / siostra" };

  var urls = {
    data: root.getAttribute("data-url-data"),
    positions: root.getAttribute("data-url-positions"),
    add: root.getAttribute("data-url-add"),
    relation: root.getAttribute("data-url-relation"),
    remove: root.getAttribute("data-url-remove"),
    alive: root.getAttribute("data-url-alive"),
    couple: root.getAttribute("data-url-couple"),
    person: root.getAttribute("data-url-person"),
  };
  var csrf = root.getAttribute("data-csrf");
  var canvas = root.querySelector(".tree-canvas");
  var world = root.querySelector(".tree-world");
  var lines = root.querySelector(".tree-lines");
  var nodesLayer = root.querySelector(".tree-nodes");
  var sheet = root.querySelector(".tree-sheet");
  var editPanel = root.querySelector(".tree-edit");
  var cardBox = root.querySelector(".tree-card");
  var cardFrame = root.querySelector(".tree-card__frame");
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
    gen: {}, bands: [], mode: "drzewo", tl: { px: null }, edit: null,
    // ETAP 35: drzewo zawsze ułożone automatycznie (bez przesuwania kafelków).
    shown: null, layoutGen: {},
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
    data.people.forEach(function (p) { index[p.id] = { parents: [], children: [], partners: [], siblings: [] }; });
    // ETAP 33: rodzeństwo zapisane wprost (bez wspólnego rodzica w drzewie).
    (data.siblings || []).forEach(function (pair) {
      if (index[pair[0]] && index[pair[1]]) {
        index[pair[0]].siblings.push(pair[1]);
        index[pair[1]].siblings.push(pair[0]);
      }
    });
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
    var kids = {};
    data.people.forEach(function (p) { gen[p.id] = 0; kids[p.id] = []; });
    data.parents.forEach(function (link) { if (kids[link[0]] && gen[link[1]] !== undefined) kids[link[0]].push(link[1]); });
    for (var round = 0; round < 60; round++) {
      var changed = false;
      // ETAP 36: rodzice bez własnych rodziców w drzewie (np. teściowie) stoją tuż nad swoimi
      // dziećmi, a nie w górnym rzędzie z protoplastami. Inaczej ich linie biegły przez całe drzewo.
      data.people.forEach(function (p) {
        if (!kids[p.id].length) return;
        var target = Math.min.apply(null, kids[p.id].map(function (c) { return gen[c]; })) - 1;
        if (gen[p.id] < target) { gen[p.id] = target; changed = true; }
      });
      data.parents.forEach(function (link) {
        if (gen[link[1]] !== undefined && gen[link[0]] !== undefined && gen[link[1]] < gen[link[0]] + 1) {
          gen[link[1]] = gen[link[0]] + 1;
          changed = true;
        }
      });
      data.partners.concat(data.siblings || []).forEach(function (pair) {
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
        r.parents.concat(r.children, r.partners, r.siblings).forEach(function (q) {
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
    // Rodzeństwo bez wspólnego rodzica (ETAP 33) stoi obok siebie, od najstarszego: łączymy ich
    // jednostki (każde ze swoimi partnerami) w jedną.
    rows = rows.map(function (row) {
      var unitOf = {};
      row.forEach(function (unit, i) { unit.forEach(function (id) { unitOf[id] = i; }); });
      var groupOf = row.map(function (_, i) { return i; });
      function find(i) { while (groupOf[i] !== i) i = groupOf[i] = groupOf[groupOf[i]]; return i; }
      row.forEach(function (unit, i) {
        unit.forEach(function (id) {
          rel[id].siblings.forEach(function (q) {
            if (unitOf[q] !== undefined && gen[q] === gen[id]) groupOf[find(unitOf[q])] = find(i);
          });
        });
      });
      var merged = {}, out = [];
      row.forEach(function (unit, i) {
        var root = find(i);
        if (!merged[root]) { merged[root] = []; out.push(merged[root]); }
        merged[root].push(unit);
      });
      return out.map(function (units) {
        if (units.length === 1) return units[0];
        var born = function (unit) {
          var years = unit.filter(function (id) { return rel[id].siblings.length; })
            .map(function (id) { return byId[id].born; }).filter(function (y) { return y !== null && y !== undefined; });
          return years.length ? Math.min.apply(null, years) : 9999;
        };
        units.sort(function (a, b) { return born(a) - born(b); });
        // Para: brat lub siostra stoi bliżej rodzeństwa, a partner/ka na zewnątrz.
        var linked = function (id) { return rel[id].siblings.length > 0; };
        units = units.map(function (unit, i) {
          if (unit.length !== 2 || linked(unit[0]) === linked(unit[1])) return unit;
          var first = i === 0, last = i === units.length - 1;
          if (first && linked(unit[0])) return [unit[1], unit[0]];
          if (last && !first && linked(unit[1])) return [unit[1], unit[0]];
          return unit;
        });
        return [].concat.apply([], units);
      });
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
          // Lepsza z dwóch kolejności szyn, plus kara za samo zachodzenie: rodziny mają stać obok
          // siebie, każda swoim blokiem, a nie mieć kreski jedna nad drugą.
          n += CROSS_WEIGHT * Math.min(costAbove(list[i], list[j]), costAbove(list[j], list[i])) + OVERLAP_WEIGHT;
        }
      }
      return n;
    }

    // Rodzeństwo od najstarszego z lewej (ETAP 30): każda para rodzeństwa w złej kolejności to kara
    // BIRTH_WEIGHT. Od ETAPU 38 jest najlżejsza: osoba, której małżeństwo łączy dwie rodziny, stoi na
    // brzegu swojego rodzeństwa, nawet gdy nie jest najmłodsza, bo wtedy linie się nie krzyżują.
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

    // Kolejność szukamy z kilku punktów startowych (ETAP 36): metoda średnich i poprawki lokalne
    // potrafią utknąć, np. gdy cała rodzina teściów powinna przejść na drugą stronę. Wygrywa układ
    // z najmniejszą liczbą przecięć; przy dużym drzewie starczy mniej prób, żeby nie trwało za długo.
    var orders, bestScore;
    function optimize(start) {
      orders = start;
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

      // Przeniesienie jednostki w dowolne miejsce rzędu (ETAP 36). Sama zamiana sąsiadów utyka, gdy
      // kafelek musi przejść obok kilku innych, np. dziecko rodziny stojącej bardziej po prawej.
      function siftRow(row) {
        var improved = false;
        for (var i = 0; i < row.length; i++) {
          var unit = row[i], bestAt = i;
          var rest = row.slice(0, i).concat(row.slice(i + 1));
          for (var at = 0; at <= rest.length; at++) {
            if (at === i) continue;
            var tried = rest.slice(0, at).concat([unit], rest.slice(at));
            for (var k = 0; k < row.length; k++) row[k] = tried[k];
            var now = total(orders);
            if (now < bestScore - 1e-9) { bestScore = now; bestAt = at; improved = true; }
          }
          var final = rest.slice(0, bestAt).concat([unit], rest.slice(bestAt));
          for (k = 0; k < row.length; k++) row[k] = final[k];
        }
        return improved;
      }

      // Poprawki lokalne: przenoszenie jednostek i odwrócenie par, dopóki ubywa przecięć.
      for (var round = 0; round < 20 && bestScore > 0; round++) {
        var improved = birthOrderPass();
        for (d = 0; d < orders.length; d++) {
          var row = orders[d];
          if (siftRow(row)) improved = true;
          for (var i = 0; i < row.length; i++) {
            var tries = [];
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
      return { orders: orders, score: bestScore };
    }
    var seed = 7;
    function shuffled(row) {
      var out = row.slice();
      for (var i = out.length - 1; i > 0; i--) {
        seed = (seed * 1103515245 + 12345) % 2147483648;
        var j = seed % (i + 1), t = out[i];
        out[i] = out[j];
        out[j] = t;
      }
      return out;
    }
    var starts = [
      rows.map(function (row) { return row.slice(); }),
      rows.map(function (row) { return row.slice().reverse(); }),
    ];
    var extra = data.people.length > 80 ? 0 : data.people.length > 40 ? 2 : 4;
    for (var s = 0; s < extra; s++) starts.push(rows.map(shuffled));
    var winner = null;
    starts.forEach(function (start) {
      if (winner && winner.score <= 0) return;
      var result = optimize(start);
      if (!winner || result.score < winner.score - 1e-9) winner = { orders: result.orders, score: result.score };
    });
    orders = winner.orders;

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

    // Współrzędne (ETAP 36): kolejność w rzędach już jest, teraz miejsca. Każda jednostka (osoba
    // z partnerami) chce stać nad środkiem swoich dzieci i pod środkiem swoich rodziców. W każdym rzędzie
    // szukamy miejsc najbliższych tym życzeniom bez nachodzenia kafelków (regresja izotoniczna, PAV),
    // na zmianę od góry i od dołu, aż drzewo się ustatkuje. Dzięki temu rodzice stoją nad dziećmi,
    // a drzewo nie rozjeżdża się na boki tak jak przy układaniu tylko od góry.
    var pos = {};
    var step = NODE_W + GAP_X;
    var childrenOf = {};
    data.people.forEach(function (p) { childrenOf[p.id] = rel[p.id].children; });
    // Odstępy mówią, kto do kogo należy (ETAP 38): rodzeństwo i rodzina stoją ciasno (GAP_X),
    // a między różnymi rodzinami jest większa przerwa (GAP_FAMILY).
    function familyKeys(unit) {
      var keys = {};
      unit.forEach(function (id) {
        (familiesOf[id] || []).forEach(function (family) { keys[family.join("+")] = true; });
        rel[id].siblings.forEach(function (q) { keys["s" + Math.min(id, q) + "-" + Math.max(id, q)] = true; });
      });
      return keys;
    }
    function together(a, b) {
      var ka = familyKeys(a), kb = familyKeys(b);
      return Object.keys(ka).some(function (k) { return kb[k]; });
    }
    var gapsAfter = orders.map(function (order) {
      return order.map(function (unit, j) {
        if (j === order.length - 1) return 0;
        return together(unit, order[j + 1]) ? GAP_X : GAP_FAMILY;
      });
    });
    function unitWidth(order, j) { return (order[j].length - 1) * step + NODE_W + gapsAfter[orders.indexOf(order)][j]; }
    orders.forEach(function (order, depth) {
      var x = 0;
      order.forEach(function (unit, j) {
        unit.forEach(function (id, k) { pos[id] = [x + k * step, depth * ROW_H]; });
        x += unitWidth(order, j);
      });
    });
    function centerOf(ids) {
      var known = ids.filter(function (id) { return pos[id]; });
      return known.length ? average(known.map(function (id) { return pos[id][0]; })) : null;
    }
    function wantOf(id, useParents, useChildren) {
      var wants = [];
      if (useParents) {
        (familiesOf[id] || []).forEach(function (family) {
          var c = centerOf(family);
          if (c !== null) wants.push(c);
        });
      }
      if (useChildren) {
        var c = centerOf(childrenOf[id]);
        if (c !== null) wants.push(c);
      }
      return wants.length ? average(wants) : null;
    }
    function placeRow(order, useParents, useChildren) {
      if (!order.length) return;
      var blocks = [], offset = 0;
      order.forEach(function (unit, j) {
        var sum = 0, weight = 0;
        unit.forEach(function (id, k) {
          var want = wantOf(id, useParents, useChildren);
          if (want !== null) { sum += want - k * step; weight += 1; }
        });
        var current = pos[unit[0]][0];
        var target = weight ? sum / weight : current;
        if (!weight) weight = 0.01;
        // Przesunięcie o szerokość wcześniejszych jednostek: wtedy warunek „bez nachodzenia” to
        // po prostu niemalejący ciąg, a takie zadanie rozwiązuje PAV.
        var block = { w: weight, wt: weight * (target - offset), from: j, to: j };
        offset += unitWidth(order, j);
        while (blocks.length && blocks[blocks.length - 1].wt / blocks[blocks.length - 1].w > block.wt / block.w) {
          var prev = blocks.pop();
          block = { w: prev.w + block.w, wt: prev.wt + block.wt, from: prev.from, to: block.to };
        }
        blocks.push(block);
      });
      offset = 0;
      var j = 0;
      blocks.forEach(function (block) {
        var y = block.wt / block.w;
        for (; j <= block.to; j++) {
          order[j].forEach(function (id, k) { pos[id][0] = y + offset + k * step; });
          offset += unitWidth(order, j);
        }
      });
    }
    for (var sweep = 0; sweep < 12; sweep++) {
      for (d = 1; d < orders.length; d++) placeRow(orders[d], true, sweep > 0);
      for (d = orders.length - 2; d >= 0; d--) placeRow(orders[d], sweep > 0, true);
    }
    var all = Object.keys(pos);
    if (all.length) {
      var left = Math.min.apply(null, all.map(function (id) { return pos[id][0]; }));
      var right = Math.max.apply(null, all.map(function (id) { return pos[id][0]; }));
      all.forEach(function (id) { pos[id][0] = Math.round(pos[id][0] - (left + right) / 2); });
    }
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
    var people = state.shown.people;
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
    return ["rodzic", "partner", "dziecko", "rodzenstwo"].filter(function (kind) {
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
    var blocked = Math.abs(a.y - b.y) < 1 && state.shown.people.some(function (p) {
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
    var couples = couplesIndex(state.shown);
    var rel = relativesIndex(state.shown);
    state.shown.partners.forEach(function (pair) {
      var a = byId[pair[0]], b = byId[pair[1]];
      if (!a || !b) return;
      partnerOf[pair[0] + "-" + pair[1]] = partnerOf[pair[1] + "-" + pair[0]] = true;
      drawCouple(a, b, couples[coupleKey(a.id, b.id)] || {}, rel, couples);
    });
    // Rodzina = rodzice (para albo jedna osoba) i ich dzieci w jednym rzędzie. Każda rodzina ma własną
    // poziomą „szynę” od rodziców nad dzieci; szyny różnych rodzin w tym samym odstępie między rzędami
    // leżą na różnych wysokościach, żeby się nie zlewały i było widać, czyje jest które dziecko.
    var parentsOf = {};
    state.shown.parents.forEach(function (link) {
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
        laneOrder(geometry).forEach(function (g, lane) { g.f.lane = lane; });
        count = Math.max(count, group.length);
      });
      lanes[gap] = { length: count };
    });
    list.forEach(function (f) {
      var count = lanes[f.gap].length;
      // Wszystkie linie rodzin w jednym kolorze (ETAP 37). Zachodzące rodziny rozróżniają osobne
      // tory (wysokości szyn) i kropki w miejscach odejścia dzieci.
      var cls = "tree-line";
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
    drawSiblings(rel);
    drawBands();
  }

  // Rodzeństwo bez wspólnego rodzica w drzewie (ETAP 33): klamra nad kafelkami, przerywana, bo
  // rodziców jeszcze nie ma. Rodzeństwo ze wspólnym rodzicem łączy już szyna rodziny.
  function drawSiblings(rel) {
    var seen = {};
    state.shown.people.forEach(function (p) {
      if (seen[p.id] || !rel[p.id].siblings.length) return;
      var group = [], queue = [p.id];
      seen[p.id] = true;
      while (queue.length) {
        var id = queue.shift();
        group.push(id);
        rel[id].siblings.forEach(function (q) {
          var shared = rel[q].parents.some(function (x) { return rel[id].parents.indexOf(x) >= 0; });
          if (!seen[q] && !shared) { seen[q] = true; queue.push(q); }
        });
      }
      var nodes = group.map(function (id) { return state.byId[id]; }).filter(function (q) { return q && q.x !== null; });
      if (nodes.length < 2) return;
      // Kafelki rodzeństwa w różnych rzędach: klamra nad najwyższym z nich.
      var top = Math.min.apply(null, nodes.map(function (q) { return q.y; }));
      var bus = top - 26;
      var xs = nodes.map(function (q) { return q.x + NODE_W / 2; });
      var cls = "tree-line tree-line--sibling";
      path("M" + Math.min.apply(null, xs) + "," + bus + " H" + Math.max.apply(null, xs), cls);
      nodes.forEach(function (q) { path("M" + (q.x + NODE_W / 2) + "," + bus + " V" + q.y, cls); });
      label((Math.min.apply(null, xs) + Math.max.apply(null, xs)) / 2, bus - 6, "rodzeństwo", "tree-couple-label tree-sibling-label");
    });
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
    if (sel && state.layoutGen[sel.id] !== undefined) {
      var d = g - state.layoutGen[sel.id];
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
    state.shown.people.forEach(function (p) {
      var g = state.layoutGen[p.id];
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
    state.shown.people.forEach(function (p) {
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
    var wanted = null;
    if (first) {
      wanted = parseInt(new URLSearchParams(location.search).get("osoba"), 10);
      if (state.byId[wanted]) state.selected = wanted;
    }
    layout();
    render();
    renderSheet();
    if (first) {
      if (state.byId[wanted]) focusOn(wanted); else fit();
    }
    renderOutside();
    renderNames();
    return data;
  }

  // --- ETAP 35: układ zawsze automatyczny -----------------------------------------

  function layout() {
    var data = state.data;
    state.shown = data;
    state.layoutGen = generations(data);
    var pos = data.people.length ? autoLayout(data) : {};
    data.people.forEach(function (p) {
      var at = pos[p.id];
      p.x = at ? at[0] : null;
      p.y = at ? at[1] : null;
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
    siblingsOf(person.id, index).forEach(function (sib) { rows.push(["rodzenstwo", sib.id, sib.linked]); });
    rel.children.forEach(function (id) { rows.push(["dziecko", id]); });
    return rows;
  }

  // Rodzeństwo: przez wspólnego rodzica i zapisane wprost. ``linked`` = da się usunąć samo połączenie.
  function siblingsOf(id, index) {
    var rel = index[id], viaParent = {}, list = [];
    rel.parents.forEach(function (p) {
      index[p].children.forEach(function (c) { if (c !== id) viaParent[c] = true; });
    });
    Object.keys(viaParent).forEach(function (c) { list.push({ id: +c, linked: false }); });
    rel.siblings.forEach(function (c) { if (!viaParent[c]) list.push({ id: c, linked: true }); });
    list.sort(function (a, b) {
      var x = state.byId[a.id].born, y = state.byId[b.id].born;
      return (x == null ? 9999 : x) - (y == null ? 9999 : y);
    });
    return list;
  }

  var LABELS = { rodzic: "rodzic", partner: "partner/ka", dziecko: "dziecko", rodzenstwo: "rodzeństwo" };

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

  // --- ETAP 34: dane osoby w panelu, edycja jako nakładka, karta w okienku ---------

  var FACT_ROWS = [
    ["Urodzenie", "birth", "birthPlace"],
    ["Śmierć", "death", "deathPlace"],
  ];

  function personFacts(person) {
    var box = el("div", "tree-facts");
    var list = el("dl", "tree-facts__list");
    FACT_ROWS.forEach(function (row) {
      var text = [person[row[1]], person[row[2]]].filter(Boolean).join(", ");
      if (row[1] === "death" && !text && person.deceased) text = "nie żyje";
      if (!text) return;
      var item = el("div");
      item.appendChild(el("dt", "", row[0]));
      item.appendChild(el("dd", "", (row[1] === "death" ? "† " : "") + text));
      list.appendChild(item);
    });
    if (list.childNodes.length) box.appendChild(list);
    if (person.bio) {
      var bio = el("p", "tree-facts__bio", person.bio);
      box.appendChild(bio);
      if (person.bio.length > 180) {
        bio.classList.add("is-clamped");
        var more = el("button", "link-button tree-facts__more", "Więcej");
        more.type = "button";
        more.addEventListener("click", function () {
          var open = bio.classList.toggle("is-clamped");
          more.textContent = open ? "Więcej" : "Mniej";
        });
        box.appendChild(more);
      }
    }
    if (!box.childNodes.length) {
      box.appendChild(el("p", "hint tree-facts__empty", state.data.canEdit ? "Brak dat i opisu. Uzupełnisz je w „Edytuj dane”." : "Brak dat i opisu."));
    }
    return box;
  }

  var EDIT_FIELDS = [
    ["name", "Imię i nazwisko", "", 100],
    ["maiden", "Nazwisko rodowe", "np. Nowak", 100],
    ["birth", "Data urodzenia", "np. 12.06.1921, 1921, ok. 1920, lata 20.", 60],
    ["birthPlace", "Miejsce urodzenia", "", 200],
    ["deceased"],
    ["death", "Data śmierci", "jak data urodzenia", 60],
    ["deathPlace", "Miejsce śmierci", "", 200],
    ["bio", "Opis", "Kim była, gdzie mieszkała, rodzinne historie.", 0],
  ];

  function personUrl(id) { return urls.person.replace(/\/0\/$/, "/" + id + "/"); }

  function openEdit(id) {
    var person = state.byId[id];
    if (!person || !state.data.canEdit) return;
    state.edit = { id: id, portraits: null, portrait: null, errors: {} };
    renderEdit();
    request(personUrl(id)).then(function (data) {
      if (!state.edit || state.edit.id !== id) return;
      state.edit.portraits = data.portraits;
      state.edit.portrait = data.portrait;
      renderPortraits();
    }).catch(function () {
      if (state.edit && state.edit.id === id) { state.edit.portraits = []; renderPortraits(); }
    });
    var first = editPanel.querySelector("input");
    if (first) first.focus();
  }

  function closeEdit() {
    state.edit = null;
    editPanel.hidden = true;
    editPanel.textContent = "";
    root.classList.remove("has-edit");
  }

  function renderEdit() {
    var person = state.edit && state.byId[state.edit.id];
    editPanel.textContent = "";
    if (!person) { closeEdit(); return; }
    editPanel.hidden = false;
    root.classList.add("has-edit");
    var head = el("div", "tree-edit__head");
    var back = el("button", "link-button tree-edit__back", "← " + person.name);
    back.type = "button";
    back.setAttribute("aria-label", "Wróć bez zapisywania");
    back.addEventListener("click", closeEdit);
    head.appendChild(back);
    head.appendChild(el("h2", "", "Dane osoby"));
    editPanel.appendChild(head);

    var form = el("form", "tree-edit__form");
    form.noValidate = true;
    var inputs = {};
    EDIT_FIELDS.forEach(function (field) {
      var key = field[0];
      var row = el("div", "field");
      if (key === "deceased") {
        var check = el("label", "check");
        var box = el("input");
        box.type = "checkbox";
        box.name = key;
        box.checked = !!person.deceased;
        check.appendChild(box);
        check.appendChild(document.createTextNode(" Nie żyje †"));
        row.appendChild(check);
        row.appendChild(el("p", "hint", "Zaznacza się samo, gdy wpiszesz datę lub miejsce śmierci."));
        inputs[key] = box;
        form.appendChild(row);
        return;
      }
      var id = "osoba-" + key;
      var label = el("label", "", field[1]);
      label.htmlFor = id;
      var input = el(key === "bio" ? "textarea" : "input");
      if (key === "bio") input.rows = 5; else input.type = "text";
      input.id = id;
      input.name = key;
      input.value = person[key] || "";
      if (field[2]) input.placeholder = field[2];
      if (field[3]) input.maxLength = field[3];
      if (key === "name") input.required = true;
      row.appendChild(label);
      row.appendChild(input);
      inputs[key] = input;
      form.appendChild(row);
    });
    var portraitBox = el("fieldset", "field tree-edit__portraits");
    portraitBox.appendChild(el("legend", "", "Portret"));
    portraitBox.appendChild(el("p", "hint", "Wczytuję zdjęcia…"));
    form.appendChild(portraitBox);

    var row = el("div", "tree-form__buttons tree-edit__buttons");
    var save = el("button", "button", "Zapisz");
    save.type = "submit";
    var cancel = el("button", "button button--quiet", "Anuluj");
    cancel.type = "button";
    cancel.addEventListener("click", closeEdit);
    row.appendChild(save);
    row.appendChild(cancel);
    form.appendChild(row);

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (state.busy) return;
      var body = {};
      EDIT_FIELDS.forEach(function (field) {
        var input = inputs[field[0]];
        body[field[0]] = field[0] === "deceased" ? input.checked : input.value;
      });
      var chosen = form.querySelector("input[name=portrait]:checked");
      body.portrait = chosen ? chosen.value : (state.edit.portraits ? "" : state.edit.portrait);
      var id = state.edit.id;
      request(personUrl(id), body).then(function (data) {
        closeEdit();
        apply(data);
        showMessage(data.notice || "Zapisano: " + (state.byId[id] ? state.byId[id].name : "") + ".");
      }).catch(function (error) {
        var errors = (error.data && error.data.errors) || {};
        form.querySelectorAll(".field__error").forEach(function (node) { node.remove(); });
        form.querySelectorAll(".field--error").forEach(function (node) { node.classList.remove("field--error"); });
        var firstBad = null;
        Object.keys(errors).forEach(function (key) {
          var target = key === "portrait" ? portraitBox : inputs[key] && inputs[key].closest(".field");
          if (!target) return;
          target.classList.add("field--error");
          target.appendChild(el("p", "field__error", errors[key]));
          if (!firstBad && inputs[key]) firstBad = inputs[key];
        });
        if (firstBad) firstBad.focus();
        else showMessage(error.message, true);
      });
    });
    editPanel.appendChild(form);
    renderPortraits();
  }

  function renderPortraits() {
    var box = editPanel.querySelector(".tree-edit__portraits");
    if (!box || !state.edit) return;
    var person = state.byId[state.edit.id];
    while (box.childNodes.length > 1) box.removeChild(box.lastChild);
    var portraits = state.edit.portraits;
    if (!portraits) { box.appendChild(el("p", "hint", "Wczytuję zdjęcia…")); return; }
    if (!portraits.length) {
      box.appendChild(el("p", "hint", "Portret wybierzesz, gdy ktoś oznaczy tę osobę na zdjęciu (pole „Kto” w opisie zdjęcia)."));
      return;
    }
    box.appendChild(el("p", "hint", "Zdjęcie na kafelku w drzewie, spośród zdjęć z tą osobą."));
    var list = el("ul", "portrait-choice__list");
    var options = [{ id: "", url: null }].concat(portraits);
    options.forEach(function (photo) {
      var item = el("li");
      var label = el("label");
      var radio = el("input");
      radio.type = "radio";
      radio.name = "portrait";
      radio.value = photo.id;
      radio.checked = String(state.edit.portrait || "") === String(photo.id);
      label.appendChild(radio);
      if (photo.url) {
        var img = el("img", "rot-" + (photo.turn || 0));
        img.src = photo.url;
        img.alt = "Zdjęcie " + photo.id;
        img.loading = "lazy";
        label.appendChild(img);
      } else {
        label.appendChild(el("span", "tree-avatar tree-avatar--empty", person.name.charAt(0)));
        label.appendChild(el("span", "visually-hidden", "bez portretu"));
      }
      item.appendChild(label);
      list.appendChild(item);
    });
    box.appendChild(list);
  }

  // Karta osoby w okienku nad drzewem: pełna strona osoby w trybie ``?okno=1`` (bez menu i edycji).
  function openCard(id) {
    var person = state.byId[id];
    if (!person) return;
    cardFrame.src = person.url + "?okno=1";
    cardBox.querySelector(".tree-card__full").href = person.url;
    cardBox.hidden = false;
    root.classList.add("has-card");
    cardBox.querySelector(".tree-card__close").focus();
  }

  function closeCard() {
    cardBox.hidden = true;
    root.classList.remove("has-card");
    cardFrame.src = "about:blank";
    canvas.focus();
  }

  cardBox.querySelector(".tree-card__close").addEventListener("click", closeCard);
  cardBox.addEventListener("click", function (event) { if (event.target === cardBox) closeCard(); });
  cardFrame.addEventListener("load", function () {
    var doc;
    try { doc = cardFrame.contentDocument; } catch (error) { return; }
    if (!doc || cardBox.hidden) return;
    try { cardBox.querySelector(".tree-card__full").href = cardFrame.contentWindow.location.pathname; } catch (error) { /* inna domena */ }
    // Esc w okienku też je zamyka (chyba że jest w nim otwarty podgląd zdjęcia).
    doc.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !event.defaultPrevented && !doc.querySelector(".viewer:not([hidden])")) closeCard();
    });
    // Przejście w okienku do krewnego zaznacza go też w drzewie.
    var match = /\/osoba\/(\d+)\//.exec(cardFrame.contentWindow.location.pathname);
    var id = match && parseInt(match[1], 10);
    if (id && state.byId[id] && state.selected !== id) {
      if (state.edit) closeEdit();
      state.selected = id;
      state.form = null;
      render();
      renderSheet();
      if (state.mode === "os") revealRow(id); else reveal(id);
    }
  });

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
      closeEdit();
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
      sheet.appendChild(personFacts(person));
      var buttons = el("div", "tree-sheet__buttons");
      if (state.data.canEdit) {
        var editButton = el("button", "button", "Edytuj dane");
        editButton.type = "button";
        editButton.addEventListener("click", function () { openEdit(person.id); });
        buttons.appendChild(editButton);
      }
      var card = el("button", "button button--quiet", "Karta osoby i zdjęcia");
      card.type = "button";
      card.addEventListener("click", function () { openCard(person.id); });
      buttons.appendChild(card);
      sheet.appendChild(buttons);

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
          if (state.data.canEdit && (row[0] !== "rodzenstwo" || row[2])) {
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
        var button = el("button", "button button--quiet", "+ " + { rodzic: "Rodzic", partner: "Partner/ka", dziecko: "Dziecko", rodzenstwo: "Rodzeństwo" }[kind]);
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
        var option = el("option", "", KIND_NAMES[key]);
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
    if (state.edit && state.edit.id !== id) closeEdit();
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
    } else {
      // Kafelków nie przesuwamy (układ jest automatyczny): przeciągnięcie kafelka przesuwa widok,
      // a stuknięcie wybiera osobę.
      gesture = {
        type: "pan", start: [event.clientX, event.clientY], origin: [state.view.x, state.view.y], moved: false,
        node: node ? parseInt(node.getAttribute("data-id"), 10) : null,
      };
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
    if (event.type === "pointercancel") return;
    if (g.type === "pan") {
      if (g.moved) return;
      if (g.node) {
        select(g.node, false);
      } else {
        state.selected = null;
        if (state.form && state.form.to) state.form = null;
        render();
        renderSheet();
      }
    } else if (g.type === "link") {
      Object.keys(nodeEls).forEach(function (id) { nodeEls[id].classList.remove("is-target"); });
      drawLines();
      var target = g.moved ? nodeAt(event.clientX, event.clientY) : null;
      if (target && target !== g.from) {
        var source = state.byId[g.from];
        var other = state.byId[target];
        send(urls.relation, { person: g.from, other: target, kind: g.kind }).then(function () {
          showMessage({ rodzic: other.name + " jest rodzicem: " + source.name, partner: "Para: " + source.name + " i " + other.name, dziecko: other.name + " jest dzieckiem: " + source.name, rodzenstwo: "Rodzeństwo: " + source.name + " i " + other.name }[g.kind] + ".");
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
  });

  // Esc chowa wysuniętą kartę osoby.
  root.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" || event.defaultPrevented) return;
    // Najpierw zamyka się to, co leży najwyżej: karta osoby, potem edycja, na końcu panel.
    if (!cardBox.hidden) { closeCard(); return; }
    if (state.edit) { closeEdit(); return; }
    if (sheet.hidden) return;
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
